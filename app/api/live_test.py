"""即時追蹤測試 — 用假用戶追蹤真實醫師，驗證完整通知鏈路"""

import json
import time
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/admin", tags=["live-test"])

TW_TZ = timezone(timedelta(hours=8))
logger = logging.getLogger(__name__)

# 即時測試記錄存 Redis
LIVE_TEST_KEY = "test:live"


def _check_auth(token):
    from app.api.admin import _check_auth as check
    return check(token)


@router.get("/api/test/live")
async def api_get_live_test(admin_token: str | None = Cookie(None)):
    """取得即時測試狀態"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    import redis as sync_redis
    import os
    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    data = r.get(LIVE_TEST_KEY)
    if data:
        return json.loads(data)
    return {"status": "idle", "tasks": []}


@router.post("/api/test/live/start")
async def api_start_live_test(request: Request, admin_token: str | None = Cookie(None)):
    """啟動即時追蹤測試"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    count = min(body.get("count", 5), 20)
    offset = body.get("offset", 3)  # 掛在目前號碼 +N
    notify_mode = body.get("notify_mode", "normal")

    import redis as sync_redis
    import os
    from app.scrapers.registry import AdapterRegistry

    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    # 找正在看診的醫師
    candidates = []
    for k in r.keys("progress:*"):
        val = r.get(k)
        if not val:
            continue
        d = json.loads(val)
        cur = d.get("current_number", 0)
        if cur > 3:
            candidates.append(d)

    if not candidates:
        return {"error": "目前沒有正在看診的醫師"}

    # 隨機挑選不同醫院的醫師
    import random
    random.shuffle(candidates)
    selected = []
    seen_hospitals = set()
    for c in candidates:
        if len(selected) >= count:
            break
        key = f"{c['hospital_code']}:{c['department']}:{c['doctor_name']}"
        if key not in seen_hospitals:
            seen_hospitals.add(key)
            selected.append(c)

    # 建立追蹤任務
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.services.tracker import TrackerService
    from app.config import settings

    eng = create_async_engine(settings.database_url, echo=False, pool_size=2)
    sess = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    tracker = TrackerService(session_factory=sess)

    tasks_info = []
    now = datetime.now(TW_TZ)

    for c in selected:
        user_id = f"__live_test_{int(time.time())}_{len(tasks_info)}"
        user_number = c["current_number"] + offset
        adapter = AdapterRegistry.get(c["hospital_code"])
        hosp_name = adapter.hospital_name if adapter else c["hospital_code"]

        try:
            task = await tracker.create_task(
                line_user_id=user_id,
                hospital_code=c["hospital_code"],
                department=c["department"],
                doctor_name=c["doctor_name"],
                clinic_room=c["clinic_room"],
                user_number=user_number,
                notify_mode=notify_mode,
                session_time=c.get("session"),
            )

            tasks_info.append({
                "task_id": task.id,
                "user_id": user_id,
                "hospital": hosp_name,
                "department": c["department"],
                "doctor": c["doctor_name"],
                "room": c["clinic_room"],
                "session": c.get("session", ""),
                "user_number": user_number,
                "start_current": c["current_number"],
                "notify_mode": notify_mode,
                "status": "ACTIVE",
                "notifications": [],
                "created_at": now.strftime("%H:%M:%S"),
            })
        except Exception as e:
            logger.error(f"[live_test] 建立任務失敗: {e}")

    await eng.dispose()

    # 存測試狀態到 Redis
    test_state = {
        "status": "running",
        "started_at": now.strftime("%m/%d %H:%M:%S"),
        "offset": offset,
        "notify_mode": notify_mode,
        "tasks": tasks_info,
    }
    r.set(LIVE_TEST_KEY, json.dumps(test_state, ensure_ascii=False), ex=7200)  # 2 小時

    return test_state


@router.post("/api/test/live/check")
async def api_check_live_test(admin_token: str | None = Cookie(None)):
    """檢查即時測試的追蹤任務狀態"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    import redis as sync_redis
    import os
    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    data = r.get(LIVE_TEST_KEY)
    if not data:
        return {"status": "idle", "tasks": []}

    test_state = json.loads(data)
    if test_state["status"] != "running":
        return test_state

    # 從 DB 查每個任務的最新狀態
    import pymysql
    from app.config import settings
    conn = pymysql.connect(
        host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password,
        database=settings.mysql_database, cursorclass=pymysql.cursors.DictCursor,
    )
    cur = conn.cursor()

    # 從 Redis 查目前號碼
    now = datetime.now(TW_TZ)
    all_done = True

    for t in test_state["tasks"]:
        # DB 狀態
        cur.execute(
            "SELECT status, notified_at, last_notified_remaining FROM tracking_tasks WHERE id=%s",
            (t["task_id"],)
        )
        row = cur.fetchone()
        if row:
            t["status"] = row["status"]
            if row["notified_at"]:
                t["notified_at"] = row["notified_at"].strftime("%H:%M:%S")
            t["last_remaining"] = row["last_notified_remaining"]

        # Redis 目前號碼
        keys = r.keys(f"progress:{t.get('hospital_code', '')}:*{t['doctor']}*")
        if not keys:
            # 嘗試用醫院名反查 code
            from demo_chat import HOSPITAL_ALIASES
            h_code = None
            for alias, (code, name) in HOSPITAL_ALIASES.items():
                if name == t["hospital"]:
                    h_code = code
                    break
            if h_code:
                keys = r.keys(f"progress:{h_code}:*{t['doctor']}*")

        if keys:
            d = json.loads(r.get(keys[0]))
            t["current_now"] = d["current_number"]
            t["remaining"] = max(0, t["user_number"] - d["current_number"])
        else:
            t["current_now"] = "N/A"
            t["remaining"] = "?"

        if t["status"] == "ACTIVE":
            all_done = False

    conn.close()

    if all_done:
        test_state["status"] = "completed"
        test_state["completed_at"] = now.strftime("%H:%M:%S")

    r.set(LIVE_TEST_KEY, json.dumps(test_state, ensure_ascii=False), ex=7200)
    return test_state


@router.post("/api/test/live/stop")
async def api_stop_live_test(admin_token: str | None = Cookie(None)):
    """停止即時測試，取消所有追蹤"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    import redis as sync_redis
    import os, pymysql
    from app.config import settings

    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    data = r.get(LIVE_TEST_KEY)
    if not data:
        return {"ok": True}

    test_state = json.loads(data)

    # 取消所有測試追蹤
    conn = pymysql.connect(
        host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password,
        database=settings.mysql_database,
    )
    cur = conn.cursor()
    for t in test_state.get("tasks", []):
        cur.execute("UPDATE tracking_tasks SET status='CANCELLED' WHERE id=%s AND status='ACTIVE'", (t["task_id"],))
    # 清理測試用戶
    cur.execute("DELETE FROM tracking_tasks WHERE user_id IN (SELECT id FROM users WHERE line_user_id LIKE '__live_test_%%')")
    cur.execute("DELETE FROM users WHERE line_user_id LIKE '__live_test_%%'")
    conn.commit()
    conn.close()

    test_state["status"] = "stopped"
    test_state["stopped_at"] = datetime.now(TW_TZ).strftime("%H:%M:%S")
    r.set(LIVE_TEST_KEY, json.dumps(test_state, ensure_ascii=False), ex=3600)

    return {"ok": True, "cancelled": len(test_state.get("tasks", []))}
