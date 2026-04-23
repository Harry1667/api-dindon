"""Web Push API — PWA 訂閱與推送

Phase 1:用 Redis 暫存 subscription,key 格式:
  - push_sub:line:{line_user_id}    (LIFF 用戶,有 LINE ID)
  - push_sub:anon:{endpoint_hash}   (匿名用戶)

Phase 2 會搬到 devices 表。
"""

import asyncio
import hashlib
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/push", tags=["Web Push"])

# Redis key TTL:30 天(沒用就清掉)
SUB_TTL = 30 * 24 * 3600


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: PushKeys
    expirationTime: int | None = None


class SubscribeRequest(BaseModel):
    line_user_id: str | None = None
    guest_id: str | None = None
    subscription: PushSubscription
    user_agent: str | None = None
    platform: str | None = Field(None, description="ios/android/desktop")


class TestPushRequest(BaseModel):
    line_user_id: str | None = None
    guest_id: str | None = None
    endpoint_hash: str | None = None
    title: str = "叮咚到號"
    body: str = "測試通知 — 這是 PWA Web Push 測試"


def _endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()[:16]


def _sub_key(line_user_id: str | None, guest_id: str | None, endpoint: str) -> str:
    """優先級：line > guest > anon(hash)"""
    if line_user_id:
        return f"push_sub:line:{line_user_id}"
    if guest_id:
        return f"push_sub:guest:{guest_id}"
    return f"push_sub:anon:{_endpoint_hash(endpoint)}"


@router.get("/vapid-key")
async def get_vapid_public_key():
    """前端訂閱時需要 VAPID public key"""
    if not settings.vapid_public_key:
        raise HTTPException(status_code=500, detail="VAPID_PUBLIC_KEY 未設定")
    return {"public_key": settings.vapid_public_key}


@router.post("/subscribe")
async def subscribe(req: SubscribeRequest, request: Request):
    """前端訂閱 Web Push 後,把 subscription 存到 Redis"""
    cache = request.app.state.cache
    redis = cache.redis  # 共用 redis 連線

    key = _sub_key(req.line_user_id, req.guest_id, req.subscription.endpoint)
    payload = {
        "subscription": req.subscription.model_dump(),
        "line_user_id": req.line_user_id,
        "guest_id": req.guest_id,
        "user_agent": req.user_agent,
        "platform": req.platform,
    }
    await redis.set(key, json.dumps(payload), ex=SUB_TTL)

    logger.info(
        f"web push subscribed: key={key} platform={req.platform} "
        f"line_user_id={req.line_user_id} guest_id={req.guest_id}"
    )
    return {
        "status": "ok",
        "key": key,
        "endpoint_hash": _endpoint_hash(req.subscription.endpoint),
    }


@router.delete("/subscribe")
async def unsubscribe(req: SubscribeRequest, request: Request):
    """取消訂閱"""
    cache = request.app.state.cache
    redis = cache.redis
    key = _sub_key(req.line_user_id, req.guest_id, req.subscription.endpoint)
    await redis.delete(key)
    logger.info(f"web push unsubscribed: key={key}")
    return {"status": "ok"}


@router.post("/test")
async def send_test_push(req: TestPushRequest, request: Request):
    """測試發送一則 Web Push(管理用)"""
    cache = request.app.state.cache
    redis = cache.redis

    # 找 subscription
    if req.line_user_id:
        key = f"push_sub:line:{req.line_user_id}"
    elif req.guest_id:
        key = f"push_sub:guest:{req.guest_id}"
    elif req.endpoint_hash:
        key = f"push_sub:anon:{req.endpoint_hash}"
    else:
        raise HTTPException(
            status_code=400,
            detail="必須提供 line_user_id、guest_id 或 endpoint_hash",
        )

    raw = await redis.get(key)
    if not raw:
        raise HTTPException(status_code=404, detail=f"找不到訂閱: {key}")

    data = json.loads(raw)
    subscription = data["subscription"]

    payload = {
        "title": req.title,
        "body": req.body,
        "url": "/chat",
        "tag": "dindon-test",
    }

    try:
        await _send_web_push(subscription, payload)
    except Exception as e:
        logger.error(f"web push test failed: {e}", exc_info=True)
        # 410 Gone / 404 Not Found → subscription 已失效,清掉
        msg = str(e).lower()
        if "410" in msg or "404" in msg or "gone" in msg or "expired" in msg:
            await redis.delete(key)
            raise HTTPException(status_code=410, detail="訂閱已失效,已清除")
        raise HTTPException(status_code=500, detail=f"發送失敗: {e}")

    return {"status": "ok", "key": key}


async def _send_web_push(subscription: dict[str, Any], payload: dict[str, Any]) -> None:
    """發送 Web Push(用 pywebpush 包 asyncio.to_thread,因為 pywebpush 是 sync)

    Phase 4 會被 notifier router 呼叫。
    """
    from pywebpush import webpush, WebPushException

    def _do_send():
        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=300,  # 5 分鐘 TTL,過期推播服務丟棄
            )
        except WebPushException as e:
            # 重新 raise 以便上層判斷 status code
            status = getattr(e.response, "status_code", None) if e.response else None
            raise RuntimeError(f"pywebpush failed: status={status} detail={e}") from e

    await asyncio.to_thread(_do_send)


# 內部呼叫 helper(notifier / celery worker 用)
async def send_push_by_key(redis, key: str, payload: dict[str, Any]) -> bool:
    """對指定 Redis key 對應的訂閱發 Web Push。回傳是否成功。

    key 格式：push_sub:line:{line_user_id} 或 push_sub:guest:{guest_id}
    失敗且 410/404/Gone → 自動刪除過期訂閱
    """
    raw = await redis.get(key)
    if not raw:
        return False
    data = json.loads(raw)
    try:
        await _send_web_push(data["subscription"], payload)
        return True
    except Exception as e:
        logger.warning(f"send_push_by_key failed key={key}: {e}")
        msg = str(e).lower()
        if "410" in msg or "404" in msg or "gone" in msg:
            await redis.delete(key)
        return False


async def send_push_to_line_user(redis, line_user_id: str, payload: dict[str, Any]) -> bool:
    return await send_push_by_key(redis, f"push_sub:line:{line_user_id}", payload)


async def send_push_to_guest(redis, guest_id: str, payload: dict[str, Any]) -> bool:
    return await send_push_by_key(redis, f"push_sub:guest:{guest_id}", payload)
