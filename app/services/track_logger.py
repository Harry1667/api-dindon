"""追蹤對話記錄器 — 用 Redis 暫存，結束時寫入 DB"""

import json
import logging
from datetime import datetime, timezone, timedelta

import redis as sync_redis

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))
LOG_TTL = 86400  # 24 小時過期


def _get_redis():
    import os
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return sync_redis.from_url(url, decode_responses=True)


def _key(task_id: int) -> str:
    return f"track_log:{task_id}"


def log_message(task_id: int, role: str, message: str):
    """記錄一則訊息

    role: "user" / "system" / "notify"
    """
    try:
        r = _get_redis()
        entry = {
            "time": datetime.now(TW_TZ).strftime("%H:%M:%S"),
            "role": role,
            "message": message[:500],  # 截斷避免太長
        }
        r.rpush(_key(task_id), json.dumps(entry, ensure_ascii=False))
        r.expire(_key(task_id), LOG_TTL)
    except Exception as e:
        logger.debug(f"track_log write failed: {e}")


def get_log(task_id: int) -> str:
    """取得對話記錄 JSON string"""
    try:
        r = _get_redis()
        entries = r.lrange(_key(task_id), 0, -1)
        if not entries:
            return "[]"
        return json.dumps(
            [json.loads(e) for e in entries],
            ensure_ascii=False,
        )
    except Exception:
        return "[]"


def clear_log(task_id: int):
    """清除對話記錄"""
    try:
        r = _get_redis()
        r.delete(_key(task_id))
    except Exception:
        pass
