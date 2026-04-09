"""API 認證測試 — bearer token 驗證

在 Docker 內執行：docker compose exec app python -m pytest tests/test_auth.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def test_app(mock_cache):
    from app.main import app
    app.state.cache = mock_cache
    return app


@pytest.mark.asyncio
async def test_no_token_401(test_app):
    """無 API key header → 401"""
    import app.middleware.auth as auth_mod
    auth_mod._API_TOKEN = "test-secret"

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        resp = await c.get("/api/hospitals")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_401(test_app):
    """錯誤 API key → 401"""
    import app.middleware.auth as auth_mod
    auth_mod._API_TOKEN = "correct-token"

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        resp = await c.get("/api/hospitals", headers={"X-API-Key": "wrong-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_correct_token_200(test_app):
    """正確 API key → 200"""
    import app.middleware.auth as auth_mod
    auth_mod._API_TOKEN = "correct-token"

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        resp = await c.get("/api/hospitals", headers={"X-API-Key": "correct-token"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_no_auth(test_app, mock_cache):
    """/health 不需要 API key"""
    import app.middleware.auth as auth_mod
    auth_mod._API_TOKEN = "some-token"

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        resp = await c.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_no_token_configured_passes(test_app):
    """未設定 API_BEARER_TOKEN → 所有請求通過（開發模式）"""
    import app.middleware.auth as auth_mod
    auth_mod._API_TOKEN = ""

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
        resp = await c.get("/api/hospitals")
    assert resp.status_code == 200
