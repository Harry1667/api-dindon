// 醫院資料處理：查找、地區分組
import { state, API_BASE } from './state.js';
import { addBotMsg } from './ui.js';
import { showPage } from './menu.js';

export function findHospital(text) {
    let found = state.hospitals.find(h => text.includes(h.name));
    if (found) return found;

    const aliases = {
        '台大': 'ntuh', '台大醫院': 'ntuh',
        '台大癌醫': 'ntuh-cancer', '癌醫': 'ntuh-cancer',
        '台大兒童': 'ntuh-children',
        '榮總': 'tpvgh', '台北榮總': 'tpvgh', '北榮': 'tpvgh',
        '台中榮總': 'tcvgh', '中榮': 'tcvgh',
        '三總': 'tsgh', '三軍': 'tsgh',
        '長庚': 'changgung-linkou', '林口長庚': 'changgung-linkou',
        '台北長庚': 'changgung-taipei',
        '高雄長庚': 'changgung-kaohsiung',
        '國泰': 'cathay', '國泰醫院': 'cathay',
        '馬偕': 'mackay-taipei', '馬偕醫院': 'mackay-taipei',
        '新光': 'shinkong', '新光醫院': 'shinkong',
        '萬芳': 'wanfang', '萬芳醫院': 'wanfang',
        '亞東': 'femh', '亞東醫院': 'femh',
        '振興': 'chgh', '振興醫院': 'chgh',
        '慈濟': 'tzuchi-taipei',
        '輔大': 'fjuh', '輔大醫院': 'fjuh',
    };
    for (const [alias, code] of Object.entries(aliases)) {
        if (text.includes(alias)) return state.hospitals.find(h => h.code === code);
    }
    return null;
}

export function groupByArea() {
    const groups = { '台北市': [], '新北市': [], '基隆': [], '桃園': [], '台中': [], '雲嘉': [], '高雄': [] };
    for (const h of state.hospitals) {
        const n = h.name;
        if (n.includes('台大') || n.includes('三軍') || n.includes('榮總') || n.includes('台北長庚') ||
            n.includes('國泰醫院') || n.includes('馬偕醫院(台北') || n.includes('新光') ||
            n.includes('萬芳') || n.includes('振興') || n.includes('台大癌醫') || n.includes('台大兒童'))
            groups['台北市'].push(h);
        else if (n.includes('亞東') || n.includes('慈濟') || n.includes('淡水') || n.includes('臺北醫院') ||
                 n.includes('汐止') || n.includes('土城') || n.includes('新北') || n.includes('輔大'))
            groups['新北市'].push(h);
        else if (n.includes('基隆')) groups['基隆'].push(h);
        else if (n.includes('林口') || n.includes('桃園')) groups['桃園'].push(h);
        else if (n.includes('台中') || n.includes('豐原')) groups['台中'].push(h);
        else if (n.includes('雲林') || n.includes('嘉義')) groups['雲嘉'].push(h);
        else if (n.includes('高雄') || n.includes('鳳山')) groups['高雄'].push(h);
    }
    return groups;
}

export async function fetchProgress(hospital) {
    state.lastHospital = hospital;

    if (state.lineUserId) {
        fetch(`${API_BASE}/api/liff/favorite`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ line_user_id: state.lineUserId, hospital_code: hospital.code, hospital_name: hospital.name }),
        }).catch(() => {});
    }

    const resp = await fetch(`${API_BASE}/api/progress/${hospital.code}`);
    const data = await resp.json();

    if (!data.data || data.data.length === 0) {
        state.menuOptions = {};
        state.menuState = 'no_data';
        addBotMsg(`${hospital.name}\n目前無看診資料\n\n0 返回`);
        return;
    }

    state.lastProgressData = data.data;
    await showDeptList(hospital);
}

export async function showDeptList(hospital) {
    const depts = [...new Set(state.lastProgressData.map(r => r.department))].sort();

    let favDepts = [];
    if (state.lineUserId) {
        try {
            const resp = await fetch(`${API_BASE}/api/liff/favorites/${state.lineUserId}?hospital_code=${hospital.code}`);
            const data = await resp.json();
            favDepts = (data.favorites || []).map(f => f.department);
        } catch (e) {}
    }

    const sorted = [];
    for (const d of favDepts) { if (depts.includes(d)) sorted.push(d); }
    for (const d of depts) { if (!sorted.includes(d)) sorted.push(d); }

    const items = sorted.map(dept => {
        const count = state.lastProgressData.filter(r => r.department === dept).length;
        const isFav = favDepts.includes(dept);
        return {
            label: `${isFav ? '⭐' : ''}${dept}(${count})`,
            action: { type: 'dept', dept },
        };
    });

    showPage(items, 'dept_list', hospital.name);
}

export function showDeptProgress(hospital, dept) {
    if (state.lineUserId) {
        fetch(`${API_BASE}/api/liff/favorite`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ line_user_id: state.lineUserId, hospital_code: hospital.code, hospital_name: hospital.name, department: dept }),
        }).catch(() => {});
    }

    const results = state.lastProgressData.filter(r => r.department === dept);
    if (results.length === 0) {
        state.menuOptions = {};
        state.menuState = 'progress';
        addBotMsg(`${dept} 目前無資料\n\n0 返回`);
        return;
    }

    const items = results.map(it => {
        let num = `#${it.current_number}`;
        if (it.is_current_skipped) num += '(過)';
        const room = it.clinic_room || '';
        return {
            label: `${it.doctor_name} ${room} ${num}`,
            action: { type: 'doctor', doctor: it },
        };
    });

    showPage(items, 'progress', `${hospital.name} ${dept}`);
}

export function showSearchResults(matched) {
    const items = matched.map(h => ({ label: h.name, action: { type: 'hospital', hospital: h } }));
    showPage(items, 'search_result', `找到${matched.length}間`);
}
