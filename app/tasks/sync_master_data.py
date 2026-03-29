"""同步醫院主檔資料 — 從各醫院爬蟲提取診科/醫生，寫入 MySQL

排程：每天凌晨 4 點執行一次（看診時段外）
也可透過 API 手動觸發：POST /api/admin/sync-master-data
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.tasks.celery_app import celery_app
from app.scrapers.registry import AdapterRegistry
from app.models.database import async_session
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.clinic_progress import ClinicProgress

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在 Celery worker (sync) 中執行 async 函式"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.sync_master_data.sync_master_data", bind=True, max_retries=2)
def sync_master_data(self):
    """Celery 任務：同步所有醫院的診科與醫生主檔到 MySQL"""
    try:
        result = _run_async(_sync_all())
        return result
    except Exception as exc:
        logger.error(f"同步主檔任務失敗: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)


async def _sync_all() -> dict:
    """對所有已註冊的 Adapter 執行爬取，提取診科與醫生寫入 MySQL"""
    adapters = AdapterRegistry.get_all()
    total_depts = 0
    total_doctors = 0
    total_progress = 0
    errors = []

    for code, adapter in adapters.items():
        try:
            logger.info(f"[sync] 開始同步 {adapter.hospital_name} ({code})")
            progress_list = await adapter.fetch_all_progress()

            if not progress_list:
                logger.info(f"[sync] {adapter.hospital_name} 目前無資料（可能非看診時段）")
                continue

            async with async_session() as session:
                # --- 寫入 clinic_progress ---
                for p in progress_list:
                    session.add(ClinicProgress(
                        hospital_code=p.hospital_code,
                        date=p.date,
                        session=p.session,
                        department=p.department,
                        doctor_name=p.doctor_name,
                        clinic_room=p.clinic_room,
                        current_number=p.current_number,
                        next_number=p.next_number,
                        is_current_skipped=p.is_current_skipped,
                        is_next_skipped=p.is_next_skipped,
                        fetched_at=p.fetched_at,
                    ))
                total_progress += len(progress_list)

                # --- 提取並 upsert 診科 ---
                dept_names = sorted(set(p.department for p in progress_list if p.department))
                for dept_name in dept_names:
                    result = await session.execute(
                        select(Department).where(
                            Department.hospital_code == code,
                            Department.name == dept_name,
                        )
                    )
                    existing = result.scalar_one_or_none()
                    if not existing:
                        session.add(Department(
                            hospital_code=code,
                            name=dept_name,
                        ))
                        total_depts += 1

                # --- 提取並 upsert 醫生 ---
                seen_doctors = set()
                for p in progress_list:
                    if not p.doctor_name:
                        continue
                    key = (code, p.department, p.doctor_name)
                    if key in seen_doctors:
                        continue
                    seen_doctors.add(key)

                    result = await session.execute(
                        select(Doctor).where(
                            Doctor.hospital_code == code,
                            Doctor.department == p.department,
                            Doctor.name == p.doctor_name,
                        )
                    )
                    existing = result.scalar_one_or_none()
                    if not existing:
                        session.add(Doctor(
                            hospital_code=code,
                            department=p.department,
                            name=p.doctor_name,
                            clinic_room=p.clinic_room,
                        ))
                        total_doctors += 1
                    else:
                        # 更新最近看診的診間
                        existing.clinic_room = p.clinic_room
                        existing.updated_at = datetime.utcnow()

                await session.commit()
                logger.info(
                    f"[sync] {adapter.hospital_name} 完成: "
                    f"{len(progress_list)} 筆進度, {len(dept_names)} 科別, {len(seen_doctors)} 醫師"
                )

        except Exception as e:
            logger.error(f"[sync] {adapter.hospital_name} 同步失敗: {e}")
            errors.append({"hospital": code, "error": str(e)})

    summary = {
        "new_departments": total_depts,
        "new_doctors": total_doctors,
        "progress_records": total_progress,
        "errors": errors,
    }
    logger.info(f"[sync] 全部完成: {summary}")
    return summary
