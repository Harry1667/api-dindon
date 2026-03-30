"""測試基礎設定"""

import pytest


@pytest.fixture
def mock_cache():
    """模擬 CacheService"""
    from unittest.mock import AsyncMock, MagicMock
    cache = MagicMock()
    cache.search_progress = AsyncMock(return_value=[])
    cache.store_progress = AsyncMock()
    cache.is_healthy = AsyncMock(return_value=True)
    cache.close = AsyncMock()
    return cache


@pytest.fixture
def mock_line_bot():
    """模擬 LineBotService"""
    from unittest.mock import AsyncMock, MagicMock
    bot = MagicMock()
    bot.push_message = AsyncMock()
    bot.reply = AsyncMock()
    return bot


@pytest.fixture
def mock_tracker():
    """模擬 TrackerService"""
    from unittest.mock import AsyncMock, MagicMock
    tracker = MagicMock()
    tracker.get_all_active_tasks = AsyncMock(return_value=[])
    tracker.update_last_remaining = AsyncMock()
    tracker.mark_notified = AsyncMock()
    tracker.create_task = AsyncMock()
    return tracker
