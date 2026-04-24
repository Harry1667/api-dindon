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
