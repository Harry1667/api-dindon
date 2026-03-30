"""Redis 快取服務測試 — 錯誤處理驗證"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCacheErrorHandling:
    """測試 Redis 錯誤不會讓系統掛掉"""

    @pytest.mark.asyncio
    async def test_get_all_progress_redis_down(self):
        """Redis 斷線時 get_all_progress 回傳空列表"""
        from app.services.cache import CacheService
        from redis.exceptions import ConnectionError

        svc = CacheService.__new__(CacheService)
        svc.redis = MagicMock()
        svc.redis.smembers = AsyncMock(side_effect=ConnectionError("Redis 斷線"))

        result = await svc.get_all_progress("ntuh")
        assert result == []

    @pytest.mark.asyncio
    async def test_store_progress_redis_down(self):
        """Redis 斷線時 store_progress 不拋例外"""
        from app.services.cache import CacheService
        from redis.exceptions import ConnectionError

        svc = CacheService.__new__(CacheService)
        svc.redis = MagicMock()
        svc.redis.keys = AsyncMock(side_effect=ConnectionError("Redis 斷線"))

        # 不應拋出例外
        progress = MagicMock()
        progress.hospital_code = "ntuh"
        await svc.store_progress([progress])

    @pytest.mark.asyncio
    async def test_is_healthy_redis_up(self):
        """Redis 正常時回傳 True"""
        from app.services.cache import CacheService

        svc = CacheService.__new__(CacheService)
        svc.redis = MagicMock()
        svc.redis.ping = AsyncMock(return_value=True)

        assert await svc.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_redis_down(self):
        """Redis 斷線時回傳 False"""
        from app.services.cache import CacheService
        from redis.exceptions import ConnectionError

        svc = CacheService.__new__(CacheService)
        svc.redis = MagicMock()
        svc.redis.ping = AsyncMock(side_effect=ConnectionError())

        assert await svc.is_healthy() is False
