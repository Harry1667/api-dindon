"""系統測試 API — 模擬多用戶並發測試"""

import asyncio
import re
import time
import json
import logging
import random
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/admin", tags=["test"])

TW_TZ = timezone(timedelta(hours=8))
logger = logging.getLogger(__name__)

# 測試報告存 Redis
REPORTS_KEY = "test:reports"
MAX_REPORTS = 50


def _load_reports() -> list:
    import redis as sync_redis, os
    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    data = r.get(REPORTS_KEY)
    return json.loads(data) if data else []


def _save_report(report: dict):
    import redis as sync_redis, os
    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    reports = _load_reports()
    reports.append(report)
    # 只保留最近 MAX_REPORTS 筆（不含 results 詳細資料以省空間）
    if len(reports) > MAX_REPORTS:
        reports = reports[-MAX_REPORTS:]
    r.set(REPORTS_KEY, json.dumps(reports, ensure_ascii=False), ex=86400 * 7)  # 7 天


def _check_auth(token):
    from app.api.admin import _check_auth as check
    return check(token)


# ============================================================
# 測試劇本定義
# ============================================================

def _build_scenarios(hospitals: list[dict]) -> list[dict]:
    """根據目前有資料的醫院動態產生測試劇本"""
    scenarios = []

    # 1. 快捷指令測試
    scenarios.append({
        "name": "快捷指令",
        "steps": [
            ("h", ["使用說明"]),
            ("00", ["支援查詢的醫院"]),
            ("@", ["主選單"]),
        ],
    })

    for hosp in hospitals:
        code = hosp["code"]
        name = hosp["name"]
        depts = hosp["depts"]  # [{dept, doctors, count}]

        if not depts:
            continue

        # 2. 查詢醫院 → 選時段(如有) → 選科 → 看結果
        first_dept = depts[0]
        query_steps = [(name, [name, "哪科", "看診中", "時段"])]
        # 如果有多時段，需要先選時段
        sessions = list(set(r.get("session", "") for d in depts for r in d.get("rooms", []) if r.get("session")))
        # 選第一個選項（科別或時段）
        query_steps.append(("1", [first_dept["dept"], "哪科", "看診中"]))
        query_steps.append(("@", ["主選單"]))
        scenarios.append({"name": f"查詢 {name}", "steps": query_steps})

        # 3. 醫院+科別直接篩選
        if len(depts) > 1:
            dept2 = depts[1]
            scenarios.append({
                "name": f"{name} 篩選科別",
                "steps": [
                    (f"{name} {dept2['dept']}", [dept2["dept"], "看診進度", "哪科", "時段"]),
                    ("@", ["主選單"]),
                ],
            })

        # 4. 快速追蹤（只用標準診間格式：\d+診 或 診室\d+）
        standard_rooms = [
            r for d in depts for r in d.get("rooms", [])
            if re.match(r"^\d+診$", r["room"]) or re.match(r"^診室\d+$", r["room"])
        ]
        if standard_rooms:
            room = standard_rooms[0]
            scenarios.append({
                "name": f"{name} 快速追蹤",
                "steps": [
                    (f"{name} {room['room']} 999", ["快速追蹤", "提醒模式"]),
                    ("2", ["追蹤成功"]),
                    ("t", ["追蹤"]),
                    ("c", ["取消"]),
                ],
            })

        # 5. 預約追蹤
        if first_dept["doctors"]:
            doc = first_dept["doctors"][0]
            scenarios.append({
                "name": f"{name} 預約追蹤",
                "steps": [
                    ("p", ["預約追蹤"]),
                    (name, ["時段"]),
                    ("1", ["科別", "請輸入"]),
                    (first_dept["dept"], ["醫師", "請輸入"]),
                    (doc, ["號碼", "請輸入"]),
                    ("888", ["提醒模式"]),
                    ("2", ["追蹤成功"]),
                    ("t", ["追蹤"]),
                    ("c", ["取消"]),
                ],
            })

    # 6. 台北榮總快速追蹤（診間名含「診室」格式）
    # Already covered by generic loop above

    # 6. 查追蹤 + 取消
    scenarios.append({
        "name": "追蹤管理",
        "steps": [
            ("t", ["追蹤"]),
            ("@", ["主選單"]),
        ],
    })

    # 7. 不存在的醫院
    scenarios.append({
        "name": "不存在醫院",
        "steps": [
            ("某某某醫院", ["您好", "主選單"]),
        ],
    })

    return scenarios


async def _get_hospitals_with_data() -> list[dict]:
    """取得目前有 Redis 資料的醫院及科別"""
    import redis as sync_redis
    import os

    r = sync_redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
    )

    from app.scrapers.registry import AdapterRegistry
    all_adapters = AdapterRegistry.get_all()

    hospitals = []
    for code, adapter in all_adapters.items():
        keys = r.keys(f"progress:{code}:*")
        if not keys:
            continue

        # 解析科別和診間
        dept_map = {}
        for k in keys:
            val = r.get(k)
            if not val:
                continue
            d = json.loads(val)
            dept = d.get("department", "")
            doctor = d.get("doctor_name", "")
            room = d.get("clinic_room", "")
            cur = d.get("current_number", 0)

            if dept not in dept_map:
                dept_map[dept] = {"dept": dept, "doctors": [], "rooms": [], "count": 0}
            dept_map[dept]["count"] += 1
            if doctor and doctor not in dept_map[dept]["doctors"]:
                dept_map[dept]["doctors"].append(doctor)
            if room:
                dept_map[dept]["rooms"].append({"room": room, "current": cur})

        depts = sorted(dept_map.values(), key=lambda x: -x["count"])
        hospitals.append({
            "code": code,
            "name": adapter.hospital_name,
            "total_rooms": len(keys),
            "depts": depts,  # 全部科別
        })

    return hospitals


def _build_random_scenarios(hospitals: list[dict], count: int = 20) -> list[dict]:
    """隨機測試 — 隨機選醫院/科別/醫師走完整流程"""
    scenarios = []
    all_combos = []  # (hospital, dept, doctor, room)

    for hosp in hospitals:
        for dept in hosp["depts"]:
            for doc in dept["doctors"]:
                rooms = [r["room"] for r in dept["rooms"]]
                all_combos.append((hosp["name"], dept["dept"], doc, rooms[0] if rooms else ""))

    if not all_combos:
        return []

    random.shuffle(all_combos)

    for hosp_name, dept_name, doctor, room in all_combos[:count]:
        # 隨機選一種測試方式
        mode = random.choice(["query_doctor", "filter_dept", "quick_track"])

        if mode == "query_doctor":
            # 醫院 → 科別 → 看結果
            scenarios.append({
                "name": f"隨機查詢 {hosp_name} {doctor}",
                "steps": [
                    (f"{hosp_name} {dept_name}", [dept_name, "看診進度", "哪科", "時段"]),
                    ("@", ["主選單"]),
                ],
            })

        elif mode == "filter_dept":
            # 直接輸入醫院+醫師名
            scenarios.append({
                "name": f"隨機篩選 {hosp_name} {doctor}",
                "steps": [
                    (f"{hosp_name} {doctor}", [doctor, "看診進度", "哪科", "時段"]),
                    ("@", ["主選單"]),
                ],
            })

        elif mode == "quick_track" and re.match(r"^\d+診$|^診室\d+$", room):
            scenarios.append({
                "name": f"隨機追蹤 {hosp_name} {room}",
                "steps": [
                    (f"{hosp_name} {room} 999", ["快速追蹤", "提醒模式"]),
                    ("2", ["追蹤成功"]),
                    ("c", ["取消"]),
                ],
            })
        else:
            # fallback: 查科別
            scenarios.append({
                "name": f"隨機查科 {hosp_name} {dept_name}",
                "steps": [
                    (f"{hosp_name} {dept_name}", [dept_name, "看診進度", "哪科", "時段"]),
                    ("@", ["主選單"]),
                ],
            })

    return scenarios


def _build_deep_scenarios(hospitals: list[dict]) -> list[dict]:
    """深度測試 — 每家醫院的每個科別都走一遍查詢"""
    scenarios = []

    for hosp in hospitals:
        name = hosp["name"]
        for dept in hosp["depts"]:
            scenarios.append({
                "name": f"深度 {name}/{dept['dept']}",
                "steps": [
                    (f"{name} {dept['dept']}", [dept["dept"], "看診進度", "哪科", "時段"]),
                    ("@", ["主選單"]),
                ],
            })

    return scenarios


# ============================================================
# 執行測試
# ============================================================

async def _run_single_user(user_id: str, scenario: dict) -> dict:
    """模擬單一用戶跑完一個劇本"""
    import sys, os
    # 確保 demo_chat.py 可被 import（它在專案根目錄）
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from demo_chat import handle_message, reset_conv

    reset_conv(user_id)
    steps_result = []
    passed = True

    for user_input, expected_keywords in scenario["steps"]:
        t0 = time.time()
        try:
            reply = await handle_message(user_input, user_id)
            elapsed = round(time.time() - t0, 3)

            # 檢查回覆是否包含預期關鍵字（任一即可）
            ok = any(kw in reply for kw in expected_keywords)
            if not ok:
                passed = False

            steps_result.append({
                "input": user_input,
                "expected": expected_keywords,
                "ok": ok,
                "elapsed": elapsed,
                "reply_preview": reply[:120].replace("\n", " "),
            })
        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            passed = False
            steps_result.append({
                "input": user_input,
                "expected": expected_keywords,
                "ok": False,
                "elapsed": elapsed,
                "reply_preview": f"ERROR: {str(e)[:100]}",
            })

    reset_conv(user_id)

    return {
        "user_id": user_id,
        "scenario": scenario["name"],
        "passed": passed,
        "steps": steps_result,
    }


async def _run_test(concurrent: int, scenarios: list[dict]) -> dict:
    """執行完整測試"""
    now = datetime.now(TW_TZ)
    start_time = now.strftime("%m/%d %H:%M:%S")

    # 判斷時段
    hour = now.hour
    if hour < 12:
        session_hint = "上午診"
    elif hour < 17:
        session_hint = "下午診（或上午延診）"
    elif hour < 21:
        session_hint = "夜診"
    else:
        session_hint = "非看診時段"

    # 取得醫院資料狀態
    hospitals = await _get_hospitals_with_data()
    total_rooms = sum(h["total_rooms"] for h in hospitals)
    data_summary = f"{len(hospitals)} 家有資料，共 {total_rooms} 個診間"

    # 分配劇本給用戶
    tasks = []
    for i in range(concurrent):
        scenario = scenarios[i % len(scenarios)]
        user_id = f"__test_user_{i}_{int(time.time())}"
        tasks.append(_run_single_user(user_id, scenario))

    # 並發執行
    t0 = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_elapsed = round(time.time() - t0, 2)

    end_time = datetime.now(TW_TZ).strftime("%m/%d %H:%M:%S")

    # 統計
    user_results = []
    total_steps = 0
    passed_steps = 0
    failed_steps = 0
    total_step_time = 0

    for r in results:
        if isinstance(r, Exception):
            user_results.append({
                "user_id": "?",
                "scenario": "?",
                "passed": False,
                "steps": [{"input": "?", "ok": False, "elapsed": 0, "reply_preview": str(r)[:100]}],
            })
            failed_steps += 1
        else:
            user_results.append(r)
            for s in r["steps"]:
                total_steps += 1
                total_step_time += s["elapsed"]
                if s["ok"]:
                    passed_steps += 1
                else:
                    failed_steps += 1

    avg_step_time = round(total_step_time / max(total_steps, 1), 3)
    passed_users = sum(1 for r in user_results if r.get("passed"))

    existing = _load_reports()
    report = {
        "id": len(existing) + 1,
        "start_time": start_time,
        "end_time": end_time,
        "total_elapsed": total_elapsed,
        "session_hint": session_hint,
        "data_summary": data_summary,
        "hospitals_with_data": len(hospitals),
        "hospital_names": [h["name"] for h in hospitals],
        "concurrent": concurrent,
        "total_scenarios": len(scenarios),
        "scenario_names": list(set(s["name"] for s in scenarios)),
        "total_users": len(user_results),
        "passed_users": passed_users,
        "failed_users": len(user_results) - passed_users,
        "total_steps": total_steps,
        "passed_steps": passed_steps,
        "failed_steps": failed_steps,
        "avg_step_time": avg_step_time,
        "results": user_results,
    }

    # 存到 Redis（含完整步驟但截短 reply）
    summary = {k: v for k, v in report.items() if k != "results"}
    summary["failed_items"] = [
        {"scenario": r["scenario"], "input": s["input"], "reply": s["reply_preview"][:80]}
        for r in user_results for s in r["steps"] if not s["ok"]
    ][:20]
    # 存每個劇本的完整對話（reply 截取前 80 字）
    summary["conversations"] = [
        {
            "scenario": r["scenario"],
            "passed": r["passed"],
            "steps": [
                {"input": s["input"], "ok": s["ok"], "elapsed": s["elapsed"],
                 "reply": s["reply_preview"][:80]}
                for s in r["steps"]
            ],
        }
        for r in user_results
    ]
    _save_report(summary)

    # 清理測試用戶的 DB 資料
    _cleanup_test_users([r["user_id"] for r in user_results])

    return report


def _cleanup_test_users(user_ids: list[str]):
    """清理測試用戶在 DB 中的資料"""
    if not user_ids:
        return
    try:
        import pymysql
        from app.config import settings as s
        conn = pymysql.connect(
            host=s.mysql_host, port=s.mysql_port,
            user=s.mysql_user, password=s.mysql_password,
            database=s.mysql_database,
        )
        cur = conn.cursor()
        fmt = ",".join(["%s"] * len(user_ids))
        cur.execute(
            f"DELETE FROM tracking_tasks WHERE user_id IN "
            f"(SELECT id FROM users WHERE line_user_id IN ({fmt}))",
            user_ids,
        )
        cur.execute(
            f"DELETE FROM users WHERE line_user_id IN ({fmt})",
            user_ids,
        )
        conn.commit()
        conn.close()
        logger.info(f"[test] 已清理 {len(user_ids)} 個測試用戶")
    except Exception as e:
        logger.error(f"[test] 清理測試用戶失敗: {e}")


# ============================================================
# API endpoints
# ============================================================

@router.get("/api/test/status")
async def api_test_status(admin_token: str | None = Cookie(None)):
    """取得測試環境狀態"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    hospitals = await _get_hospitals_with_data()
    scenarios = _build_scenarios(hospitals)

    return {
        "hospitals": [{"name": h["name"], "rooms": h["total_rooms"], "depts": len(h["depts"])} for h in hospitals],
        "scenarios": [{"name": s["name"], "steps": len(s["steps"])} for s in scenarios],
        "total_scenarios": len(scenarios),
    }


@router.post("/api/test/run")
async def api_test_run(request: Request, admin_token: str | None = Cookie(None)):
    """執行測試（可帶參數）"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    from fastapi import Request as Req
    try:
        body = await request.json()
    except Exception:
        body = {}

    selected_hospitals = body.get("hospitals", [])  # 醫院名稱列表，空=全部
    selected_types = body.get("scenario_types", [])  # 劇本類型，空=全部
    users_per_scenario = min(body.get("users_per_scenario", 1), 20)
    max_concurrent = min(body.get("max_concurrent", 30), 200)

    hospitals = await _get_hospitals_with_data()

    # 篩選醫院
    if selected_hospitals:
        hospitals = [h for h in hospitals if h["name"] in selected_hospitals]

    scenarios = _build_scenarios(hospitals)

    # 篩選劇本類型
    type_map = {
        "query": "查詢",
        "filter": "篩選",
        "quick_track": "快速追蹤",
        "pretrack": "預約追蹤",
        "shortcut": "快捷",
        "edge": "不存在",
    }
    if selected_types:
        keywords = [type_map[t] for t in selected_types if t in type_map]
        # 也包含「追蹤管理」（屬於 edge）
        if "edge" in selected_types:
            keywords.append("追蹤管理")
        scenarios = [s for s in scenarios if any(kw in s["name"] for kw in keywords)]

    if not scenarios:
        return {"error": "沒有符合條件的劇本"}

    # 加入隨機測試和深度測試
    test_mode = body.get("test_mode", "standard")  # standard / random / deep / all
    if test_mode in ("random", "all"):
        random_count = body.get("random_count", 20)
        scenarios.extend(_build_random_scenarios(hospitals, random_count))
    if test_mode in ("deep", "all"):
        scenarios.extend(_build_deep_scenarios(hospitals))

    # 計算並發數
    concurrent = min(len(scenarios) * users_per_scenario, max_concurrent)
    expanded = []
    for _ in range(users_per_scenario):
        expanded.extend(scenarios)

    report = await _run_test(concurrent, expanded[:concurrent])
    report["test_mode"] = test_mode
    return report


# ============================================================
# 排程測試
# ============================================================

SCHEDULE_KEY = "test:schedule"


def _get_schedule():
    import redis as sync_redis
    import os
    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    data = r.get(SCHEDULE_KEY)
    if data:
        return json.loads(data)
    return None


def _save_schedule(schedule):
    import redis as sync_redis
    import os
    r = sync_redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    if schedule is None:
        r.delete(SCHEDULE_KEY)
    else:
        r.set(SCHEDULE_KEY, json.dumps(schedule, ensure_ascii=False), ex=86400)


@router.post("/api/test/schedule")
async def api_test_schedule(request: Request, admin_token: str | None = Cookie(None)):
    """建立排程測試"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    body = await request.json()
    schedule = {
        "hospitals": body.get("hospitals", []),
        "scenario_types": body.get("scenario_types", []),
        "users_per_scenario": min(body.get("users_per_scenario", 1), 20),
        "max_concurrent": min(body.get("max_concurrent", 30), 200),
        "start_time": body.get("start_time", "08:30"),
        "end_time": body.get("end_time", "12:00"),
        "interval_minutes": body.get("interval_minutes", 10),
        "active": True,
        "runs_done": 0,
        "created_at": datetime.now(TW_TZ).strftime("%m/%d %H:%M"),
    }
    _save_schedule(schedule)
    return {"ok": True}


@router.delete("/api/test/schedule")
async def api_test_cancel_schedule(admin_token: str | None = Cookie(None)):
    """取消排程"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)
    _save_schedule(None)
    return {"ok": True}


@router.get("/api/test/schedule")
async def api_test_get_schedule(admin_token: str | None = Cookie(None)):
    """取得排程狀態"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)
    schedule = _get_schedule()
    if not schedule:
        return {"active": False}
    return {
        "active": schedule.get("active", False),
        "start_time": schedule.get("start_time"),
        "end_time": schedule.get("end_time"),
        "interval": schedule.get("interval_minutes"),
        "runs_done": schedule.get("runs_done", 0),
    }


async def run_scheduled_test_if_needed():
    """由 celery beat 每分鐘呼叫，檢查是否需要執行排程測試"""
    schedule = _get_schedule()
    if not schedule or not schedule.get("active"):
        return

    now = datetime.now(TW_TZ)
    now_str = now.strftime("%H:%M")
    start = schedule["start_time"]
    end = schedule["end_time"]

    # 不在時間範圍內
    if now_str < start or now_str > end:
        return

    # 檢查間隔
    interval = schedule.get("interval_minutes", 10)
    runs_done = schedule.get("runs_done", 0)
    # 從開始時間算，現在應該跑到第幾次
    start_h, start_m = map(int, start.split(":"))
    start_minutes = start_h * 60 + start_m
    now_minutes = now.hour * 60 + now.minute
    expected_runs = (now_minutes - start_minutes) // interval + 1

    if runs_done >= expected_runs:
        return  # 這一輪已跑過

    # 執行測試
    logger.info(f"[test_schedule] 執行排程測試 #{runs_done + 1}")

    hospitals = await _get_hospitals_with_data()
    selected = schedule.get("hospitals", [])
    if selected:
        hospitals = [h for h in hospitals if h["name"] in selected]

    scenarios = _build_scenarios(hospitals)

    type_map = {"query": "查詢", "filter": "篩選", "quick_track": "快速追蹤",
                "pretrack": "預約追蹤", "shortcut": "快捷", "edge": "不存在"}
    selected_types = schedule.get("scenario_types", [])
    if selected_types:
        keywords = [type_map.get(t, "") for t in selected_types]
        if "edge" in selected_types:
            keywords.append("追蹤管理")
        scenarios = [s for s in scenarios if any(kw in s["name"] for kw in keywords if kw)]

    if not scenarios:
        return

    # 加入隨機和深度測試
    test_mode = schedule.get("test_mode", "standard")
    if test_mode in ("random", "all"):
        scenarios.extend(_build_random_scenarios(hospitals, schedule.get("random_count", 20)))
    if test_mode in ("deep", "all"):
        scenarios.extend(_build_deep_scenarios(hospitals))

    users = schedule.get("users_per_scenario", 1)
    max_c = schedule.get("max_concurrent", 30)
    concurrent = min(len(scenarios) * users, max_c)
    expanded = []
    for _ in range(users):
        expanded.extend(scenarios)

    report = await _run_test(concurrent, expanded[:concurrent])

    # 更新計數
    schedule["runs_done"] = runs_done + 1
    # 結束時間到了就停
    if now_str >= end:
        schedule["active"] = False
    _save_schedule(schedule)

    logger.info(f"[test_schedule] 完成 #{runs_done + 1}: {report['passed_steps']}/{report['total_steps']} passed")


@router.get("/api/test/reports")
async def api_test_reports(admin_token: str | None = Cookie(None)):
    """取得歷史報告列表"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    reports = _load_reports()
    return list(reversed(reports[-20:]))
