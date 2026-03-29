"""後台管理路由 — 登入彈框 + 統計 + 醫院管理"""

import secrets
from fastapi import APIRouter, Request, Cookie
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])

_active_tokens: set[str] = set()


def _check_auth(token: str | None) -> bool:
    return token is not None and token in _active_tokens


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
        token = secrets.token_urlsafe(32)
        _active_tokens.add(token)
        resp = JSONResponse({"ok": True})
        resp.set_cookie("admin_token", token, httponly=True, samesite="strict", max_age=86400)
        return resp
    return JSONResponse({"ok": False, "error": "帳號或密碼錯誤"}, status_code=401)


@router.post("/api/logout")
async def api_logout(admin_token: str | None = Cookie(None)):
    _active_tokens.discard(admin_token)
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


@router.get("/api/hospitals")
async def api_hospitals(admin_token: str | None = Cookie(None)):
    if not _check_auth(admin_token):
        return JSONResponse({"error": "未登入"}, status_code=401)

    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.hospital import Hospital
    from app.models.hospital_alias import HospitalAlias

    async with async_session() as session:
        result = await session.execute(
            select(Hospital).order_by(Hospital.level, Hospital.city, Hospital.id)
        )
        hospitals = result.scalars().all()

        # 取所有別名
        alias_result = await session.execute(select(HospitalAlias))
        all_aliases = alias_result.scalars().all()

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

        # 寫入新別名
        added = []
        skipped = []
        for alias in new_aliases:
            # 檢查別名是否已被其他醫院佔用
            existing = await session.execute(
                select(HospitalAlias).where(
                    HospitalAlias.alias == alias,
                    HospitalAlias.hospital_code != code,
                )
            )
            if existing.scalar_one_or_none():
                skipped.append(alias)
                continue
            session.add(HospitalAlias(hospital_code=code, alias=alias))
            added.append(alias)

        await session.commit()

    return {
        "ok": True,
        "code": code,
        "short_name": new_short_name or hospital.short_name,
        "aliases_added": added,
        "aliases_skipped": skipped,
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

.container { max-width:1200px; margin:20px auto; padding:0 16px; }
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

.search-bar { margin-bottom:16px; }
.search-bar input { width:100%; max-width:400px; padding:8px 12px; border:1px solid #ddd; border-radius:6px; font-size:14px; }

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
    <button class="logout" onclick="doLogout()">登出</button>
  </div>
</div>

<!-- 統計頁 -->
<div class="container hidden" id="pageStats">
  <div class="stat-grid" id="statCards"></div>
</div>

<!-- 醫院頁 -->
<div class="container hidden" id="pageHospitals">
  <div class="search-bar">
    <input type="text" id="hospitalSearch" placeholder="搜尋醫院名稱、代碼、縣市、別名..." oninput="filterHospitals()">
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th><th>code</th><th>簡稱 / 別名</th><th>層級</th><th>縣市</th><th>區</th>
          <th>健保代碼</th><th>Adapter</th><th>狀態</th><th>電話</th>
        </tr>
      </thead>
      <tbody id="hospitalBody"></tbody>
    </table>
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
  document.getElementById('pageStats').classList.toggle('hidden', tab !== 'stats');
  document.getElementById('pageHospitals').classList.toggle('hidden', tab !== 'hospitals');
  document.getElementById('tabStats').classList.toggle('active', tab === 'stats');
  document.getElementById('tabHospitals').classList.toggle('active', tab === 'hospitals');
  if (tab === 'stats') loadStats();
  if (tab === 'hospitals') loadHospitals();
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
async function loadHospitals() {
  try {
    const r = await fetch('/admin/api/hospitals');
    if (r.status === 401) { location.reload(); return; }
    allHospitals = await r.json();
    renderHospitals(allHospitals);
  } catch(e) {}
}

function renderHospitals(list) {
  document.getElementById('hospitalBody').innerHTML = list.map((h, i) => {
    const status = h.is_active
      ? '<span class="badge badge-green">啟用</span>'
      : '<span class="badge badge-gray">未啟用</span>';
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

function filterHospitals() {
  const q = document.getElementById('hospitalSearch').value.toLowerCase();
  if (!q) { renderHospitals(allHospitals); return; }
  renderHospitals(allHospitals.filter(h =>
    (h.code + h.name + h.short_name + h.city + h.district + h.level
     + (h.adapter_name||'') + h.aliases.join(' ')).toLowerCase().includes(q)
  ));
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
      const skipped = d.aliases_skipped?.length ? ` (已被佔用: ${d.aliases_skipped.join(', ')})` : '';
      msg.textContent = `已儲存${skipped}`;
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
</script>
</body>
</html>"""
