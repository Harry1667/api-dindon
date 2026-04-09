"""Rate limit 測試 — Redis fixed window counter

在 Docker 內執行：docker compose exec app python -m pytest tests/test_rate_limit.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture(autouse=True)
def disable_auth():
    """測試 rate limit 時停用 token 驗證"""
    import app.middleware.auth as auth_mod
    original = auth_mod._API_TOKEN
    auth_mod._API_TOKEN = ""
    yield
    auth_mod._API_TOKEN = original


@pytest.fixture
def test_app(mock_cache):
    from app.main import app
    app.state.cache = mock_cache
    return app


@pytest.mark.asyncio
async def test_under_limit_passes(test_app, mock_cache):
    """低於限制 → 正常通過"""
    mock_cache.redis.incr = AsyncMock(return_value=50)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        resp = await c.get("/api/hospitals")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_over_limit_429(test_app, mock_cache):
    """超過限制 → 429"""
    mock_cache.redis.incr = AsyncMock(return_value=101)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        resp = await c.get("/api/hospitals")
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_redis_down_fail_open(test_app, mock_cache):
    """Redis 斷線 → fail open，請求通過"""
    from redis.exceptions import ConnectionError
    mock_cache.redis.incr = AsyncMock(side_effect=ConnectionError("Redis 斷線"))

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        resp = await c.get("/api/hospitals")
    assert resp.status_code == 200
