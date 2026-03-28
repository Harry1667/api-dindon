"""NHI 醫事機構資料同步排程任務"""

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在 Celery worker (sync) 中執行 async 函式"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.tasks.nhi_sync.sync_nhi_institutions",
    soft_time_limit=540,
    time_limit=600,
)
def sync_nhi_institutions(types: list[str] | None = None):
    """
    同步 NHI 醫事機構資料到本地 DB

    Args:
        types: 指定同步類型，如 ["醫學中心", "區域醫院"]
               預設同步全部五種
    """
    try:
        result = _run_async(_sync(types))
        logger.info(f"[NHI Sync Task] 完成: {result}")
        return result
    except Exception as e:
        logger.error(f"[NHI Sync Task] 失敗: {e}", exc_info=True)


@celery_app.task(name="app.tasks.nhi_sync.sync_nhi_hospitals_only")
def sync_nhi_hospitals_only():
    """只同步醫院類（醫學中心+區域醫院+地區醫院）"""
    try:
        result = _run_async(_sync(["醫學中心", "區域醫院", "地區醫院"]))
        logger.info(f"[NHI Sync Task] 醫院同步完成: {result}")
        return result
    except Exception as e:
        logger.error(f"[NHI Sync Task] 醫院同步失敗: {e}", exc_info=True)


async def _sync(types: list[str] | None = None):
    """建立獨立的 DB 連線進行同步"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.config import settings
    from app.services.nhi_sync import NhiSyncService

    task_engine = create_async_engine(
        settings.database_url,
        pool_size=3,
        max_overflow=5,
        pool_recycle=3600,
    )
    task_session = async_sessionmaker(
        task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        sync_service = NhiSyncService(session_factory=task_session)
        created, updated = await sync_service.sync_all(types)
        return {"created": created, "updated": updated}
    finally:
        await task_engine.dispose()
