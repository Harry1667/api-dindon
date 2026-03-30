"""通知推播服務 — 比對追蹤任務並推播 LINE 通知"""

import logging

from app.services.cache import CacheService
from app.services.tracker import TrackerService
from app.services.line_bot import LineBotService

logger = logging.getLogger(__name__)


class NotifierService:
    """比對追蹤任務與即時進度，觸發推播"""

    def __init__(self, session_factory=None):
        self.cache = CacheService()
        self.tracker = TrackerService(session_factory=session_factory)
        self.line_bot = LineBotService()

    async def check_and_notify(self):
        """檢查所有活躍追蹤任務，觸發到號通知"""
        active_tasks = await self.tracker.get_all_active_tasks()

        if not active_tasks:
            return

        logger.info(f"[notifier] 檢查 {len(active_tasks)} 筆追蹤任務")

        for task, line_user_id in active_tasks:
            try:
                await self._check_single_task(task, line_user_id)
            except Exception as e:
                logger.error(f"[notifier] 檢查任務 {task.id} 失敗: {e}")

    async def _check_single_task(self, task, line_user_id: str):
        """檢查單一追蹤任務"""
        results = await self.cache.search_progress(
            hospital_code=task.hospital_code,
            department=task.department if task.department else None,
            doctor_name=task.doctor_name,
            clinic_room=task.clinic_room,
        )

        if not results:
            return

        progress = results[0]
        current = progress.current_number
        user_num = task.user_number
        remaining = max(0, user_num - current)
        header = (
            f"{progress.hospital_name}-{progress.department} "
            f"{progress.doctor_name} {progress.clinic_room}"
        )

        message = None

        # 情境 1: 用戶已過號（目前號碼已超過用戶號碼）
        if current > user_num:
            message = (
                f"⚠️ 您的號碼已過號！\n"
                f"{header}\n"
                f"目前看到第 {current} 號，您是第 {user_num} 號\n"
                f"請儘速前往診間報到"
            )
        # 情境 2: 輪到了
        elif current >= user_num:
            message = (
                f"🔔 輪到您了！\n"
                f"{header}\n"
                f"目前已看到第 {current} 號，您是第 {user_num} 號\n"
                f"請儘速前往診間！"
            )
        # 情境 3: 快到了（在閾值內）
        elif current >= user_num - task.threshold:
            message = (
                f"🔔 您的看診號碼快到了！\n"
                f"{header}\n"
                f"目前看到第 {current} 號，您是第 {user_num} 號\n"
                f"預計還有約 {remaining} 位"
            )

        if message:
            try:
                await self.line_bot.push_message(line_user_id, message)
                await self.tracker.mark_notified(task.id)
                logger.info(
                    f"[notifier] 已通知 user={line_user_id} task={task.id} "
                    f"current={current} user_number={user_num}"
                )
            except Exception as e:
                logger.error(f"[notifier] 推播失敗 task={task.id}: {e}")
