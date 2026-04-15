"""定期維護任務 — 清理過期資料"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import text, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.tasks.celery_app import celery_app
from app.config import settings
from app.models.clinic_progress import ClinicProgress

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
