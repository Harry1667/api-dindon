"""排程測試 Celery 任務 — 每分鐘檢查是否需要跑排程測試"""

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.test_scheduler.check_scheduled_test")
def check_scheduled_test():
    """每分鐘由 beat 呼叫，檢查排程測試"""
    try:
        from app.api.test_harness import run_scheduled_test_if_needed
        _run_async(run_scheduled_test_if_needed())
    except Exception as e:
        logger.error(f"[test_scheduler] 排程測試失敗: {e}")
