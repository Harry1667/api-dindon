"""通知推播排程任務"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

TW_TZ = ZoneInfo("Asia/Taipei")


def _is_operating_hours() -> bool:
    """判斷現在是否在看診時間"""
    now = datetime.now(TW_TZ)
    if now.weekday() == 6:  # 週日
        return False
    if now.hour < 7 or now.hour > 21:
        return False
    if now.hour == 21 and now.minute > 30:
        return False
    return True


def _run_async(coro):
    """在 Celery worker (sync) 中執行 async 函式"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.notify.check_and_notify")
def check_and_notify():
    """檢查所有追蹤任務並推播通知（只在看診時間執行）"""
    if not _is_operating_hours():
        return

    try:
        _run_async(_check())
    except Exception as e:
        logger.error(f"通知任務失敗: {e}", exc_info=True)


async def _check():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.config import settings
    from app.services.notifier import NotifierService

    task_engine = create_async_engine(
        settings.database_url,
        pool_size=2,
        max_overflow=5,
        pool_recycle=3600,
    )
    task_session = async_sessionmaker(
        task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        notifier = NotifierService(session_factory=task_session)
        await notifier.check_and_notify()
    finally:
        await task_engine.dispose()
