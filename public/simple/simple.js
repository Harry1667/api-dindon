// 叮咚到號 · /simple 共用邏輯（長輩版）

const API = '';  // same origin

// ---- 醫院代碼分區（hardcoded，因後端 API 無 region 欄位）----
const REGIONS = {
  north: [
    'ntuh','tsgh','tpvgh','changgung-taipei','mackay-taipei','cathay','shinkong',
    'ntuh-cancer','ntuh-children','chgh','femh','tzuchi-taipei',
    'mackay-tamsui','tph','cathay-xizhi','changgung-tucheng',
    'newtaipei-banqiao','newtaipei-sanchong','fjuh',
    'changgung-keelung','changgung-linkou','changgung-taoyuan','wanfang',
  ],
  central: ['tcvgh','fyh-mohw','changgung-yunlin','changgung-chiayi'],
  south:   ['changgung-kaohsiung','changgung-fengshan','kaohsiung-united'],
};
const REGION_LABELS = { north: '北部', central: '中部', south: '南部' };

// 粗略位置（補顯示用；API 沒返回地址）
const HOSPITAL_LOC = {
  'ntuh': '台北 中正區',
  'tsgh': '台北 內湖區',
  'tpvgh': '台北 北投區',
  'changgung-taipei': '台北 松山區',
  'mackay-taipei': '台北 中山區',
  'cathay': '台北 大安區',
  'shinkong': '台北 士林區',
  'ntuh-cancer': '台北 大安區',
  'ntuh-children': '台北 中正區',
  'chgh': '台北 北投區',
  'femh': '新北 板橋區',
  'tzuchi-taipei': '新北 新店區',
  'mackay-tamsui': '新北 淡水區',
  'tph': '新北 新莊區',
  'cathay-xizhi': '新北 汐止區',
  'changgung-tucheng': '新北 土城區',
  'newtaipei-banqiao': '新北 板橋區',
  'newtaipei-sanchong': '新北 三重區',
  'fjuh': '新北 泰山區',
  'changgung-keelung': '基隆 安樂區',
  'changgung-linkou': '桃園 龜山區',
  'changgung-taoyuan': '桃園 龜山區',
  'wanfang': '台北 文山區',
  'tcvgh': '台中 西屯區',
  'fyh-mohw': '台中 豐原區',
  'changgung-yunlin': '雲林 麥寮鄉',
  'changgung-chiayi': '嘉義 朴子市',
  'changgung-kaohsiung': '高雄 鳥松區',
  'changgung-fengshan': '高雄 鳳山區',
  'kaohsiung-united': '高雄 鼓山區',
};

function regionOf(code) {
  if (REGIONS.north.includes(code))   return 'north';
  if (REGIONS.central.includes(code)) return 'central';
  if (REGIONS.south.includes(code))   return 'south';
  return 'other';
}

// ---- 虛擬醫院拆分（同一 hospital_code 分多院區顯示，API 仍用原 code）----
const HOSPITAL_SPLITS = {
  'tsgh': [
    { vid: 'tsgh:內湖',   main: '三軍總醫院', branch: '內湖本院', prefix: '內湖',   loc: '台北 內湖區' },
    { vid: 'tsgh:汀州',   main: '三軍總醫院', branch: '汀州院區', prefix: '汀州',   loc: '台北 中正區' },
    { vid: 'tsgh:台北門', main: '三軍總醫院', branch: '台北門診', prefix: '台北門', loc: '台北 大安區' },
  ],
};
function expandHospitals(list) {
  const out = [];
  for (const h of list) {
    const splits = HOSPITAL_SPLITS[h.code];
    if (splits) {
      for (const s of splits) {
        out.push({
          code: h.code, vid: s.vid,
          name: s.main, branch: s.branch,
          fullName: `${s.main} ${s.branch}`,
          loc: s.loc, branch_prefix: s.prefix,
        });
      }
    } else {
      out.push({
        code: h.code, vid: h.code,
        name: h.name, branch: '', fullName: h.name,
        loc: HOSPITAL_LOC[h.code] || '',
      });
    }
  }
  return out;
}

// ---- State helpers (sessionStorage for current tracking setup flow) ----
const S = {
  get(k, d) { try { return JSON.parse(sessionStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { sessionStorage.setItem(k, JSON.stringify(v)); },
  clear() { sessionStorage.removeItem('simple_setup'); },
};
const L = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { localStorage.setItem(k, JSON.stringify(v)); },
};

function getSetup() { return S.get('simple_setup', {}); }
function saveSetup(patch) { S.set('simple_setup', { ...getSetup(), ...patch }); }

// ---- 點擊次數記錄（給自動排序用；純前端 localStorage）----
function _picks() { return L.get('dd_pick_count', { hospitals: {}, depts: {} }); }
function bumpPick(kind, key, subKey) {
  const data = _picks();
  if (kind === 'hospital') {
    data.hospitals[key] = (data.hospitals[key] || 0) + 1;
  } else if (kind === 'dept') {
    data.depts[key] = data.depts[key] || {};
    data.depts[key][subKey] = (data.depts[key][subKey] || 0) + 1;
  }
  L.set('dd_pick_count', data);
}
function sortByPick(items, countFn) {
  // 穩定排序：次數多的靠前，次數相同維持原順序
  return items
    .map((item, idx) => ({ item, idx, n: countFn(item) || 0 }))
    .sort((a, b) => (b.n - a.n) || (a.idx - b.idx))
    .map(x => x.item);
}
function pickCount(kind, key, subKey) {
  const data = _picks();
  if (kind === 'hospital') return data.hospitals[key] || 0;
  if (kind === 'dept') return (data.depts[key] || {})[subKey] || 0;
  return 0;
}

// Guest ID（與 /chat 共用同一個 key）
function getGuestId() {
  let id = localStorage.getItem('dd_guest_id');
  if (!id) {
    id = 'g_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    localStorage.setItem('dd_guest_id', id);
  }
  return id;
}

// ==================== 訂閱層級 + 追蹤管理 ====================
// 層級：free 追 1、paid 追 3（純前端旗標，之後可綁後端）
function getTier() {
  // URL 參數 ?tier=paid 可快速切換並存起來
  const qs = new URLSearchParams(location.search);
  if (qs.get('tier')) {
    localStorage.setItem('dd_tier', qs.get('tier'));
  }
  return localStorage.getItem('dd_tier') || 'free';
}
function setTier(t) { localStorage.setItem('dd_tier', t); }
function getTrackLimit() { return getTier() === 'paid' ? 3 : 1; }

// 追蹤清單（array）。欄位：track_id, hospital_code, hospital_name, department,
// department_display, doctor_name, clinic_room, session, user_number, started_at
function getTracks() {
  let tracks = L.get('dd_tracks', null);
  // 相容舊版 dd_last_tracked（單筆 → 遷移到陣列）
  if (!tracks) {
    const old = L.get('dd_last_tracked', null);
    tracks = (old && old.hospital_code) ? [old] : [];
    L.set('dd_tracks', tracks);
  }
  return tracks;
}
function saveTracks(arr) { L.set('dd_tracks', arr); }

function addTrack(track) {
  const tracks = getTracks();
  // 相同 track_id 去重（重入同一個醫生視為更新）
  const filtered = tracks.filter(t => t.track_id !== track.track_id);
  filtered.push(track);
  saveTracks(filtered);
  // 同步寫入 dd_last_tracked（向下相容）
  L.set('dd_last_tracked', track);
}

function removeTrack(trackId) {
  const tracks = getTracks().filter(t => t.track_id !== trackId);
  saveTracks(tracks);
  const last = L.get('dd_last_tracked', null);
  if (last && last.track_id === trackId) {
    if (tracks.length) L.set('dd_last_tracked', tracks[tracks.length - 1]);
    else localStorage.removeItem('dd_last_tracked');
  }
}

function findTrack(trackId) {
  const id = parseInt(trackId);
  return getTracks().find(t => t.track_id === id) || null;
}

/* 移除過期追蹤（> 4 小時，跟 backend cleanup 對齊）*/
function pruneExpiredTracks() {
  const limit = 4 * 60 * 60 * 1000;
  const now = Date.now();
  const kept = getTracks().filter(t => t.started_at && (now - t.started_at) < limit);
  saveTracks(kept);
  return kept;
}

// ---- API wrappers ----
async function apiGet(path) {
  const r = await fetch(API + path, { headers: { 'Accept': 'application/json' } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
async function apiPost(path, body) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function fetchHospitals() {
  const d = await apiGet('/api/hospitals');
  return d.hospitals || [];
}
async function fetchHospitalStatus() {
  try {
    const d = await apiGet('/api/hospitals/status');
    return d.hospitals || {};
  } catch { return {}; }
}
async function fetchDepartments(code) {
  const d = await apiGet(`/api/departments/${code}`);
  return d.departments || [];
}
async function fetchProgress(code) {
  const d = await apiGet(`/api/progress/${code}`);
  return d.data || d.progress || [];
}

/* 統一比對邏輯：從進度清單找到符合本次追蹤設定的那筆
   優先級：
   1. doctor_name 完全相符 + clinic_room 相符
   2. doctor_name 完全相符
   3. clinic_room 相符（只在沒 doctor_name 時）
   4. department 包含相符（fallback）
*/
function findMatchingRoom(list, last) {
  if (!list || !list.length || !last) return null;
  const doc = last.doctor_name || '';
  const room = last.clinic_room || '';
  if (doc && room) {
    const both = list.find(r => r.doctor_name === doc && r.clinic_room === room);
    if (both) return both;
  }
  if (doc) {
    const docMatch = list.find(r => r.doctor_name === doc);
    if (docMatch) return docMatch;
  }
  if (room && !doc) {
    const roomMatch = list.find(r => r.clinic_room === room);
    if (roomMatch) return roomMatch;
  }
  if (last.department) {
    return list.find(r => (r.department || '').includes(last.department)) || null;
  }
  return null;
}

async function startTrack({ hospital_code, department, doctor_name, clinic_room, session, user_number }) {
  return apiPost('/api/track/start', {
    guest_id: getGuestId(),
    hospital_code, department, doctor_name, clinic_room, session, user_number,
  });
}

// ---- UI helpers ----
function toast(msg) {
  let t = document.querySelector('.toast');
  if (!t) { t = document.createElement('div'); t.className = 'toast'; document.body.appendChild(t); }
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove('show'), 2200);
}

function go(path) { location.href = path; }
function back() { history.length > 1 ? history.back() : go('/simple'); }

// ==================== 音效（WebAudio，零檔案）====================
let _audioCtx = null;
function _getAudio() {
  if (getSoundEnabled() === false) return null;
  if (!_audioCtx) {
    try { _audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch { return null; }
  }
  if (_audioCtx.state === 'suspended') _audioCtx.resume().catch(() => {});
  return _audioCtx;
}
function _beep(freq, dur, type = 'sine', vol = 0.15, delay = 0) {
  const ctx = _getAudio();
  if (!ctx) return;
  const t0 = ctx.currentTime + delay;
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = type; osc.frequency.value = freq;
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(vol, t0 + 0.005);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g).connect(ctx.destination);
  osc.start(t0); osc.stop(t0 + dur + 0.02);
}
function playTap()      { _beep(1800, 0.04, 'square',   0.05); }
function playBack()     { _beep(420,  0.10, 'triangle', 0.14); _beep(280, 0.12, 'triangle', 0.12, 0.05); }
function playSend()     { _beep(880,  0.08, 'sine',     0.10); }
function playDing()     { _beep(1320, 0.25, 'triangle', 0.18); }
function playDingDong() {
  _beep(1320, 0.22, 'triangle', 0.22, 0);
  _beep(990,  0.32, 'triangle', 0.22, 0.18);
}

function getSoundEnabled() {
  const v = localStorage.getItem('dd_sound');
  return v === null ? true : v === '1';   // 預設開
}
function setSoundEnabled(on) { localStorage.setItem('dd_sound', on ? '1' : '0'); }

// 全頁按鈕 tap 音：任何 button 點擊觸發（第一次點才會啟動 AudioContext）
document.addEventListener('click', (e) => {
  const btn = e.target.closest('button, .card, .back, .tab');
  if (!btn) return;
  if (btn.classList.contains('dd-dlg-cancel')) return;
  // 返回鍵：低沉音效
  if (btn.classList.contains('back') || btn.classList.contains('back-btn')) {
    playBack();
    return;
  }
  // CTA 按鈕（看診進度主要動作鈕）：叮咚音效
  if (btn.classList.contains('cta')) {
    playDingDong();
    return;
  }
  playTap();
}, true);

// ==================== 自訂彈框 ====================
// showDialog({ title, message, okText, cancelText }) → Promise<boolean>
// cancelText 傳 null 則只有確定鍵（alert 模式）
function showDialog(opts) {
  const { title = '', message = '', okText = '確定', cancelText = '取消' } = opts || {};
  return new Promise(resolve => {
    // 清掉舊的 dialog
    document.querySelectorAll('.dd-modal').forEach(el => el.remove());
    const modal = document.createElement('div');
    modal.className = 'dd-modal';
    const cancelHtml = cancelText === null ? '' :
      `<button class="dd-dlg-btn dd-dlg-cancel">${cancelText}</button>`;
    modal.innerHTML = `
      <div class="dd-dlg">
        ${title ? `<div class="dd-dlg-title">${title}</div>` : ''}
        <div class="dd-dlg-msg">${String(message).replace(/\n/g, '<br>')}</div>
        <div class="dd-dlg-actions">
          ${cancelHtml}
          <button class="dd-dlg-btn dd-dlg-ok">${okText}</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('show'));

    const close = (val) => {
      modal.classList.remove('show');
      setTimeout(() => modal.remove(), 200);
      resolve(val);
    };
    modal.querySelector('.dd-dlg-ok').onclick = () => close(true);
    if (cancelText !== null) modal.querySelector('.dd-dlg-cancel').onclick = () => close(false);
    modal.addEventListener('click', e => { if (e.target === modal && cancelText !== null) close(false); });
  });
}
function ddAlert(msg, title)   { return showDialog({ title, message: msg, cancelText: null }); }
function ddConfirm(msg, title) { return showDialog({ title, message: msg }); }
