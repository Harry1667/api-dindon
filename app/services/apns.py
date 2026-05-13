"""APNs (Apple Push Notification service) 推播

採用 Token-based Auth（.p8 金鑰），JWT 簽 ES256，HTTP/2 連 api.push.apple.com。

設計要點：
- JWT 快取 50 分鐘（Apple 規定 ≤60 分），避免每次推播重簽
- 410 Gone → 自動把該 device token 從 tracking_tasks 清空（並標 cancelled）
- 任何錯誤都吞掉、寫 log，不影響 LINE 推送主流程
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Apple 規定 JWT 有效期 ≤ 60 分鐘，我們留 10 分鐘 buffer
_JWT_TTL = 50 * 60

# 換行符在 .env 多行字串裡常以 \n 字面存在，runtime 還原
def _normalize_pem(raw: str) -> str:
    if not raw:
        return ""
    if "\\n" in raw and "\n" not in raw:
        return raw.replace("\\n", "\n")
    return raw


@dataclass
class _JwtCache:
    token: str = ""
    issued_at: float = 0.0

    def is_valid(self) -> bool:
        return bool(self.token) and (time.time() - self.issued_at) < _JWT_TTL


_jwt_cache = _JwtCache()
_jwt_lock = threading.Lock()


def _make_apns_jwt() -> str:
    """產生 APNs JWT。失敗會 raise；上層用 try/except 包住。"""
    import jwt  # PyJWT

    key_id = settings.apns_key_id
    team_id = settings.apns_team_id
    private_key = _normalize_pem(settings.apns_private_key)

    if not (key_id and team_id and private_key):
        raise RuntimeError("APNs 環境變數不完整 (APNS_KEY_ID/APNS_TEAM_ID/APNS_PRIVATE_KEY)")

    payload = {"iss": team_id, "iat": int(time.time())}
    headers = {"alg": "ES256", "kid": key_id}
    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


def _get_jwt() -> str:
    if _jwt_cache.is_valid():
        return _jwt_cache.token
    with _jwt_lock:
        if _jwt_cache.is_valid():
            return _jwt_cache.token
        token = _make_apns_jwt()
        _jwt_cache.token = token
        _jwt_cache.issued_at = time.time()
        return token


def is_configured() -> bool:
    """是否已設定 APNs 環境變數（沒設就靜默 skip）"""
    return bool(
        settings.apns_key_id
        and settings.apns_team_id
        and settings.apns_bundle_id
        and settings.apns_private_key
    )


async def send_apns(
    device_token: str,
    title: str,
    body: str,
    data: dict | None = None,
    *,
    on_invalid_token=None,
) -> bool:
    """發送 APNs 推播。

    Args:
        device_token: iOS device token (hex)
        title, body: 通知標題與內容
        data: 額外要塞進 payload 的 key/value（會與 aps 同層）
        on_invalid_token: callable(token: str) → 收到 400 BadDeviceToken / 410 Unregistered
                          時呼叫，給上層清 DB。可為 async 或 sync。

    Returns:
        True if 200 OK；False 表示失敗（已記 log）。
    """
    if not device_token:
        return False
    if not is_configured():
        logger.debug("[apns] 未設定，跳過推送")
        return False

    host = "api.sandbox.push.apple.com" if settings.apns_use_sandbox else "api.push.apple.com"
    url = f"https://{host}/3/device/{device_token}"

    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        }
    }
    if data:
        # data 不可覆蓋 aps
        for k, v in data.items():
            if k == "aps":
                continue
            payload[k] = v

    try:
        jwt_token = _get_jwt()
    except Exception as e:
        logger.error(f"[apns] JWT 簽發失敗: {e}")
        return False

    headers = {
        "authorization": f"bearer {jwt_token}",
        "apns-topic": settings.apns_bundle_id,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }

    try:
        async with httpx.AsyncClient(http2=True, timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except Exception as e:
        logger.error(f"[apns] 請求失敗 token={device_token[:8]}…: {e}")
        return False

    if resp.status_code == 200:
        return True

    # 解析錯誤
    try:
        err_reason = resp.json().get("reason", "")
    except Exception:
        err_reason = resp.text[:200]

    # 400 BadDeviceToken / 410 Unregistered → token 失效
    invalid_reasons = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}
    is_invalid = (resp.status_code == 410) or (
        resp.status_code == 400 and err_reason in invalid_reasons
    )

    if is_invalid:
        logger.warning(f"[apns] device token 失效 ({err_reason}) token={device_token[:8]}…")
        if on_invalid_token:
            try:
                result = on_invalid_token(device_token)
                if hasattr(result, "__await__"):
                    await result
            except Exception as cb_err:
                logger.error(f"[apns] on_invalid_token callback 失敗: {cb_err}")
    else:
        logger.error(
            f"[apns] 推送失敗 status={resp.status_code} reason={err_reason} token={device_token[:8]}…"
        )

    return False


async def clear_invalid_token(device_token: str) -> None:
    """把失效的 token 從所有 tracking_tasks 清空（同 token 可能對應多任務）"""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.models.tracking_task import TrackingTask

    eng = create_async_engine(settings.database_url, echo=False)
    sf = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sf() as session:
            await session.execute(
                update(TrackingTask)
                .where(TrackingTask.apns_token == device_token)
                .values(apns_token=None)
            )
            await session.commit()
    finally:
        await eng.dispose()
