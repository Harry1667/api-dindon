"""API /api/progress 端點測試 — 驗證讀取快取行為

在 Docker 內執行：docker compose exec app python -m pytest tests/test_api_progress.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from httpx import AsyncClient, ASGITransport


def _make_progress_data():
    from app.schemas.clinic import ClinicProgressData
    return ClinicProgressData(
        hospital_code="test",
        hospital_name="測試醫院",
        date="2026/04/09",
        session="上午診",
        department="內科",
        doctor_name="王大明",
        clinic_room="101診",
        current_number=30,
        next_number=31,
        is_current_skipped=False,
        is_next_skipped=False,
        fetched_at=datetime(2026, 4, 9, 9, 30),
    )


@pytest.fixture
def test_app(mock_cache):
    """建立帶 mock cache、停用 auth 的 test app"""
    import app.middleware.auth as auth_mod
    auth_mod._API_TOKEN = ""
    from app.main import app
    app.state.cache = mock_cache
    return app


@pytest.mark.asyncio
async def test_progress_valid_hospital(test_app, mock_cache):
    """有效醫院代碼 → 200 + Redis 快取資料"""
    progress = _make_progress_data()
    mock_cache.get_all_progress = AsyncMock(return_value=[progress])
    mock_adapter = MagicMock()
    mock_adapter.hospital_name = "測試醫院"

    with patch("app.scrapers.registry.AdapterRegistry.get", return_value=mock_adapter):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
            resp = await c.get("/api/progress/test")

    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["data"][0]["department"] == "內科"


@pytest.mark.asyncio
async def test_progress_invalid_hospital(test_app):
    """無效醫院代碼 → 回傳 error"""
    with patch("app.scrapers.registry.AdapterRegistry.get", return_value=None), \
         patch("app.scrapers.registry.AdapterRegistry.get_all_codes", return_value=["ntuh"]):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
            resp = await c.get("/api/progress/xxx")

    assert "error" in resp.json()


@pytest.mark.asyncio
async def test_progress_empty_cache(test_app, mock_cache):
    """醫院存在但 Redis 沒資料 → 200 + 空列表"""
    mock_cache.get_all_progress = AsyncMock(return_value=[])
    mock_adapter = MagicMock()
    mock_adapter.hospital_name = "測試醫院"

    with patch("app.scrapers.registry.AdapterRegistry.get", return_value=mock_adapter):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as c:
            resp = await c.get("/api/progress/test")

    assert resp.status_code == 200
    assert resp.json()["count"] == 0
