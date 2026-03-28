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
        # 搜尋該任務對應的診間進度
        results = await self.cache.search_progress(
            hospital_code=task.hospital_code,
            department=task.department if task.department else None,
            doctor_name=task.doctor_name,
            clinic_room=task.clinic_room,
        )

        if not results:
            return

        progress = results[0]

        # 判斷是否該通知: 目前號碼 >= 用戶號碼 - 閾值
        if progress.current_number >= task.user_number - task.threshold:
            remaining = max(0, task.user_number - progress.current_number)

            if remaining > 0:
                message = (
                    f"🔔 您的看診號碼快到了！\n"
                    f"{progress.hospital_name}-{progress.department} "
                    f"{progress.doctor_name} {progress.clinic_room}\n"
                    f"目前看到第 {progress.current_number} 號，您是第 {task.user_number} 號\n"
                    f"預計還有約 {remaining} 位"
                )
            else:
                message = (
                    f"🔔 輪到您了！\n"
                    f"{progress.hospital_name}-{progress.department} "
                    f"{progress.doctor_name} {progress.clinic_room}\n"
                    f"目前已看到第 {progress.current_number} 號，您是第 {task.user_number} 號\n"
                    f"請儘速前往診間！"
                )

            try:
                await self.line_bot.push_message(line_user_id, message)
                await self.tracker.mark_notified(task.id)
                logger.info(
                    f"[notifier] 已通知 user={line_user_id} task={task.id} "
                    f"current={progress.current_number} user_number={task.user_number}"
                )
            except Exception as e:
                logger.error(f"[notifier] 推播失敗 task={task.id}: {e}")
