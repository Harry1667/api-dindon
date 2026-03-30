"""後台管理路由 — 登入彈框 + 統計 + 醫院管理"""

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Request, Cookie
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])

import hashlib
JWT_SECRET = hashlib.sha256(settings.admin_password.encode()).hexdigest()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24


def _make_token() -> str:
    payload = {
        "sub": settings.admin_username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _check_auth(token: str | None) -> bool:
    if not token:
        return False
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return False


# ============================================================
# API
# ============================================================

@router.post("/api/login")
async def api_login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    if (secrets.compare_digest(username, settings.admin_username)
            and secrets.compare_digest(password, settings.admin_password)):
        token = _make_token()
        resp = JSONResponse({"ok": True})
        resp.set_cookie("admin_token", token, httponly=True, samesite="strict",
                         max_age=JWT_EXPIRE_HOURS * 3600)
        return resp
    return JSONResponse({"ok": False, "error": "帳號或密碼錯誤"}, status_code=401)


@router.post("/api/logout")
async def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("admin_token")
    return resp


@router.get("/api/stats")
async def api_stats(admin_token: str | None = Cookie(None)):
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    from sqlalchemy import select, func
    from app.models.database import async_session
    from app.models.hospital import Hospital
    from app.models.user import User
    from app.models.tracking_task import TrackingTask

    async with async_session() as session:
        total_hospitals = (await session.execute(select(func.count(Hospital.id)))).scalar() or 0
        active_hospitals = (await session.execute(
            select(func.count(Hospital.id)).where(Hospital.is_active == True)
        )).scalar() or 0
        total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
        active_tracks = (await session.execute(
            select(func.count(TrackingTask.id)).where(TrackingTask.status == "active")
        )).scalar() or 0
        total_tracks = (await session.execute(select(func.count(TrackingTask.id)))).scalar() or 0

    from app.scrapers.registry import AdapterRegistry
    adapter_count = len(AdapterRegistry.get_all())

    return {
        "total_hospitals": total_hospitals,
        "active_hospitals": active_hospitals,
        "adapter_count": adapter_count,
        "total_users": total_users,
        "active_tracks": active_tracks,
        "total_tracks": total_tracks,
    }


# ============================================================
# 追蹤回饋 API
# ============================================================

@router.get("/api/feedbacks")
async def api_feedbacks(admin_token: str | None = Cookie(None)):
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.tracking_feedback import TrackingFeedback

    async with async_session() as session:
        result = await session.execute(
            select(TrackingFeedback).order_by(TrackingFeedback.created_at.desc()).limit(100)
        )
        feedbacks = result.scalars().all()

    from app.scrapers.registry import AdapterRegistry

    end_reason_labels = {
        "arrived": "✅ 到號", "passed": "⚠️ 過號", "doctor_gone": "📴 停診",
        "timeout": "⏰ 逾時", "cancelled": "🚫 取消",
    }

    return [
        {
            "id": f.id,
            "task_id": f.task_id,
            "line_user_id": f.line_user_id[:8] + "...",
            "hospital": getattr(f, 'hospital_name', None) or (AdapterRegistry.get(f.hospital_code).hospital_name if AdapterRegistry.get(f.hospital_code) else f.hospital_code),
            "department": f.department,
            "doctor_name": f.doctor_name,
            "clinic_room": f.clinic_room,
            "session": f.session,
            "user_number": f.user_number,
            "notify_mode": f.notify_mode,
            "track_created_at": f.track_created_at.strftime("%m/%d %H:%M") if getattr(f, 'track_created_at', None) else "",
            "final_current": f.final_current,
            "notify_count": getattr(f, 'notify_count', 0),
            "end_reason": end_reason_labels.get(getattr(f, 'end_reason', ''), getattr(f, 'end_reason', '')),
            "final_message": f.final_message,
            "is_correct": f.is_correct,
            "user_comment": f.user_comment,
            "conversation_log": getattr(f, 'conversation_log', None) or "[]",
            "created_at": f.created_at.strftime("%m/%d %H:%M") if f.created_at else "",
        }
        for f in feedbacks
    ]


# ============================================================
# 快捷指令管理（存 Redis）
# ============================================================

SHORTCUTS_KEY = "config:shortcuts"

# 預設快捷指令
DEFAULT_SHORTCUTS = [
    {"trigger": "@, 0, 返回, 主選單", "action": "返回", "label": "回主選單", "description": "回到主選單"},
    {"trigger": "00, 醫院, 列表", "action": "醫院", "label": "醫院列表", "description": "查看支援的醫院"},
    {"trigger": "h, help, 說明, 幫助", "action": "說明", "label": "功能介紹", "description": "顯示使用說明"},
    {"trigger": "t, 追蹤, 我的追蹤", "action": "我的追蹤", "label": "追蹤狀態", "description": "查看目前追蹤"},
    {"trigger": "c, 取消追蹤, 停止追蹤", "action": "取消追蹤", "label": "取消追蹤", "description": "取消所有追蹤"},
    {"trigger": "p, 預約, 預約追蹤, 預先追蹤", "action": "預約追蹤", "label": "預約追蹤", "description": "提前設定看診追蹤"},
]


def _get_shortcuts() -> list[dict]:
    """從 Redis 讀取快捷指令，若不存在則寫入預設值"""
    import json
    import redis as sync_redis
    r = sync_redis.from_url(settings.redis_url if hasattr(settings, 'redis_url') else "redis://redis:6379/0", decode_responses=True)
    data = r.get(SHORTCUTS_KEY)
    if data:
        return json.loads(data)
    # 寫入預設
    r.set(SHORTCUTS_KEY, json.dumps(DEFAULT_SHORTCUTS, ensure_ascii=False))
    return DEFAULT_SHORTCUTS


def _save_shortcuts(shortcuts: list[dict]):
    import json
    import redis as sync_redis
    r = sync_redis.from_url(settings.redis_url if hasattr(settings, 'redis_url') else "redis://redis:6379/0", decode_responses=True)
    r.set(SHORTCUTS_KEY, json.dumps(shortcuts, ensure_ascii=False))


@router.get("/api/shortcuts")
async def api_get_shortcuts(admin_token: str | None = Cookie(None)):
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)
    return _get_shortcuts()


@router.put("/api/shortcuts")
async def api_save_shortcuts(request: Request, admin_token: str | None = Cookie(None)):
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)
    body = await request.json()
    shortcuts = body if isinstance(body, list) else body.get("shortcuts", [])
    _save_shortcuts(shortcuts)
    return {"ok": True, "count": len(shortcuts)}


@router.post("/api/shortcuts/reset")
async def api_reset_shortcuts(admin_token: str | None = Cookie(None)):
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)
    _save_shortcuts(DEFAULT_SHORTCUTS)
    return {"ok": True, "shortcuts": DEFAULT_SHORTCUTS}


@router.get("/api/hospitals")
async def api_hospitals(admin_token: str | None = Cookie(None)):
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.hospital import Hospital
    from app.models.hospital_alias import HospitalAlias

    CITY_ORDER = ['臺北市','新北市','桃園市','基隆市','臺中市','高雄市','臺南市','宜蘭縣']

    async with async_session() as session:
        result = await session.execute(select(Hospital))
        hospitals = result.scalars().all()

        # 取所有別名
        alias_result = await session.execute(select(HospitalAlias))
        all_aliases = alias_result.scalars().all()

    def city_rank(c):
        try:
            return CITY_ORDER.index(c)
        except ValueError:
            return 100

    hospitals.sort(key=lambda h: (
        0 if h.level == '醫學中心' else 1,
        city_rank(h.city),
        h.city,
        h.id,
    ))

    # 按 hospital_code 分組
    alias_map: dict[str, list[str]] = {}
    for a in all_aliases:
        alias_map.setdefault(a.hospital_code, []).append(a.alias)

    return [
        {
            "id": h.id,
            "code": h.code,
            "nhi_code": h.nhi_code,
            "name": h.name,
            "short_name": h.short_name,
            "aliases": alias_map.get(h.code, []),
            "level": h.level,
            "city": h.city,
            "district": h.district,
            "phone": h.phone,
            "url": h.url,
            "adapter_name": h.adapter_name,
            "is_active": h.is_active,
            "scrape_interval": h.scrape_interval,
        }
        for h in hospitals
    ]


@router.put("/api/hospitals/{code}/toggle")
async def toggle_hospital(code: str, request: Request, admin_token: str | None = Cookie(None)):
    """切換醫院啟用/停用"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    body = await request.json()
    active = body.get("is_active")
    if active is None:
        return JSONResponse({"error": "缺少 is_active"}, status_code=400)

    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.hospital import Hospital

    async with async_session() as session:
        result = await session.execute(select(Hospital).where(Hospital.code == code))
        hospital = result.scalar_one_or_none()
        if not hospital:
            return JSONResponse({"error": f"找不到醫院: {code}"}, status_code=404)
        hospital.is_active = bool(active)
        await session.commit()

    return {"ok": True, "code": code, "is_active": bool(active)}


@router.put("/api/hospitals/{code}/aliases")
async def update_hospital_aliases(code: str, request: Request, admin_token: str | None = Cookie(None)):
    """更新醫院簡稱和別名"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    body = await request.json()
    new_short_name = (body.get("short_name") or "").strip()
    # aliases 是逗號分隔的字串，拆成 list
    aliases_raw = body.get("aliases", "")
    new_aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]

    from sqlalchemy import select, delete
    from app.models.database import async_session
    from app.models.hospital import Hospital
    from app.models.hospital_alias import HospitalAlias

    async with async_session() as session:
        # 更新 short_name
        result = await session.execute(select(Hospital).where(Hospital.code == code))
        hospital = result.scalar_one_or_none()
        if not hospital:
            return JSONResponse({"error": f"找不到醫院: {code}"}, status_code=404)

        if new_short_name:
            hospital.short_name = new_short_name

        # 刪除該醫院舊別名
        await session.execute(
            delete(HospitalAlias).where(HospitalAlias.hospital_code == code)
        )

        # 寫入新別名（允許重複，同一個 alias 可對應多家醫院）
        added = []
        for alias in new_aliases:
            session.add(HospitalAlias(hospital_code=code, alias=alias))
            added.append(alias)

        await session.commit()

    # 找出哪些別名有其他醫院也在用（提示用）
    shared = []
    async with async_session() as session:
        for alias in added:
            result = await session.execute(
                select(HospitalAlias).where(
                    HospitalAlias.alias == alias,
                    HospitalAlias.hospital_code != code,
                )
            )
            others = result.scalars().all()
            if others:
                shared.append(f"{alias}({len(others)+1}家共用)")

    return {
        "ok": True,
        "code": code,
        "short_name": new_short_name or hospital.short_name,
        "aliases_added": added,
        "aliases_shared": shared,
    }


@router.get("/api/department-guide")
async def api_department_guide(admin_token: str | None = Cookie(None)):
    """科別就醫指南"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.department import DepartmentGuide

    async with async_session() as session:
        result = await session.execute(
            select(DepartmentGuide).order_by(DepartmentGuide.category, DepartmentGuide.department)
        )
        guides = result.scalars().all()

    return [
        {
            "id": g.id,
            "department": g.department,
            "category": g.category,
            "disease": g.disease,
            "symptoms": g.symptoms,
            "keywords": g.keywords,
        }
        for g in guides
    ]


@router.get("/api/doctors")
async def api_doctors(admin_token: str | None = Cookie(None), hospital_code: str = ""):
    """醫師清單"""
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    from sqlalchemy import select, func
    from app.models.database import async_session
    from app.models.doctor import Doctor

    async with async_session() as session:
        query = select(Doctor).order_by(Doctor.hospital_code, Doctor.department, Doctor.name)
        if hospital_code:
            query = query.where(Doctor.hospital_code == hospital_code)
        query = query.limit(500)
        result = await session.execute(query)
        doctors = result.scalars().all()

        total = (await session.execute(select(func.count(Doctor.id)))).scalar() or 0

    return {
        "total": total,
        "count": len(doctors),
        "doctors": [
            {
                "id": d.id,
                "hospital_code": d.hospital_code,
                "department": d.department,
                "name": d.name,
                "title": d.title,
                "specialty": d.specialty,
                "clinic_room": d.clinic_room,
            }
            for d in doctors
        ],
    }


# ============================================================
# 頁面
# ============================================================

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_page():
    return ADMIN_HTML


# ============================================================
# HTML
# ============================================================

ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>叮咚到號 — 後台管理</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, 'Segoe UI', Roboto, 'Noto Sans TC', sans-serif; background:#f0f2f5; color:#333; }

.overlay { position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:1000; display:flex; align-items:center; justify-content:center; }
.login-box, .modal-box { background:#fff; border-radius:12px; padding:32px; width:420px; box-shadow:0 8px 30px rgba(0,0,0,.15); }
.login-box h2, .modal-box h2 { text-align:center; margin-bottom:20px; font-size:18px; }
.login-box input, .modal-box input { width:100%; padding:10px 12px; margin-bottom:12px; border:1px solid #ddd; border-radius:6px; font-size:14px; }
.login-box input:focus, .modal-box input:focus { outline:none; border-color:#4a90d9; }
.login-box button, .modal-box .btn { padding:10px 20px; background:#4a90d9; color:#fff; border:none; border-radius:6px; font-size:14px; cursor:pointer; }
.login-box button:hover, .modal-box .btn:hover { background:#357abd; }
.login-box button { width:100%; }
.login-box .error, .modal-box .msg { font-size:13px; text-align:center; margin-top:8px; min-height:20px; }
.modal-box .msg.ok { color:#27ae60; }
.modal-box .msg.err { color:#e74c3c; }
.modal-box label { display:block; font-size:13px; color:#666; margin-bottom:4px; }
.modal-box .hint { font-size:12px; color:#999; margin:-8px 0 12px; }
.modal-box .btn-row { display:flex; gap:8px; justify-content:flex-end; margin-top:16px; }
.modal-box .btn-cancel { background:#eee; color:#333; }
.modal-box .btn-cancel:hover { background:#ddd; }
.modal-box .alias-tags { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px; min-height:28px; }
.modal-box .alias-tag { display:inline-flex; align-items:center; gap:2px; background:#e8f0fe; color:#2979ff; padding:2px 8px; border-radius:10px; font-size:12px; }
.modal-box .alias-tag .x { cursor:pointer; font-weight:700; margin-left:2px; }
.modal-box .alias-tag .x:hover { color:#e74c3c; }

.header { background:#fff; border-bottom:1px solid #e0e0e0; padding:12px 24px; display:flex; align-items:center; justify-content:space-between; }
.header h1 { font-size:18px; }
.header .right { display:flex; gap:8px; align-items:center; }
.header button { padding:6px 14px; border:1px solid #ddd; border-radius:6px; background:#fff; cursor:pointer; font-size:13px; }
.header button:hover { background:#f5f5f5; }
.header button.active { background:#4a90d9; color:#fff; border-color:#4a90d9; }
.header .logout { color:#e74c3c; border-color:#e74c3c; }
.header .logout:hover { background:#e74c3c; color:#fff; }

.container { max-width:100%; margin:20px auto; padding:0 24px; }
.hidden { display:none !important; }

.stat-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(180px,1fr)); gap:16px; margin-bottom:24px; }
.stat-card { background:#fff; border-radius:10px; padding:20px; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,.08); }
.stat-card .num { font-size:32px; font-weight:700; color:#4a90d9; }
.stat-card .label { font-size:13px; color:#888; margin-top:4px; }

.table-wrap { background:#fff; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,.08); overflow:auto; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th,td { padding:8px 12px; text-align:left; border-bottom:1px solid #f0f0f0; white-space:nowrap; }
th { background:#fafafa; font-weight:600; position:sticky; top:0; }
tr:hover td { background:#f8f9ff; }
td.clickable { cursor:pointer; }
td.clickable:hover { color:#4a90d9; text-decoration:underline; }
.badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }
.badge-green { background:#e6f9ee; color:#27ae60; }
.badge-red { background:#fde8e8; color:#e74c3c; }
.badge-gray { background:#f0f0f0; color:#888; }
.badge-blue { background:#e8f0fe; color:#2979ff; }
.alias-list { font-size:11px; color:#888; }
.toggle { cursor:pointer; }
.toggle:hover { opacity:.7; }

.filter-bar { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; align-items:center; }
.filter-bar input { flex:1; min-width:180px; max-width:300px; padding:8px 12px; border:1px solid #ddd; border-radius:6px; font-size:14px; }
.filter-bar select { padding:8px 10px; border:1px solid #ddd; border-radius:6px; font-size:13px; background:#fff; }
.filter-count { font-size:13px; color:#888; }
th.sortable { cursor:pointer; user-select:none; }
th.sortable:hover { background:#f0f4ff; }
th.sortable span { font-size:10px; }

@media(max-width:600px) {
  .stat-grid { grid-template-columns:repeat(2,1fr); }
  .header { flex-wrap:wrap; gap:8px; }
  .modal-box { width:95%; padding:20px; }
}
</style>
</head>
<body>

<!-- 登入 -->
<div class="overlay" id="loginOverlay">
  <div class="login-box">
    <h2>叮咚到號 後台登入</h2>
    <input type="text" id="username" placeholder="帳號" autocomplete="username">
    <input type="password" id="password" placeholder="密碼" autocomplete="current-password">
    <button onclick="doLogin()">登入</button>
    <div class="error" id="loginError"></div>
  </div>
</div>

<!-- 編輯別名彈框 -->
<div class="overlay hidden" id="editOverlay" onclick="if(event.target===this)closeEdit()">
  <div class="modal-box">
    <h2 id="editTitle">編輯簡稱 / 別名</h2>
    <label>簡稱</label>
    <input type="text" id="editShortName" placeholder="醫院簡稱">
    <label>別名（輸入後按 Enter 新增）</label>
    <div class="alias-tags" id="aliasTags"></div>
    <input type="text" id="aliasInput" placeholder="輸入別名後按 Enter">
    <div class="hint">用戶可透過簡稱或別名搜尋醫院，例如「台大」「北榮」「三總」</div>
    <div class="msg" id="editMsg"></div>
    <div class="btn-row">
      <button class="btn btn-cancel" onclick="closeEdit()">取消</button>
      <button class="btn" onclick="saveEdit()">儲存</button>
    </div>
  </div>
</div>

<!-- Header -->
<div class="header" id="mainHeader" style="display:none">
  <h1>叮咚到號 後台管理</h1>
  <div class="right">
    <button id="tabStats" class="active" onclick="switchTab('stats')">統計總覽</button>
    <button id="tabHospitals" onclick="switchTab('hospitals')">醫院管理</button>
    <button id="tabShortcuts" onclick="switchTab('shortcuts')">快捷指令</button>
    <button id="tabFeedback" onclick="switchTab('feedback')">回饋記錄</button>
    <button id="tabTest" onclick="switchTab('test')">系統測試</button>
    <button id="tabLive" onclick="switchTab('live')">即時追蹤測試</button>
    <button class="logout" onclick="doLogout()">登出</button>
  </div>
</div>

<!-- 統計頁 -->
<div class="container hidden" id="pageStats">
  <div class="stat-grid" id="statCards"></div>
</div>

<!-- 醫院頁 -->
<div class="container hidden" id="pageHospitals">
  <div class="filter-bar">
    <input type="text" id="hospitalSearch" placeholder="搜尋名稱、代碼、別名..." oninput="applyFilters()">
    <select id="filterCity" onchange="applyFilters()"><option value="">全部縣市</option></select>
    <select id="filterDistrict" onchange="applyFilters()"><option value="">全部區</option></select>
    <select id="filterLevel" onchange="applyFilters()">
      <option value="">全部層級</option><option value="醫學中心">醫學中心</option><option value="區域醫院">區域醫院</option>
    </select>
    <select id="filterStatus" onchange="applyFilters()">
      <option value="">全部狀態</option><option value="active">已啟用</option><option value="inactive">未啟用</option>
    </select>
    <span id="filterCount" class="filter-count"></span>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th class="sortable" onclick="sortBy('code')">code <span id="sort_code"></span></th>
          <th>簡稱 / 別名</th>
          <th class="sortable" onclick="sortBy('level')">層級 <span id="sort_level"></span></th>
          <th class="sortable" onclick="sortBy('city')">縣市 <span id="sort_city"></span></th>
          <th class="sortable" onclick="sortBy('district')">區 <span id="sort_district"></span></th>
          <th>健保代碼</th>
          <th class="sortable" onclick="sortBy('adapter')">Adapter <span id="sort_adapter"></span></th>
          <th class="sortable" onclick="sortBy('status')">狀態 <span id="sort_status"></span></th>
          <th>電話</th>
        </tr>
      </thead>
      <tbody id="hospitalBody"></tbody>
    </table>
  </div>
</div>

<!-- 回饋記錄頁 -->
<div class="container hidden" id="pageFeedback">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
    <h2 style="font-size:16px;margin:0;">追蹤回饋記錄</h2>
    <span id="feedbackStats" style="font-size:13px;color:#888;"></span>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>用戶</th>
        <th>追蹤建立</th>
        <th>醫院</th>
        <th>科別/醫師</th>
        <th>診間</th>
        <th>掛號</th>
        <th>結束號碼</th>
        <th>結束原因</th>
        <th>通知次數</th>
        <th>回饋</th>
        <th>用戶說明</th>
        <th>對話</th>
      </tr></thead>
      <tbody id="feedbackBody"></tbody>
    </table>
  </div>
</div>

<!-- 即時追蹤測試頁 -->
<div class="container hidden" id="pageLive">
  <h2 style="font-size:16px;margin:0 0 12px;">即時追蹤測試</h2>
  <p style="font-size:13px;color:#666;margin-bottom:12px;">用假用戶追蹤正在看診的真實醫師，驗證通知是否正確觸發。掛號號碼 = 目前號碼 + 偏移量。</p>
  <div style="display:flex;gap:16px;align-items:center;margin-bottom:16px;flex-wrap:wrap;">
    <label style="font-size:13px;">追蹤數量 <select id="liveCount" style="padding:4px;border:1px solid #ddd;border-radius:4px;">
      <option value="3">3</option><option value="5" selected>5</option><option value="10">10</option><option value="15">15</option>
    </select></label>
    <label style="font-size:13px;">號碼偏移 <select id="liveOffset" style="padding:4px;border:1px solid #ddd;border-radius:4px;">
      <option value="1">+1（快到號）</option><option value="3" selected>+3</option><option value="5">+5</option><option value="10">+10</option>
    </select></label>
    <label style="font-size:13px;">提醒模式 <select id="liveMode" style="padding:4px;border:1px solid #ddd;border-radius:4px;">
      <option value="normal">📢 每號</option><option value="light">🔔 輕量</option><option value="final">🔕 最後</option>
    </select></label>
    <button id="btnLiveStart" onclick="startLiveTest()" style="padding:8px 20px;border:none;border-radius:6px;background:#4a90d9;color:#fff;cursor:pointer;font-size:14px;">▶ 開始追蹤</button>
    <button id="btnLiveCheck" onclick="checkLiveTest()" style="padding:8px 16px;border:1px solid #4a90d9;border-radius:6px;background:#fff;color:#4a90d9;cursor:pointer;font-size:13px;">🔄 刷新</button>
    <button id="btnLiveStop" onclick="stopLiveTest()" style="padding:8px 16px;border:1px solid #e74c3c;border-radius:6px;background:#fff;color:#e74c3c;cursor:pointer;font-size:13px;display:none;">⏹ 停止</button>
  </div>
  <div id="liveStatus" style="margin-bottom:12px;font-size:13px;color:#888;"></div>
  <div class="table-wrap">
    <table><thead><tr>
      <th>醫院</th><th>科別</th><th>醫師</th><th>診間</th><th>時段</th>
      <th>掛號</th><th>開始時號碼</th><th>目前號碼</th><th>剩餘</th><th>狀態</th>
    </tr></thead><tbody id="liveBody"></tbody></table>
  </div>
</div>

<!-- 系統測試頁 -->
<div class="container hidden" id="pageTest">
  <h2 style="font-size:16px;margin:0 0 16px;">系統測試</h2>

  <!-- 設定區 -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
    <!-- 左：環境 + 醫院 -->
    <div style="background:#f8f9ff;border-radius:8px;padding:16px;">
      <b>環境狀態</b>
      <div id="testEnv" style="font-size:13px;color:#666;margin-top:8px;">載入中...</div>
      <div style="margin-top:12px;">
        <b>醫院選擇</b>
        <div style="margin-top:4px;display:flex;gap:8px;align-items:center;">
          <label style="font-size:13px;"><input type="checkbox" id="testAllHospitals" checked onchange="toggleAllHospitals()"> 全部</label>
        </div>
        <div id="testHospitalList" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;font-size:12px;"></div>
      </div>
    </div>

    <!-- 右：劇本 + 參數 -->
    <div style="background:#f8f9ff;border-radius:8px;padding:16px;">
      <b>測試劇本</b>
      <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:8px;font-size:13px;" id="testScenarioTypes">
        <label><input type="checkbox" value="query" checked> 查詢醫院</label>
        <label><input type="checkbox" value="filter" checked> 科別篩選</label>
        <label><input type="checkbox" value="quick_track" checked> 快速追蹤</label>
        <label><input type="checkbox" value="pretrack" checked> 預約追蹤</label>
        <label><input type="checkbox" value="shortcut" checked> 快捷指令</label>
        <label><input type="checkbox" value="edge" checked> 邊界測試</label>
      </div>
      <div style="margin-top:12px;">
        <b>測試模式</b>
        <div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:8px;font-size:13px;">
          <label><input type="radio" name="testMode" value="standard" checked> 標準（每院基本流程）</label>
          <label><input type="radio" name="testMode" value="random"> 隨機（隨機醫師/科別）</label>
          <label><input type="radio" name="testMode" value="deep"> 深度（每院每科都測）</label>
          <label><input type="radio" name="testMode" value="all"> 全部（標準+隨機+深度）</label>
        </div>
      </div>
      <div style="margin-top:12px;display:flex;gap:16px;align-items:center;">
        <div>
          <b>隨機測試數</b>
          <select id="testRandomCount" style="margin-left:8px;padding:4px 8px;border:1px solid #ddd;border-radius:4px;">
            <option value="10">10</option>
            <option value="20" selected>20</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>
        <div>
          <b>最大並發</b>
          <select id="testMaxConcurrent" style="margin-left:8px;padding:4px 8px;border:1px solid #ddd;border-radius:4px;">
            <option value="30">30</option>
            <option value="50" selected>50</option>
            <option value="100">100</option>
            <option value="200">200</option>
          </select>
        </div>
      </div>
      <div style="margin-top:16px;border-top:1px solid #e0e0e0;padding-top:12px;">
        <b>排程設定</b>
        <div style="margin-top:8px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:13px;">
          <label>開始 <input type="time" id="testStartTime" value="08:30" style="padding:4px;border:1px solid #ddd;border-radius:4px;"></label>
          <label>結束 <input type="time" id="testEndTime" value="12:00" style="padding:4px;border:1px solid #ddd;border-radius:4px;"></label>
          <label>間隔 <select id="testInterval" style="padding:4px;border:1px solid #ddd;border-radius:4px;">
            <option value="1">1 分鐘</option>
            <option value="3">3 分鐘</option>
            <option value="5" selected>5 分鐘</option>
            <option value="10">10 分鐘</option>
            <option value="30">30 分鐘</option>
            <option value="60">60 分鐘</option>
          </select></label>
          <div style="display:flex;gap:4px;">
            <button onclick="setTimePreset('morning')" style="padding:2px 8px;border:1px solid #ddd;border-radius:4px;background:#fff;cursor:pointer;font-size:12px;">上午診</button>
            <button onclick="setTimePreset('afternoon')" style="padding:2px 8px;border:1px solid #ddd;border-radius:4px;background:#fff;cursor:pointer;font-size:12px;">下午診</button>
            <button onclick="setTimePreset('night')" style="padding:2px 8px;border:1px solid #ddd;border-radius:4px;background:#fff;cursor:pointer;font-size:12px;">夜診</button>
          </div>
        </div>
      </div>
      <div style="margin-top:12px;display:flex;gap:8px;align-items:center;">
        <button id="btnRunTest" onclick="runTest()" style="padding:10px 28px;border:none;border-radius:6px;background:#4a90d9;color:#fff;cursor:pointer;font-size:14px;font-weight:600;">▶ 立即測試</button>
        <button id="btnSchedule" onclick="scheduleTest()" style="padding:10px 28px;border:none;border-radius:6px;background:#27ae60;color:#fff;cursor:pointer;font-size:14px;font-weight:600;">⏰ 排程測試</button>
        <button id="btnCancelSchedule" onclick="cancelSchedule()" style="padding:10px 20px;border:1px solid #e74c3c;border-radius:6px;background:#fff;color:#e74c3c;cursor:pointer;font-size:13px;display:none;">取消排程</button>
        <span id="testRunning" style="display:none;margin-left:8px;font-size:13px;color:#888;">⏳ 測試中...</span>
        <span id="scheduleStatus" style="margin-left:8px;font-size:13px;color:#27ae60;"></span>
      </div>
    </div>
  </div>

  <!-- 結果區 -->
  <div id="testReport" style="display:none;">
    <div id="testSummary" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px;margin-bottom:16px;"></div>
    <div id="testFails" style="margin-bottom:16px;"></div>
    <div style="margin-bottom:8px;font-size:13px;color:#888;">
      <label><input type="checkbox" id="testShowOnlyFails" onchange="filterTestResults()"> 只顯示失敗</label>
    </div>
    <div class="table-wrap">
      <table><thead><tr>
        <th>#</th><th>劇本</th><th>步驟</th><th>輸入</th><th>結果</th><th>耗時</th><th>回覆預覽</th>
      </tr></thead><tbody id="testBody"></tbody></table>
    </div>
  </div>

  <!-- 歷史 -->
  <div id="testHistory" style="margin-top:24px;"></div>
</div>

<!-- 快捷指令頁 -->
<div class="container hidden" id="pageShortcuts">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
    <h2 style="font-size:16px;margin:0;">快捷指令設定</h2>
    <div style="display:flex;gap:8px;">
      <button class="btn" onclick="addShortcut()" style="padding:6px 14px;border:1px solid #4a90d9;border-radius:6px;background:#4a90d9;color:#fff;cursor:pointer;font-size:13px;">+ 新增指令</button>
      <button onclick="resetShortcuts()" style="padding:6px 14px;border:1px solid #e74c3c;border-radius:6px;background:#fff;color:#e74c3c;cursor:pointer;font-size:13px;">恢復預設</button>
    </div>
  </div>
  <p style="font-size:13px;color:#888;margin-bottom:12px;">用戶輸入「觸發詞」時，系統會自動轉換為「對應動作」執行。觸發詞用逗號分隔可設多個（如：h, help, 說明）。</p>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th style="width:36px">#</th>
        <th style="width:33%">觸發詞（逗號分隔）</th>
        <th style="width:120px">對應動作</th>
        <th style="width:100px">顯示名稱</th>
        <th>說明</th>
        <th style="width:60px">操作</th>
      </tr></thead>
      <tbody id="shortcutBody"></tbody>
    </table>
  </div>
  <div style="margin-top:12px;display:flex;gap:8px;">
    <button class="btn" onclick="saveShortcuts()" style="padding:8px 24px;border:none;border-radius:6px;background:#27ae60;color:#fff;cursor:pointer;font-size:14px;">儲存變更</button>
    <span id="shortcutMsg" style="font-size:13px;color:#27ae60;line-height:36px;"></span>
  </div>
</div>

<script>
let currentTab = 'stats';
let allHospitals = [];
let editCode = '';
let editAliases = [];

// ===== 登入 =====
async function doLogin() {
  const u = document.getElementById('username').value;
  const p = document.getElementById('password').value;
  const err = document.getElementById('loginError');
  err.textContent = '';
  try {
    const r = await fetch('/admin/api/login', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: u, password: p})
    });
    const d = await r.json();
    if (d.ok) {
      document.getElementById('loginOverlay').style.display = 'none';
      document.getElementById('mainHeader').style.display = '';
      switchTab('stats');
    } else {
      err.textContent = d.error || '登入失敗';
    }
  } catch(e) { err.textContent = '連線失敗'; }
}
document.getElementById('password').addEventListener('keydown', e => { if(e.key==='Enter') doLogin(); });
document.getElementById('username').addEventListener('keydown', e => { if(e.key==='Enter') document.getElementById('password').focus(); });

async function doLogout() {
  await fetch('/admin/api/logout', {method:'POST'});
  location.reload();
}

// ===== 切頁 =====
function switchTab(tab) {
  currentTab = tab;
  for (const p of ['Stats','Hospitals','Shortcuts','Feedback','Test','Live']) {
    document.getElementById('page'+p).classList.toggle('hidden', tab !== p.toLowerCase());
    document.getElementById('tab'+p).classList.toggle('active', tab === p.toLowerCase());
  }
  if (tab === 'stats') loadStats();
  if (tab === 'hospitals') loadHospitals();
  if (tab === 'shortcuts') loadShortcuts();
  if (tab === 'feedback') loadFeedback();
  if (tab === 'test') loadTestEnv();
  if (tab === 'live') checkLiveTest();
}

// ===== 統計 =====
async function loadStats() {
  try {
    const r = await fetch('/admin/api/stats');
    if (r.status === 401) { location.reload(); return; }
    const d = await r.json();
    const cards = [
      {num: d.total_hospitals, label: '全部醫院'},
      {num: d.active_hospitals, label: '已啟用'},
      {num: d.adapter_count, label: 'Adapter 數'},
      {num: d.total_users, label: '用戶數'},
      {num: d.active_tracks, label: '進行中追蹤'},
      {num: d.total_tracks, label: '累計追蹤'},
    ];
    document.getElementById('statCards').innerHTML = cards.map(c =>
      `<div class="stat-card"><div class="num">${c.num}</div><div class="label">${c.label}</div></div>`
    ).join('');
  } catch(e) {}
}

// ===== 醫院 =====
let sortKey = '';
let sortAsc = true;
let filteredHospitals = [];

async function loadHospitals() {
  try {
    const r = await fetch('/admin/api/hospitals');
    if (r.status === 401) { location.reload(); return; }
    allHospitals = await r.json();
    buildFilterOptions();
    applyFilters();
  } catch(e) {}
}

function buildFilterOptions() {
  const cities = [...new Set(allHospitals.map(h => h.city))];
  cities.sort((a, b) => {
    const ra = cityRank(a), rb = cityRank(b);
    if (ra !== rb) return ra - rb;
    return a.localeCompare(b, 'zh-Hant-TW');
  });
  const cityEl = document.getElementById('filterCity');
  cityEl.innerHTML = '<option value="">全部縣市</option>' +
    cities.map(c => `<option value="${c}">${c}</option>`).join('');
}

function updateDistrictOptions() {
  const city = document.getElementById('filterCity').value;
  const distEl = document.getElementById('filterDistrict');
  if (!city) {
    distEl.innerHTML = '<option value="">全部區</option>';
    return;
  }
  const districts = [...new Set(allHospitals.filter(h => h.city === city).map(h => h.district))].sort();
  distEl.innerHTML = '<option value="">全部區</option>' +
    districts.map(d => `<option value="${d}">${d}</option>`).join('');
}

document.getElementById('filterCity').addEventListener('change', () => {
  updateDistrictOptions();
  applyFilters();
});

function applyFilters() {
  const q = document.getElementById('hospitalSearch').value.toLowerCase();
  const city = document.getElementById('filterCity').value;
  const district = document.getElementById('filterDistrict').value;
  const level = document.getElementById('filterLevel').value;
  const status = document.getElementById('filterStatus').value;

  filteredHospitals = allHospitals.filter(h => {
    if (q && !(h.code + h.name + h.short_name + h.city + h.district + (h.adapter_name||'') + h.aliases.join(' ')).toLowerCase().includes(q)) return false;
    if (city && h.city !== city) return false;
    if (district && h.district !== district) return false;
    if (level && h.level !== level) return false;
    if (status === 'active' && !h.is_active) return false;
    if (status === 'inactive' && h.is_active) return false;
    return true;
  });

  if (sortKey) doSort();
  renderHospitals(filteredHospitals);
  document.getElementById('filterCount').textContent = `${filteredHospitals.length} / ${allHospitals.length}`;
}

function sortBy(key) {
  if (sortKey === key) {
    sortAsc = !sortAsc;
  } else {
    sortKey = key;
    sortAsc = true;
  }
  // 更新箭頭
  for (const el of document.querySelectorAll('th.sortable span')) el.textContent = '';
  const arrow = sortAsc ? '▲' : '▼';
  const spanEl = document.getElementById('sort_' + key);
  if (spanEl) spanEl.textContent = arrow;

  doSort();
  renderHospitals(filteredHospitals);
}

const CITY_ORDER = ['臺北市','新北市','桃園市','基隆市','臺中市','高雄市','臺南市','宜蘭縣'];
function cityRank(c) { const i = CITY_ORDER.indexOf(c); return i >= 0 ? i : 100; }

function doSort() {
  const cmp = (a, b) => {
    let va, vb;
    switch (sortKey) {
      case 'code': va = a.code; vb = b.code; break;
      case 'level': va = a.level === '醫學中心' ? '0' : '1'; vb = b.level === '醫學中心' ? '0' : '1'; break;
      case 'city': {
        const ra = cityRank(a.city), rb = cityRank(b.city);
        if (ra !== rb) return sortAsc ? ra - rb : rb - ra;
        va = a.city; vb = b.city; break;
      }
      case 'district': va = a.district; vb = b.district; break;
      case 'adapter': va = a.adapter_name || 'zzz'; vb = b.adapter_name || 'zzz'; break;
      case 'status': va = a.is_active ? '0' : '1'; vb = b.is_active ? '0' : '1'; break;
      default: return 0;
    }
    if (va < vb) return sortAsc ? -1 : 1;
    if (va > vb) return sortAsc ? 1 : -1;
    return 0;
  };
  filteredHospitals.sort(cmp);
}

function renderHospitals(list) {
  document.getElementById('hospitalBody').innerHTML = list.map((h, i) => {
    const status = h.is_active
      ? `<span class="badge badge-green toggle" onclick="toggleHospital('${h.code}',false)">啟用</span>`
      : `<span class="badge badge-gray toggle" onclick="toggleHospital('${h.code}',true)">未啟用</span>`;
    const adapter = h.adapter_name
      ? `<span class="badge badge-blue">${h.adapter_name}</span>`
      : '<span class="badge badge-red">未接入</span>';
    const level = h.level === '醫學中心'
      ? '<span class="badge badge-blue">醫學中心</span>'
      : '<span class="badge badge-gray">區域醫院</span>';
    const aliasStr = h.aliases.length
      ? `<div class="alias-list">${h.aliases.join(', ')}</div>`
      : '';
    return `<tr>
      <td>${i+1}</td>
      <td><code>${h.code}</code></td>
      <td class="clickable" onclick="openEdit('${h.code}')">
        ${h.short_name}${aliasStr}
      </td>
      <td>${level}</td>
      <td>${h.city}</td>
      <td>${h.district}</td>
      <td>${h.nhi_code || '<span style="color:#ccc">待查</span>'}</td>
      <td>${adapter}</td>
      <td>${status}</td>
      <td>${h.phone || ''}</td>
    </tr>`;
  }).join('');
}

// ===== 醫院開關 =====
async function toggleHospital(code, active) {
  try {
    const r = await fetch(`/admin/api/hospitals/${code}/toggle`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({is_active: active})
    });
    if (r.status === 401) { location.reload(); return; }
    const d = await r.json();
    if (d.ok) {
      // 更新本地資料
      const h = allHospitals.find(x => x.code === code);
      if (h) h.is_active = active;
      applyFilters();
    }
  } catch(e) {}
}

// ===== 編輯別名 =====
function openEdit(code) {
  const h = allHospitals.find(x => x.code === code);
  if (!h) return;
  editCode = code;
  editAliases = [...h.aliases];
  document.getElementById('editTitle').textContent = `編輯: ${h.name}`;
  document.getElementById('editShortName').value = h.short_name;
  document.getElementById('aliasInput').value = '';
  document.getElementById('editMsg').textContent = '';
  document.getElementById('editMsg').className = 'msg';
  renderAliasTags();
  document.getElementById('editOverlay').classList.remove('hidden');
  document.getElementById('editShortName').focus();
}

function closeEdit() {
  document.getElementById('editOverlay').classList.add('hidden');
}

function renderAliasTags() {
  document.getElementById('aliasTags').innerHTML = editAliases.map((a, i) =>
    `<span class="alias-tag">${a}<span class="x" onclick="removeAlias(${i})">x</span></span>`
  ).join('');
}

function removeAlias(idx) {
  editAliases.splice(idx, 1);
  renderAliasTags();
}

// Enter 新增別名
document.getElementById('aliasInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    const val = this.value.trim();
    if (!val) return;
    // 支援逗號分隔一次貼入多個
    const parts = val.split(/[,，]/).map(s => s.trim()).filter(Boolean);
    for (const p of parts) {
      if (!editAliases.includes(p)) editAliases.push(p);
    }
    this.value = '';
    renderAliasTags();
  }
});

async function saveEdit() {
  const msg = document.getElementById('editMsg');
  const shortName = document.getElementById('editShortName').value.trim();
  // 把 input 裡還沒按 Enter 的也加進去
  const pending = document.getElementById('aliasInput').value.trim();
  if (pending) {
    pending.split(/[,，]/).map(s => s.trim()).filter(Boolean).forEach(p => {
      if (!editAliases.includes(p)) editAliases.push(p);
    });
  }
  msg.textContent = '儲存中...';
  msg.className = 'msg';
  try {
    const r = await fetch(`/admin/api/hospitals/${editCode}/aliases`, {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({short_name: shortName, aliases: editAliases.join(',')})
    });
    const d = await r.json();
    if (d.ok) {
      const shared = d.aliases_shared?.length ? ` (共用: ${d.aliases_shared.join(', ')})` : '';
      msg.textContent = `已儲存${shared}`;
      msg.className = 'msg ok';
      await loadHospitals();
      setTimeout(closeEdit, 800);
    } else {
      msg.textContent = d.error || '儲存失敗';
      msg.className = 'msg err';
    }
  } catch(e) {
    msg.textContent = '連線失敗';
    msg.className = 'msg err';
  }
}

// 自動檢查登入
(async () => {
  try {
    const r = await fetch('/admin/api/stats');
    if (r.ok) {
      document.getElementById('loginOverlay').style.display = 'none';
      document.getElementById('mainHeader').style.display = '';
      switchTab('stats');
    }
  } catch(e) {}
})();
// ===== 系統測試 =====
let _testStatusData = null;
let _lastTestData = null;
let _testReportsData = [];

let _testReportsSortAsc = false;
function sortTestReports() {
  if (!_testReportsData.length) return;
  _testReportsSortAsc = !_testReportsSortAsc;
  _testReportsData.sort((a, b) => {
    const aHas = (a.conversations && a.conversations.length > 0) ? 1 : 0;
    const bHas = (b.conversations && b.conversations.length > 0) ? 1 : 0;
    return _testReportsSortAsc ? aHas - bHas : bHas - aHas;
  });
  // re-render
  renderTestHistory(_testReportsData);
}

function renderTestHistory(reports) {
  const tbody = document.getElementById('testHistoryBody');
  if (!tbody) return;
  tbody.innerHTML = reports.map((r, ri) => {
    const failItems = (r.failed_items||[]).map(f => f.scenario+': '+f.input).join(', ');
    const hasConv = r.conversations && r.conversations.length > 0;
    return '<tr'+ ((r.failed_steps||r.failed||0)>0?' style="background:#fff5f5;"':'') +'>' +
      '<td style="padding:4px;">'+(r.id||'')+'</td>' +
      '<td style="white-space:nowrap">'+r.start_time+'</td>' +
      '<td style="white-space:nowrap">'+r.end_time+'</td>' +
      '<td>'+r.session_hint+'</td>' +
      '<td style="font-size:11px">'+(r.hospitals_with_data||'')+'家</td>' +
      '<td style="color:green;">✅'+(r.passed_steps||r.passed||0)+'</td>' +
      '<td style="color:'+((r.failed_steps||r.failed||0)>0?'red':'gray')+';">'+((r.failed_steps||r.failed||0)>0?'❌':'')+(r.failed_steps||r.failed||0)+'</td>' +
      '<td>'+(r.avg_step_time||r.avg_time||0)+'s</td>' +
      '<td style="font-size:11px;max-width:200px;word-break:break-all;">'+(failItems||'✅')+'</td>' +
      '<td>'+(hasConv?'<button onclick="showTestConv('+ri+')" style="padding:2px 8px;border:1px solid #4a90d9;border-radius:4px;background:#fff;color:#4a90d9;cursor:pointer;font-size:11px;">查看('+r.conversations.length+')</button>':'—')+'</td></tr>';
  }).join('');
}

function showTestConv(reportIdx) {
  const r = _testReportsData[reportIdx];
  if (!r || !r.conversations) return;
  const convs = r.conversations;
  let html = '';
  for (const c of convs) {
    const badge = c.passed ? '✅' : '❌';
    html += `<div style="margin-bottom:16px;">`;
    html += `<div style="text-align:center;margin:8px 0;"><span style="background:${c.passed?'#e8f5e9':'#ffebee'};padding:4px 16px;border-radius:12px;font-size:12px;font-weight:600;">${badge} ${c.scenario}</span></div>`;
    for (const s of c.steps) {
      const icon = s.ok ? '✅' : '❌';
      // 用戶訊息（右邊，綠色）
      html += `<div style="display:flex;justify-content:flex-end;margin:4px 0;">
        <div style="background:#DCF8C6;padding:8px 12px;border-radius:12px 12px 0 12px;max-width:75%;font-size:13px;word-break:break-all;">
          ${s.input}
          <div style="font-size:10px;color:#888;text-align:right;margin-top:2px;">${s.elapsed}s</div>
        </div>
      </div>`;
      // 系統回覆（左邊，白色）
      const replyBorder = s.ok ? '' : 'border:1px solid #ffcdd2;';
      html += `<div style="display:flex;justify-content:flex-start;margin:4px 0;">
        <div style="background:#fff;${replyBorder}padding:8px 12px;border-radius:12px 12px 12px 0;max-width:75%;font-size:13px;box-shadow:0 1px 2px rgba(0,0,0,.08);word-break:break-all;">
          ${s.reply.replace(/\\n/g,'<br>')}
          <div style="font-size:10px;color:#888;margin-top:2px;">${icon}</div>
        </div>
      </div>`;
    }
    html += `</div>`;
  }
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
  overlay.innerHTML = `<div style="background:#E5DDD5;border-radius:12px;max-width:500px;width:95%;max-height:90vh;overflow-y:auto;display:flex;flex-direction:column;">
    <div style="background:#075E54;color:#fff;padding:12px 16px;border-radius:12px 12px 0 0;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;">
      <b>測試對話 #${r.id} (${r.start_time})</b>
      <button onclick="this.closest('div[style*=fixed]').remove()" style="border:none;background:none;color:#fff;font-size:18px;cursor:pointer;">✕</button>
    </div>
    <div style="padding:12px;flex:1;">
      ${html}
    </div>
  </div>`;
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

async function loadTestEnv() {
  try {
    const r = await fetch('/admin/api/test/status');
    if (r.status === 401) { location.reload(); return; }
    const d = await r.json();
    _testStatusData = d;

    document.getElementById('testEnv').innerHTML =
      `🏥 有資料：${d.hospitals.length} 家，共 ${d.hospitals.reduce((a,h)=>a+h.rooms,0)} 個診間<br>` +
      `📋 可產生劇本：${d.total_scenarios} 個`;

    // 醫院勾選
    const list = document.getElementById('testHospitalList');
    list.innerHTML = d.hospitals.map(h =>
      `<label style="background:#fff;padding:2px 8px;border-radius:4px;border:1px solid #ddd;cursor:pointer;">` +
      `<input type="checkbox" class="test-hosp-cb" value="${h.name}" checked> ${h.name}(${h.rooms})</label>`
    ).join('');

    // 歷史
    const r2 = await fetch('/admin/api/test/reports');
    const reports = await r2.json();
    _testReportsData = reports;
    if (reports.length) {
      document.getElementById('testHistory').innerHTML =
        '<h3 style="font-size:14px;margin-bottom:8px;">歷史報告</h3>' +
        '<table style="width:100%;font-size:12px;border-collapse:collapse;"><thead><tr>' +
        '<th style="text-align:left;padding:4px;">#</th><th>開始</th><th>結束</th><th>時段</th><th>醫院</th><th>通過</th><th>失敗</th><th>均耗時</th><th>失敗項</th><th style="cursor:pointer" onclick="sortTestReports()">對話 ⇅</th></tr></thead><tbody id="testHistoryBody"></tbody></table>';
      renderTestHistory(reports);
    }
    checkScheduleStatus();
  } catch(e) { console.error(e); }
}

function toggleAllHospitals() {
  const checked = document.getElementById('testAllHospitals').checked;
  document.querySelectorAll('.test-hosp-cb').forEach(cb => cb.checked = checked);
}

function filterTestResults() {
  if (!_lastTestData) return;
  renderTestResults(_lastTestData);
}

function renderTestResults(d) {
  const onlyFails = document.getElementById('testShowOnlyFails').checked;
  let rowIdx = 0;
  const rows = [];
  d.results.forEach(r => {
    r.steps.forEach((s, si) => {
      rowIdx++;
      if (onlyFails && s.ok) return;
      const bg = s.ok ? '' : 'background:#fff5f5;';
      const badge = s.ok ? '<span class="badge badge-green">✅</span>' : '<span class="badge badge-red">❌</span>';
      rows.push(`<tr style="${bg}">
        <td>${rowIdx}</td>
        <td>${r.scenario}</td>
        <td>${si+1}/${r.steps.length}</td>
        <td><code>${s.input}</code></td>
        <td>${badge}</td>
        <td>${s.elapsed}s</td>
        <td style="font-size:11px;max-width:300px;word-break:break-all;">${s.reply_preview || ''}</td>
      </tr>`);
    });
  });
  document.getElementById('testBody').innerHTML = rows.join('');
}

async function runTest() {
  const btn = document.getElementById('btnRunTest');
  btn.disabled = true;
  document.getElementById('testRunning').style.display = 'inline';
  document.getElementById('testReport').style.display = 'none';

  // 收集參數
  const selectedHospitals = [...document.querySelectorAll('.test-hosp-cb:checked')].map(cb => cb.value);
  const selectedTypes = [...document.querySelectorAll('#testScenarioTypes input:checked')].map(cb => cb.value);
  const usersPerScenario = parseInt(document.getElementById('testUsersPerScenario').value);
  const maxConcurrent = parseInt(document.getElementById('testMaxConcurrent').value);

  try {
    const r = await fetch('/admin/api/test/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        hospitals: selectedHospitals,
        scenario_types: selectedTypes,
        users_per_scenario: usersPerScenario,
        max_concurrent: maxConcurrent,
      }),
    });
    const d = await r.json();
    _lastTestData = d;
    if (d.error) { alert(d.error); return; }

    // Summary cards
    const cards = [
      {num: `${d.start_time}`, label: '開始時間', color: '#333'},
      {num: `${d.end_time}`, label: '結束時間', color: '#333'},
      {num: `${d.total_elapsed}s`, label: '總耗時', color: '#4a90d9'},
      {num: d.session_hint, label: '時段', color: '#888'},
      {num: `${d.passed_steps}/${d.total_steps}`, label: '通過/總步驟', color: '#27ae60'},
      {num: `${d.failed_steps}`, label: '失敗', color: d.failed_steps > 0 ? '#e74c3c' : '#27ae60'},
      {num: `${d.avg_step_time}s`, label: '平均耗時/步', color: '#4a90d9'},
      {num: d.data_summary, label: 'Redis 資料', color: '#888'},
    ];
    document.getElementById('testSummary').innerHTML = cards.map(c =>
      `<div class="stat-card"><div class="num" style="font-size:18px;color:${c.color}">${c.num}</div><div class="label">${c.label}</div></div>`
    ).join('');

    // Failed steps highlight
    const fails = [];
    d.results.forEach(r => r.steps.forEach(s => { if (!s.ok) fails.push({...s, scenario: r.scenario}); }));
    if (fails.length) {
      document.getElementById('testFails').innerHTML =
        '<div style="background:#fff5f5;border:1px solid #fcc;border-radius:8px;padding:12px;margin-bottom:8px;">' +
        '<b style="color:#e74c3c;">❌ 失敗項目</b><br>' +
        fails.map(f => `<div style="margin-top:6px;font-size:13px;">
          <b>${f.scenario}</b> → 輸入「${f.input}」<br>
          預期含：${f.expected.join('/')}<br>
          實際：${f.reply_preview}
        </div>`).join('<hr style="margin:4px 0;">') + '</div>';
    } else {
      document.getElementById('testFails').innerHTML =
        '<div style="background:#f0fff0;border:1px solid #cfc;border-radius:8px;padding:12px;text-align:center;">✅ 全部通過！</div>';
    }

    renderTestResults(d);
    document.getElementById('testReport').style.display = 'block';
    loadTestEnv();
  } catch(e) {
    alert('測試執行失敗: ' + e.message);
  } finally {
    btn.disabled = false;
    document.getElementById('testRunning').style.display = 'none';
  }
}

function setTimePreset(preset) {
  const presets = {
    morning:   {start:'08:30', end:'12:00'},
    afternoon: {start:'13:30', end:'17:00'},
    night:     {start:'18:00', end:'21:00'},
  };
  const p = presets[preset];
  if (p) {
    document.getElementById('testStartTime').value = p.start;
    document.getElementById('testEndTime').value = p.end;
  }
}

function _getTestParams() {
  return {
    hospitals: [...document.querySelectorAll('.test-hosp-cb:checked')].map(cb => cb.value),
    scenario_types: [...document.querySelectorAll('#testScenarioTypes input:checked')].map(cb => cb.value),
    test_mode: document.querySelector('input[name=testMode]:checked')?.value || 'standard',
    random_count: parseInt(document.getElementById('testRandomCount').value),
    users_per_scenario: 1,
    max_concurrent: parseInt(document.getElementById('testMaxConcurrent').value),
    start_time: document.getElementById('testStartTime').value,
    end_time: document.getElementById('testEndTime').value,
    interval_minutes: parseInt(document.getElementById('testInterval').value),
  };
}

async function scheduleTest() {
  const params = _getTestParams();
  try {
    const r = await fetch('/admin/api/test/schedule', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(params),
    });
    const d = await r.json();
    if (d.ok) {
      document.getElementById('scheduleStatus').textContent = `✅ 已排程：${params.start_time} ~ ${params.end_time}，每 ${params.interval_minutes} 分鐘`;
      document.getElementById('btnCancelSchedule').style.display = 'inline';
      loadTestEnv();
    } else {
      alert(d.error || '排程失敗');
    }
  } catch(e) { alert('排程失敗: ' + e.message); }
}

async function cancelSchedule() {
  try {
    await fetch('/admin/api/test/schedule', {method:'DELETE'});
    document.getElementById('scheduleStatus').textContent = '已取消排程';
    document.getElementById('btnCancelSchedule').style.display = 'none';
    setTimeout(() => document.getElementById('scheduleStatus').textContent = '', 3000);
  } catch(e) {}
}

// 檢查排程狀態
async function checkScheduleStatus() {
  try {
    const r = await fetch('/admin/api/test/schedule');
    const d = await r.json();
    if (d.active) {
      document.getElementById('scheduleStatus').textContent =
        `⏰ 排程中：${d.start_time} ~ ${d.end_time}，每 ${d.interval}分，已跑 ${d.runs_done} 次`;
      document.getElementById('btnCancelSchedule').style.display = 'inline';
    }
  } catch(e) {}
}

// ===== 即時追蹤測試 =====
let _liveAutoRefresh = null;

async function startLiveTest() {
  try {
    const r = await fetch('/admin/api/test/live/start', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        count: parseInt(document.getElementById('liveCount').value),
        offset: parseInt(document.getElementById('liveOffset').value),
        notify_mode: document.getElementById('liveMode').value,
      }),
    });
    const d = await r.json();
    if (d.error) { alert(d.error); return; }
    renderLiveTest(d);
    document.getElementById('btnLiveStop').style.display = 'inline';
    // 每 30 秒自動刷新
    if (_liveAutoRefresh) clearInterval(_liveAutoRefresh);
    _liveAutoRefresh = setInterval(checkLiveTest, 30000);
  } catch(e) { alert(e.message); }
}

async function checkLiveTest() {
  try {
    const r = await fetch('/admin/api/test/live/check', {method:'POST'});
    const d = await r.json();
    renderLiveTest(d);
    if (d.status === 'completed' || d.status === 'stopped' || d.status === 'idle') {
      if (_liveAutoRefresh) { clearInterval(_liveAutoRefresh); _liveAutoRefresh = null; }
      document.getElementById('btnLiveStop').style.display = 'none';
    } else {
      document.getElementById('btnLiveStop').style.display = 'inline';
      if (!_liveAutoRefresh) _liveAutoRefresh = setInterval(checkLiveTest, 30000);
    }
  } catch(e) {}
}

async function stopLiveTest() {
  if (!confirm('確定停止即時測試？')) return;
  await fetch('/admin/api/test/live/stop', {method:'POST'});
  if (_liveAutoRefresh) { clearInterval(_liveAutoRefresh); _liveAutoRefresh = null; }
  document.getElementById('btnLiveStop').style.display = 'none';
  checkLiveTest();
}

function renderLiveTest(d) {
  const statusMap = {ACTIVE:'⏳ 追蹤中', NOTIFIED:'✅ 已通知', CANCELLED:'🚫 取消', completed:'✅ 完成', stopped:'⏹ 已停止', idle:'💤 閒置', running:'🔄 進行中'};
  document.getElementById('liveStatus').innerHTML =
    `狀態：<b>${statusMap[d.status]||d.status}</b>` +
    (d.started_at ? ` ｜ 開始：${d.started_at}` : '') +
    (d.completed_at ? ` ｜ 完成：${d.completed_at}` : '') +
    (d.stopped_at ? ` ｜ 停止：${d.stopped_at}` : '');

  const tbody = document.getElementById('liveBody');
  const tasks = d.tasks || [];
  if (!tasks.length) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#888;padding:20px;">尚無追蹤任務</td></tr>';
    return;
  }
  tbody.innerHTML = tasks.map(t => {
    const st = t.status || 'ACTIVE';
    const stBadge = st === 'NOTIFIED' ? '<span class="badge badge-green">✅ 已通知</span>'
      : st === 'ACTIVE' ? '<span class="badge badge-blue">⏳ 追蹤中</span>'
      : '<span class="badge badge-gray">' + st + '</span>';
    const remaining = t.remaining !== undefined && t.remaining !== '?' ? t.remaining : '?';
    const curNow = t.current_now !== undefined ? t.current_now : '?';
    const rowBg = st === 'NOTIFIED' ? 'background:#f0fff0;' : remaining !== '?' && remaining <= 0 ? 'background:#fff5f5;' : '';
    return `<tr style="${rowBg}">
      <td>${t.hospital}</td>
      <td>${t.department}</td>
      <td>${t.doctor}</td>
      <td>${t.room||'-'}</td>
      <td>${t.session||'-'}</td>
      <td><b>${t.user_number}號</b></td>
      <td>${t.start_current}號</td>
      <td><b>${curNow}${curNow !== '?' && curNow !== 'N/A' ? '號' : ''}</b></td>
      <td>${remaining}</td>
      <td>${stBadge}</td>
    </tr>`;
  }).join('');
}

// ===== 對話記錄 Modal =====
function showConvLog(logJson, feedbackId) {
  try {
    const logs = typeof logJson === 'string' ? JSON.parse(logJson) : logJson;
    if (!logs || !logs.length) {
      alert('此追蹤無對話記錄');
      return;
    }
    const roleLabels = {user:'👤 用戶', system:'🤖 系統', notify:'🔔 通知'};
    const roleColors = {user:'#e3f2fd', system:'#f5f5f5', notify:'#fff8e1'};
    const html = logs.map(e => {
      const label = roleLabels[e.role] || e.role;
      const bg = roleColors[e.role] || '#fff';
      return `<div style="margin:4px 0;padding:6px 10px;background:${bg};border-radius:6px;font-size:13px;">
        <span style="color:#888;font-size:11px;">${e.time || ''}</span> <b>${label}</b><br>
        <span style="white-space:pre-wrap;">${e.message}</span>
      </div>`;
    }).join('');
    // Simple modal
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = `<div style="background:#fff;border-radius:12px;padding:20px;max-width:500px;width:90%;max-height:80vh;overflow-y:auto;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <b>對話記錄 #${feedbackId}</b>
        <button onclick="this.closest('div[style*=fixed]').remove()" style="border:none;background:none;font-size:18px;cursor:pointer;">✕</button>
      </div>
      ${html}
    </div>`;
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  } catch(e) { alert('解析對話記錄失敗'); }
}

// ===== 回饋記錄 =====
async function loadFeedback() {
  try {
    const r = await fetch('/admin/api/feedbacks');
    if (r.status === 401) { location.reload(); return; }
    const data = await r.json();
    const tbody = document.getElementById('feedbackBody');
    const total = data.length;
    const errors = data.filter(f => f.is_correct === false).length;
    const correct = data.filter(f => f.is_correct === true).length;
    const pending = data.filter(f => f.is_correct === null).length;
    document.getElementById('feedbackStats').textContent =
      `共 ${total} 筆｜✅ ${correct} 正確｜❌ ${errors} 有誤｜⏳ ${pending} 未回饋`;

    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;color:#888;padding:20px;">尚無回饋記錄</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(f => {
      let badge = '';
      if (f.is_correct === true) badge = '<span class="badge badge-green">✅ 正確</span>';
      else if (f.is_correct === false) badge = '<span class="badge badge-red">❌ 有誤</span>';
      else badge = '<span class="badge badge-gray">⏳ 未回饋</span>';
      const detail = f.doctor_name ? `${f.department}<br>${f.doctor_name}` : f.department;
      const session = f.session ? `<br><small>${f.session}</small>` : '';
      return `<tr${f.is_correct === false ? ' style="background:#fff5f5;"' : ''}>
        <td style="font-size:11px;">${f.line_user_id}</td>
        <td style="white-space:nowrap">${f.track_created_at || '-'}</td>
        <td>${f.hospital}${session}</td>
        <td>${detail}</td>
        <td>${f.clinic_room || '-'}</td>
        <td>${f.user_number}號</td>
        <td>${f.final_current}號</td>
        <td>${f.end_reason || '-'}</td>
        <td style="text-align:center">${f.notify_count || 0}</td>
        <td>${badge}</td>
        <td style="max-width:200px;word-break:break-all;">${f.user_comment || '-'}</td>
        <td><button onclick='showConvLog(${JSON.stringify(f.conversation_log)}, ${f.id})' style="padding:2px 8px;border:1px solid #4a90d9;border-radius:4px;background:#fff;color:#4a90d9;cursor:pointer;font-size:11px;">查看</button></td>
      </tr>`;
    }).join('');
  } catch(e) { console.error(e); }
}

// ===== 快捷指令 =====
let shortcuts = [];

async function loadShortcuts() {
  try {
    const r = await fetch('/admin/api/shortcuts');
    if (r.status === 401) { location.reload(); return; }
    shortcuts = await r.json();
    renderShortcuts();
  } catch(e) {}
}

function renderShortcuts() {
  const tbody = document.getElementById('shortcutBody');
  if (!shortcuts.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888;padding:20px;">尚無快捷指令</td></tr>';
    return;
  }
  tbody.innerHTML = shortcuts.map((s, i) => `<tr>
    <td>${i+1}</td>
    <td><input value="${s.trigger||''}" onchange="shortcuts[${i}].trigger=this.value" placeholder="h, help, 說明" style="width:100%;padding:4px 8px;border:1px solid #ddd;border-radius:4px;font-size:13px;"></td>
    <td><input value="${s.action||''}" onchange="shortcuts[${i}].action=this.value" style="width:100%;padding:4px 8px;border:1px solid #ddd;border-radius:4px;font-size:13px;"></td>
    <td><input value="${s.label||''}" onchange="shortcuts[${i}].label=this.value" style="width:100%;padding:4px 8px;border:1px solid #ddd;border-radius:4px;font-size:13px;"></td>
    <td><input value="${s.description||''}" onchange="shortcuts[${i}].description=this.value" style="width:100%;padding:4px 8px;border:1px solid #ddd;border-radius:4px;font-size:13px;"></td>
    <td><button onclick="removeShortcut(${i})" style="padding:4px 10px;border:1px solid #e74c3c;border-radius:4px;background:#fff;color:#e74c3c;cursor:pointer;font-size:12px;">刪除</button></td>
  </tr>`).join('');
}

function addShortcut() {
  shortcuts.push({trigger:'', action:'', label:'', description:''});
  renderShortcuts();
  // focus last trigger input
  const inputs = document.querySelectorAll('#shortcutBody input');
  if (inputs.length) inputs[inputs.length - 4].focus();
}

function removeShortcut(i) {
  shortcuts.splice(i, 1);
  renderShortcuts();
}

async function saveShortcuts() {
  // filter empty triggers
  const valid = shortcuts.filter(s => s.trigger && s.action);
  try {
    const r = await fetch('/admin/api/shortcuts', {
      method: 'PUT',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(valid),
    });
    const d = await r.json();
    if (d.ok) {
      shortcuts = valid;
      renderShortcuts();
      const msg = document.getElementById('shortcutMsg');
      msg.textContent = `已儲存 ${d.count} 筆快捷指令`;
      setTimeout(() => msg.textContent = '', 3000);
    }
  } catch(e) {}
}

async function resetShortcuts() {
  if (!confirm('確定恢復為預設快捷指令？')) return;
  try {
    const r = await fetch('/admin/api/shortcuts/reset', {method:'POST'});
    const d = await r.json();
    if (d.ok) {
      shortcuts = d.shortcuts;
      renderShortcuts();
      const msg = document.getElementById('shortcutMsg');
      msg.textContent = '已恢復預設';
      setTimeout(() => msg.textContent = '', 3000);
    }
  } catch(e) {}
}
</script>
</body>
</html>"""
