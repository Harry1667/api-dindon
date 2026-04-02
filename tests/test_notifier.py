"""通知服務測試 — 1-push 模式核心邏輯驗證"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.notifier import NotifierService


class TestShouldNotify:
    """測試 1-push 通知觸發條件（threshold-based）"""

    def setup_method(self):
        self.svc = NotifierService.__new__(NotifierService)

    # ========== 首次檢查（last_remaining=None）==========

    def test_first_check_within_threshold_triggers(self):
        """首次檢查，已在門檻內（如差 2 號，門檻 3）→ 立即通知"""
        assert self.svc._should_notify(threshold=3, remaining=2, last_remaining=None) is True

    def test_first_check_at_threshold_triggers(self):
        """首次檢查，剛好在門檻上（差 3 號，門檻 3）→ 通知"""
        assert self.svc._should_notify(threshold=3, remaining=3, last_remaining=None) is True

    def test_first_check_beyond_threshold_no_trigger(self):
        """首次檢查，還沒到門檻（差 10 號，門檻 3）→ 不通知"""
        assert self.svc._should_notify(threshold=3, remaining=10, last_remaining=None) is False

    # ========== 門檻穿越（正常情境）==========

    def test_crosses_threshold_triggers(self):
        """從門檻外穿越到門檻內 → 通知"""
        assert self.svc._should_notify(threshold=5, remaining=4, last_remaining=6) is True

    def test_at_threshold_from_above_triggers(self):
        """從門檻外到達門檻值 → 通知"""
        assert self.svc._should_notify(threshold=5, remaining=5, last_remaining=6) is True

    def test_already_below_threshold_no_retrigger(self):
        """已經在門檻內，號碼繼續下降 → 不重複通知"""
        assert self.svc._should_notify(threshold=5, remaining=3, last_remaining=4) is False

    def test_still_above_threshold_no_trigger(self):
        """還在門檻外 → 不通知"""
        assert self.svc._should_notify(threshold=5, remaining=8, last_remaining=10) is False

    # ========== 邊界情況 ==========

    def test_threshold_1_triggers_at_1(self):
        """門檻 1：差 1 號時通知"""
        assert self.svc._should_notify(threshold=1, remaining=1, last_remaining=2) is True

    def test_threshold_1_no_trigger_at_2(self):
        """門檻 1：差 2 號時不通知"""
        assert self.svc._should_notify(threshold=1, remaining=2, last_remaining=3) is False

    def test_large_threshold_triggers(self):
        """大門檻（30）：差 30 號時通知"""
        assert self.svc._should_notify(threshold=30, remaining=29, last_remaining=31) is True

    def test_remaining_zero_after_threshold_no_retrigger(self):
        """到號了（remaining=0）但已經通知過 → 不重複"""
        assert self.svc._should_notify(threshold=3, remaining=0, last_remaining=2) is False

    # ========== 號碼跳過門檻 ==========

    def test_skip_past_threshold_triggers(self):
        """號碼跳過門檻（如 7→1，門檻 5）→ 通知"""
        assert self.svc._should_notify(threshold=5, remaining=1, last_remaining=7) is True


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
