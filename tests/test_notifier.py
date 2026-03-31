"""通知服務測試 — 核心邏輯驗證"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.notifier import NotifierService
from app.models.tracking_task import NotifyMode


class TestShouldNotify:
    """測試通知觸發條件"""

    def setup_method(self):
        self.svc = NotifierService.__new__(NotifierService)

    def test_normal_mode_first_notify_within_10(self):
        """NORMAL 模式：首次通知，剩 10 號內"""
        assert self.svc._should_notify("normal", remaining=5, last_remaining=None) is True

    def test_normal_mode_first_notify_beyond_10(self):
        """NORMAL 模式：首次通知，超過 10 號也通知（讓用戶知道系統在追蹤）"""
        assert self.svc._should_notify("normal", remaining=35, last_remaining=None) is True

    def test_normal_mode_number_changed(self):
        """NORMAL 模式：號碼變動"""
        assert self.svc._should_notify("normal", remaining=3, last_remaining=4) is True

    def test_normal_mode_number_same(self):
        """NORMAL 模式：號碼沒變"""
        assert self.svc._should_notify("normal", remaining=3, last_remaining=3) is False

    def test_light_mode_first_always_triggers(self):
        """LIGHT 模式：首次一定觸發"""
        assert self.svc._should_notify("light", remaining=50, last_remaining=None) is True

    def test_light_mode_triggers_at_10(self):
        """LIGHT 模式：剩 10 號時觸發"""
        assert self.svc._should_notify("light", remaining=10, last_remaining=50) is True

    def test_light_mode_triggers_at_5(self):
        """LIGHT 模式：剩 5 號時觸發（上次通知是在 > 10 號時）"""
        assert self.svc._should_notify("light", remaining=5, last_remaining=11) is True

    def test_light_mode_no_retrigger_at_5_after_10(self):
        """LIGHT 模式：已在 10 號通知過，剩 5 號時不重複觸發 10 號通知"""
        assert self.svc._should_notify("light", remaining=5, last_remaining=10) is False

    def test_light_mode_no_trigger_at_7(self):
        """LIGHT 模式：剩 7 號時不觸發"""
        assert self.svc._should_notify("light", remaining=7, last_remaining=10) is False

    def test_final_mode_first_always_triggers(self):
        """FINAL 模式：首次一定觸發"""
        assert self.svc._should_notify("final", remaining=50, last_remaining=None) is True

    def test_final_mode_triggers_at_3(self):
        """FINAL 模式：剩 3 號時觸發"""
        assert self.svc._should_notify("final", remaining=3, last_remaining=50) is True

    def test_final_mode_no_trigger_at_5_after_first(self):
        """FINAL 模式：首次通知後，剩 5 號不觸發"""
        assert self.svc._should_notify("final", remaining=5, last_remaining=35) is False


class TestNotifyAtomicity:
    """測試通知原子性 — 推播失敗時不更新 DB"""

    @pytest.mark.asyncio
    async def test_send_push_failure_no_db_update(self):
        """推播失敗時不應更新 last_remaining"""
        svc = NotifierService.__new__(NotifierService)
        svc.line_bot = MagicMock()
        svc.line_bot.push_message = AsyncMock(side_effect=Exception("LINE API 失敗"))
        svc.tracker = MagicMock()
        svc.tracker.update_last_remaining = AsyncMock()

        task = MagicMock()
        task.id = 1

        await svc._send(task, "user123", "test msg", remaining=5)

        # 推播失敗，DB 不應被更新
        svc.tracker.update_last_remaining.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_push_success_db_update(self):
        """推播成功時應更新 last_remaining"""
        svc = NotifierService.__new__(NotifierService)
        svc.line_bot = MagicMock()
        svc.line_bot.push_message = AsyncMock()
        svc.tracker = MagicMock()
        svc.tracker.update_last_remaining = AsyncMock()

        task = MagicMock()
        task.id = 1

        await svc._send(task, "user123", "test msg", remaining=5)

        svc.tracker.update_last_remaining.assert_called_once_with(1, 5)

    @pytest.mark.asyncio
    async def test_send_and_finish_push_failure_no_mark(self):
        """推播失敗時不應標記任務完成"""
        svc = NotifierService.__new__(NotifierService)
        svc.line_bot = MagicMock()
        svc.line_bot.push_message = AsyncMock(side_effect=Exception("LINE API 失敗"))
        svc.tracker = MagicMock()
        svc.tracker.mark_notified = AsyncMock()

        task = MagicMock()
        task.id = 1

        await svc._send_and_finish(task, "user123", "test msg", "arrived")

        svc.tracker.mark_notified.assert_not_called()
