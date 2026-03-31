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
from app.models.tracking_feedback import TrackingFeedback
from app.services.track_logger import log_message as track_log, get_log, clear_log

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

        from datetime import datetime, timedelta
        now = datetime.utcnow()

        for task, line_user_id in active_tasks:
            try:
                # 預約追蹤超過 12 小時沒配到資料 → 自動提醒
                if (task.last_notified_remaining is None
                        and task.created_at
                        and now - task.created_at > timedelta(hours=12)):
                    from app.scrapers.registry import AdapterRegistry
                    adapter = AdapterRegistry.get(task.hospital_code)
                    hosp_name = adapter.hospital_name if adapter else task.hospital_code
                    desc = f"{hosp_name} {task.department or ''} {task.doctor_name or ''}".strip()
                    session_info = f"（{task.session}）" if task.session else ""
                    message = (
                        f"ℹ️ 預約追蹤提醒\n"
                        f"{desc}{session_info}\n"
                        f"已超過 12 小時未偵測到看診資料\n"
                        f"請確認醫師是否有排診\n\n"
                        f"輸入 t 查看追蹤 ｜ 輸入 c 取消"
                    )
                    await self._send_and_finish(task, line_user_id, message, "timeout")
                    continue

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
            # 有指定時段，再試不限時段
            if task.session:
                results = await self.cache.search_progress(
                    hospital_code=task.hospital_code,
                    department=task.department if task.department else None,
                    doctor_name=task.doctor_name,
                    clinic_room=task.clinic_room,
                )

        # 有指定時段時，只匹配對應時段
        if results and task.session:
            results = [r for r in results if r.session == task.session]

        if not results:
            # 之前有資料現在沒了 → 醫生可能停診了
            if task.last_notified_remaining is not None:
                from app.scrapers.registry import AdapterRegistry
                adapter = AdapterRegistry.get(task.hospital_code)
                hosp_name = adapter.hospital_name if adapter else task.hospital_code
                desc = f"{hosp_name} {task.department or ''} {task.doctor_name or ''} {task.clinic_room or ''}".strip()
                message = (
                    f"ℹ️ 看診進度已無資料\n"
                    f"{desc}\n"
                    f"醫師可能已結束看診或系統更新中\n\n"
                    f"輸入 t 查看追蹤 ｜ 輸入 c 取消追蹤"
                )
                await self._send_and_finish(task, line_user_id, message, "doctor_gone")
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
                # 過號超過 30 分鐘 → 自動停止追蹤
                from datetime import datetime, timedelta
                if (task.updated_at and
                        datetime.utcnow() - task.updated_at > timedelta(minutes=30)):
                    message = (
                        f"ℹ️ 過號超過 30 分鐘，自動停止追蹤\n"
                        f"{header}\n"
                        f"如需繼續追蹤，請重新輸入醫院名稱查詢"
                    )
                    await self._send_and_finish(task, line_user_id, message, "passed")
                return
            message = (
                f"⚠️ 您的號碼可能已過號\n"
                f"{header}\n"
                f"目前看到第 {current} 號，您是第 {user_num} 號\n"
                f"請前往診間確認，告知護理站您已到\n\n"
                f"輸入 c 取消追蹤（30 分鐘後自動停止）"
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
            await self._send_and_finish(task, line_user_id, message, "arrived")
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
                return True  # 首次一定通知（讓用戶知道系統在追蹤）
            return remaining != last_remaining

        elif mode == NotifyMode.LIGHT.value:
            if last_remaining is None:
                return True  # 首次一定通知
            for point in LIGHT_NOTIFY_POINTS:
                if remaining <= point:
                    if last_remaining > point:
                        return True
                    break
            return False

        elif mode == NotifyMode.FINAL.value:
            if last_remaining is None:
                return True  # 首次一定通知
            if remaining > 3:
                return False
            if last_remaining > 3:
                return True
            return remaining != last_remaining and remaining <= 1

        return False

    async def _send(self, task, line_user_id: str, message: str, remaining: int):
        """發送通知，更新剩餘數，但不結束追蹤

        原子性保證：先推播成功，才更新 DB。推播失敗時不更新狀態，
        下次 check cycle 會重新觸發通知。
        """
        track_log(task.id, "notify", message[:300])
        try:
            await self.line_bot.push_message(line_user_id, message)
        except Exception as e:
            logger.error(f"[notifier] 推播失敗 task={task.id}: {e}")
            return  # 推播失敗，不更新 DB，下次重試
        try:
            await self.tracker.update_last_remaining(task.id, remaining)
        except Exception as e:
            logger.error(f"[notifier] 更新剩餘數失敗 task={task.id}: {e}")
        logger.info(
            f"[notifier] 已通知 user={line_user_id} task={task.id} remaining={remaining}"
        )

    async def _send_and_finish(self, task, line_user_id: str, message: str, end_reason: str = "arrived"):
        """發送通知、標記完成、建立回饋記錄、詢問用戶

        原子性保證：先推播成功，才標記完成。推播失敗時不改 DB，
        下次 check cycle 會重新嘗試通知。
        """
        track_log(task.id, "notify", message[:300])
        # Step 1: 先推播，失敗就不改 DB
        try:
            await self.line_bot.push_message(line_user_id, message)
        except Exception as e:
            logger.error(f"[notifier] 推播失敗 task={task.id}: {e}")
            return  # 推播失敗，不標記完成，下次重試
        # Step 2: 推播成功，標記完成
        try:
            await self.tracker.mark_notified(task.id)
        except Exception as e:
            logger.error(f"[notifier] 標記完成失敗 task={task.id}: {e}")
        # Step 3: 建立回饋（非關鍵，失敗不影響主流程）
        feedback_id = await self._create_feedback(task, line_user_id, message, end_reason)
        if feedback_id:
            try:
                await self.line_bot.push_message(line_user_id, (
                    f"📋 追蹤結束，通知是否正確？\n\n"
                    f"  0 — ✅ 正確\n"
                    f"  1 — ❌ 有誤\n\n"
                    f"（回覆 0 或 1，幫助我們改善）"
                ))
                from demo_chat import _conversations
                _conversations[line_user_id] = {
                    "state": "waiting_feedback",
                    "feedback_id": feedback_id,
                }
            except Exception as e:
                logger.error(f"[notifier] 回饋推播失敗 task={task.id}: {e}")
        logger.info(f"[notifier] 已通知(結束) task={task.id} reason={end_reason} feedback={feedback_id}")

    async def _create_feedback(self, task, line_user_id: str, message: str, end_reason: str) -> int | None:
        """建立回饋記錄，包含完整追蹤過程資訊"""
        try:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
            from app.config import settings
            from app.scrapers.registry import AdapterRegistry

            eng = create_async_engine(settings.database_url, echo=False)
            sess = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)

            # 取得結束時的看診號碼
            results = await self.cache.search_progress(
                hospital_code=task.hospital_code,
                department=task.department if task.department else None,
                doctor_name=task.doctor_name,
                clinic_room=task.clinic_room,
            )
            final_current = results[0].current_number if results else 0

            # 醫院名稱
            adapter = AdapterRegistry.get(task.hospital_code)
            hosp_name = adapter.hospital_name if adapter else task.hospital_code

            # 計算通知次數（從 last_notified_remaining 推算）
            notify_count = 0
            if task.last_notified_remaining is not None:
                notify_count = max(1, (task.threshold or 5) - (task.last_notified_remaining or 0))

            # 取得對話記錄
            conv_log = get_log(task.id)

            async with sess() as session:
                fb = TrackingFeedback(
                    task_id=task.id,
                    line_user_id=line_user_id,
                    hospital_code=task.hospital_code,
                    hospital_name=hosp_name,
                    department=task.department or "",
                    doctor_name=task.doctor_name or "",
                    clinic_room=task.clinic_room or "",
                    session=task.session or "",
                    user_number=task.user_number,
                    notify_mode=task.notify_mode or "light",
                    track_created_at=task.created_at,
                    start_current=None,
                    final_current=final_current,
                    notify_count=notify_count,
                    final_message=message,
                    end_reason=end_reason,
                    conversation_log=conv_log,
                )
                session.add(fb)
                await session.commit()
                await session.refresh(fb)
                feedback_id = fb.id

            await eng.dispose()
            clear_log(task.id)
            return feedback_id
        except Exception as e:
            logger.error(f"[notifier] 建立回饋失敗: {e}")
            return None
