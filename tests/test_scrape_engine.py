"""scrape.py 共用 engine 測試 — 驗證連線不再洩漏

在 Docker 內執行：docker compose exec app python -m pytest tests/test_scrape_engine.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_shared_engine_one_cycle():
    """一個 scrape cycle 只建一個 DB engine（不是 30 個）"""
    engine_count = 0

    def counting_create(*args, **kwargs):
        nonlocal engine_count
        engine_count += 1
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        return mock_engine

    adapter1 = MagicMock()
    adapter1.hospital_name = "醫院A"
    adapter1.fetch_all_progress = AsyncMock(return_value=[])

    adapter2 = MagicMock()
    adapter2.hospital_name = "醫院B"
    adapter2.fetch_all_progress = AsyncMock(return_value=[])

    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value="0")
    mock_redis.close = MagicMock()

    mock_cache = MagicMock()
    mock_cache.close = AsyncMock()

    with patch("app.tasks.scrape.create_async_engine", side_effect=counting_create), \
         patch("app.tasks.scrape.async_sessionmaker", return_value=MagicMock()), \
         patch("app.tasks.scrape.AdapterRegistry.get_all", return_value={"a": adapter1, "b": adapter2}), \
         patch("app.tasks.scrape._get_redis", return_value=mock_redis), \
         patch("app.tasks.scrape.CacheService", return_value=mock_cache):

        from app.tasks.scrape import _scrape_all
        await _scrape_all()

    assert engine_count == 1


@pytest.mark.asyncio
async def test_engine_dispose_on_error():
    """即使爬蟲拋 exception，engine 也會被 dispose"""
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    adapter = MagicMock()
    adapter.hospital_name = "炸裂醫院"
    adapter.fetch_all_progress = AsyncMock(side_effect=RuntimeError("boom"))

    mock_redis = MagicMock()
    mock_redis.get = MagicMock(return_value="0")
    mock_redis.close = MagicMock()

    mock_cache = MagicMock()
    mock_cache.close = AsyncMock()

    with patch("app.tasks.scrape.create_async_engine", return_value=mock_engine), \
         patch("app.tasks.scrape.async_sessionmaker", return_value=MagicMock()), \
         patch("app.tasks.scrape.AdapterRegistry.get_all", return_value={"x": adapter}), \
         patch("app.tasks.scrape._get_redis", return_value=mock_redis), \
         patch("app.tasks.scrape.CacheService", return_value=mock_cache), \
         patch("app.tasks.scrape._check_and_alert_failure", new_callable=AsyncMock):

        from app.tasks.scrape import _scrape_all
        await _scrape_all()

    mock_engine.dispose.assert_awaited_once()
