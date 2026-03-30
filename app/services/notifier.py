"""通知推播服務 — 比對追蹤任務並推播 LINE 通知

通知模式：
  - normal：每次號碼變動都提醒
  - light：剩 10、5、3、1、0 號時提醒（預設）
  - final：只在剩 3 號內提醒

過號處理：
  - 醫院端過號（is_current_skipped）：醫院叫號但病人未到，僅提示不結束追蹤
  - 號碼已過（current > user_num）：目前號碼超過用戶號碼，提示過號但不結束
  - 輪到了（current == user_num 且未過號）：通知到號並結束追蹤
"""

import logging

from app.services.cache import CacheService
from app.services.tracker import TrackerService
from app.services.line_bot import LineBotService
from app.models.tracking_task import NotifyMode, LIGHT_NOTIFY_POINTS

logger = logging.getLogger(__name__)

MODE_LABELS = {
    NotifyMode.NORMAL.value: "📢",
    NotifyMode.LIGHT.value: "🔔",
    NotifyMode.FINAL.value: "🔕",
}


class NotifierService:
    """比對追蹤任務與即時進度，觸發推播"""

    def __init__(self, session_factory=None):
        self.cache = CacheService()
        self.tracker = TrackerService(session_factory=session_factory)
        self.line_bot = LineBotService()

    async def check_and_notify(self):
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
        results = await self.cache.search_progress(
            hospital_code=task.hospital_code,
            department=task.department if task.department else None,
            doctor_name=task.doctor_name,
            clinic_room=task.clinic_room,
        )

        if not results:
            return

        # 有指定時段時，只匹配對應時段
        if task.session:
            results = [r for r in results if r.session == task.session]
            if not results:
                return

        progress = results[0]
        current = progress.current_number
        user_num = task.user_number
        remaining = max(0, user_num - current)
        last_remaining = task.last_notified_remaining
        mode = task.notify_mode or NotifyMode.LIGHT.value
        header = (
            f"{progress.hospital_name}-{progress.department} "
            f"{progress.doctor_name} {progress.clinic_room}"
        )

        # ========== 過號情境 ==========

        # 情境 A：醫院端標記「過號」且正好是用戶的號碼附近
        # is_current_skipped = 目前叫到的號碼被標記過號
        if progress.is_current_skipped and current == user_num:
            # 用戶的號碼被叫到但標記過號 → 可能是用戶沒到
            message = (
                f"⚠️ 您的號碼 {user_num} 號已被叫到但標記過號！\n"
                f"{header}\n"
                f"請儘速前往診間報到，告知護理站您已到\n"
                f"（大多數醫院可重新安排看診順序）"
            )
            await self._send(task, line_user_id, message, remaining)
            return

        # 情境 B：號碼已過（目前看診號 > 用戶號碼）
        if current > user_num:
            # 只通知一次，避免重複轟炸
            if last_remaining is not None and last_remaining <= 0:
                return  # 已經通知過過號了
            message = (
                f"⚠️ 您的號碼可能已過號\n"
                f"{header}\n"
                f"目前看到第 {current} 號，您是第 {user_num} 號\n"
                f"請前往診間確認，告知護理站您已到"
            )
            # 記錄 remaining=0 表示已通知過號，但不結束追蹤
            await self._send(task, line_user_id, message, remaining=0)
            return

        # ========== 到號情境 ==========

        # 輪到了
        if current >= user_num:
            message = (
                f"🔔 輪到您了！\n"
                f"{header}\n"
                f"目前已看到第 {current} 號，您是第 {user_num} 號\n"
                f"請儘速前往診間！"
            )
            await self._send_and_finish(task, line_user_id, message)
            return

        # ========== 一般提醒 ==========

        should_notify = self._should_notify(mode, remaining, last_remaining)

        if not should_notify:
            return

        icon = MODE_LABELS.get(mode, "🔔")
        message = (
            f"{icon} 看診進度更新\n"
            f"{header}\n"
            f"目前看到第 {current} 號，您是第 {user_num} 號\n"
            f"還有約 {remaining} 位"
        )

        await self._send(task, line_user_id, message, remaining)

    def _should_notify(self, mode: str, remaining: int, last_remaining: int | None) -> bool:
        if mode == NotifyMode.NORMAL.value:
            if last_remaining is None:
                return remaining <= 10
            return remaining != last_remaining

        elif mode == NotifyMode.LIGHT.value:
            for point in LIGHT_NOTIFY_POINTS:
                if remaining <= point:
                    if last_remaining is None or last_remaining > point:
                        return True
                    break
            return False

        elif mode == NotifyMode.FINAL.value:
            if remaining > 3:
                return False
            if last_remaining is None or last_remaining > 3:
                return True
            return remaining != last_remaining and remaining <= 1

        return False

    async def _send(self, task, line_user_id: str, message: str, remaining: int):
        """發送通知，更新剩餘數，但不結束追蹤"""
        try:
            await self.line_bot.push_message(line_user_id, message)
            await self.tracker.update_last_remaining(task.id, remaining)
            logger.info(
                f"[notifier] 已通知 user={line_user_id} task={task.id} remaining={remaining}"
            )
        except Exception as e:
            logger.error(f"[notifier] 推播失敗 task={task.id}: {e}")

    async def _send_and_finish(self, task, line_user_id: str, message: str):
        """發送通知並標記完成"""
        try:
            await self.line_bot.push_message(line_user_id, message)
            await self.tracker.mark_notified(task.id)
            logger.info(f"[notifier] 已通知(結束) task={task.id}")
        except Exception as e:
            logger.error(f"[notifier] 推播失敗 task={task.id}: {e}")
