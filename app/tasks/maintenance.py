"""定期維護任務 — 清理過期資料 + 統計診間排班"""

import logging
from datetime import datetime, timedelta, time

from sqlalchemy import text, delete, select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.tasks.celery_app import celery_app
from app.config import settings
from app.models.clinic_progress import ClinicProgress
from app.models.clinic_schedule import ClinicSchedule

logger = logging.getLogger(__name__)

RETAIN_DAYS = 7  # 保留最近 N 天資料


def _run_async(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.maintenance.cleanup_old_progress")
def cleanup_old_progress():
    """刪除超過 RETAIN_DAYS 天的 clinic_progress 資料（每日凌晨執行）"""
    _run_async(_do_cleanup())


async def _do_cleanup():
    cutoff = datetime.utcnow() - timedelta(days=RETAIN_DAYS)
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    total_deleted = 0
    batch_size = 10000

    try:
        while True:
            async with session_factory() as session:
                # 分批刪除，避免長時間 lock
                result = await session.execute(
                    text(
                        "DELETE FROM clinic_progress "
                        "WHERE fetched_at < :cutoff "
                        "LIMIT :batch"
                    ),
                    {"cutoff": cutoff, "batch": batch_size},
                )
                await session.commit()
                deleted = result.rowcount

            total_deleted += deleted
            if deleted < batch_size:
                break

        logger.info(f"[maintenance] 清理完成：刪除 {total_deleted} 筆 clinic_progress（>{RETAIN_DAYS}天）")
    except Exception as e:
        logger.error(f"[maintenance] 清理失敗: {e}")
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.maintenance.build_clinic_schedule")
def build_clinic_schedule():
    """從 ClinicProgress 歷史資料統計每個診間的開關診時間（每天凌晨 1 點執行）

    邏輯：
    - 取最近 14 天的資料（避免過舊資料影響）
    - GROUP BY hospital_code + department + clinic_room + weekday
    - 計算 MIN(fetched_at time) = 開診時間，MAX(fetched_at time) = 關診時間
    - UPSERT 到 clinic_schedule
    """
    _run_async(_do_build_schedule())


async def _do_build_schedule():
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 只取最近 14 天資料
    cutoff = datetime.utcnow() - timedelta(days=14)
    tz = ZoneInfo("Asia/Taipei")

    try:
        async with session_factory() as session:
            # 用 raw SQL 做聚合（性能比 ORM 好，資料量可能很大）
            rows = await session.execute(text("""
                SELECT
                    hospital_code,
                    department,
                    clinic_room,
                    WEEKDAY(CONVERT_TZ(fetched_at, '+00:00', '+08:00')) AS weekday,
                    TIME(MIN(CONVERT_TZ(fetched_at, '+00:00', '+08:00')))  AS open_time,
                    TIME(MAX(CONVERT_TZ(fetched_at, '+00:00', '+08:00')))  AS close_time,
                    COUNT(*) AS sample_count
                FROM clinic_progress
                WHERE fetched_at >= :cutoff
                GROUP BY hospital_code, department, clinic_room, weekday
            """), {"cutoff": cutoff})

            records = rows.fetchall()

        if not records:
            logger.info("[maintenance] build_clinic_schedule: 無資料可統計")
            return

        # UPSERT — MySQL ON DUPLICATE KEY UPDATE
        upsert_sql = text("""
            INSERT INTO clinic_schedule
                (hospital_code, department, clinic_room, weekday,
                 open_time, close_time, sample_count, updated_at)
            VALUES
                (:hospital_code, :department, :clinic_room, :weekday,
                 :open_time, :close_time, :sample_count, NOW())
            ON DUPLICATE KEY UPDATE
                open_time    = LEAST(open_time, VALUES(open_time)),
                close_time   = GREATEST(close_time, VALUES(close_time)),
                sample_count = VALUES(sample_count),
                updated_at   = NOW()
        """)

        async with session_factory() as session:
            for row in records:
                await session.execute(upsert_sql, {
                    "hospital_code": row.hospital_code,
                    "department":    row.department,
                    "clinic_room":   row.clinic_room,
                    "weekday":       row.weekday,
                    "open_time":     str(row.open_time),
                    "close_time":    str(row.close_time),
                    "sample_count":  row.sample_count,
                })
            await session.commit()

        logger.info(f"[maintenance] build_clinic_schedule: 更新 {len(records)} 筆診間排班")
    except Exception as e:
        logger.error(f"[maintenance] build_clinic_schedule 失敗: {e}")
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.maintenance.cleanup_stale_web_tracks")
def cleanup_stale_web_tracks():
    """清理過期的網頁追蹤任務（每 30 分鐘執行）

    條件：source=web + status=ACTIVE + 建立超過 4 小時
    代表用戶已離開網頁或診別已結束，自動標為 cancelled
    """
    _run_async(_do_cleanup_web_tracks())


async def _do_cleanup_web_tracks():
    cutoff = datetime.utcnow() - timedelta(hours=4)
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "UPDATE tracking_tasks SET status='CANCELLED' "
                    "WHERE source='web' AND status='ACTIVE' AND created_at < :cutoff"
                ),
                {"cutoff": cutoff},
            )
            await session.commit()
            count = result.rowcount
        if count:
            logger.info(f"[maintenance] 清理網頁追蹤：{count} 筆過期任務自動取消")
    except Exception as e:
        logger.error(f"[maintenance] 清理網頁追蹤失敗: {e}")
    finally:
        await engine.dispose()
