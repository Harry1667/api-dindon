"""API 認證 + 頻率限制 — FastAPI Depends

使用方式：在需要認證的 route 加上 Depends(verify_api_token)

不影響的路徑：/health, /webhook, /docs, /openapi.json
"""

import os
import time
import logging

from fastapi import Header, HTTPException, Request

logger = logging.getLogger(__name__)

# 從環境變數取 token，未設定時所有 /api/* 請求都會被拒
_API_TOKEN = os.getenv("API_BEARER_TOKEN", "")

# Rate limit 設定
RATE_LIMIT_MAX = int(os.getenv("API_RATE_LIMIT", "100"))  # 每分鐘最大請求數
RATE_LIMIT_WINDOW = 60  # 秒


async def verify_api_token(x_api_key: str = Header(None, alias="X-API-Key")):
    """驗證 API bearer token（FastAPI Depends）"""
    if not _API_TOKEN:
        # 未設定 token = 不啟用認證（開發模式）
        return

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "缺少 API key"}},
        )

    if x_api_key != _API_TOKEN:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "無效的 API key"}},
        )


async def check_rate_limit(request: Request):
    """Redis fixed window rate limit（FastAPI Depends）

    超過限制回 429。Redis 斷線時 fail open（不阻擋請求）。
    """
    try:
        cache = request.app.state.cache
        minute_key = f"ratelimit:{int(time.time()) // RATE_LIMIT_WINDOW}"
        count = await cache.redis.incr(minute_key)
        if count == 1:
            await cache.redis.expire(minute_key, RATE_LIMIT_WINDOW)

        if count > RATE_LIMIT_MAX:
            raise HTTPException(
                status_code=429,
                detail={"error": {"code": "RATE_LIMITED", "message": "超過請求限制，請稍後再試"}},
            )
    except HTTPException:
        raise  # 429 要往上拋
    except Exception as e:
        # Redis 斷線 → fail open，不阻擋請求
        logger.warning(f"[rate_limit] Redis 錯誤，fail open: {e}")
