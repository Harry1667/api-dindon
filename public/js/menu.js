// 選單 / 分頁模組
import { state, API_BASE } from './state.js';
import { addBotMsg } from './ui.js';
import { groupByArea } from './hospital.js';

export function showPage(items, menuStateVal, title) {
    state.pageItems = items;
    state.pageContext = { state: menuStateVal, title };
    state.pageIndex = 0;
    renderPage();
}

export function renderPage() {
    const perPage = 8;
    const slice = state.pageItems.slice(state.pageIndex, state.pageIndex + perPage);
    const total = state.pageItems.length;
    const pageNum = Math.floor(state.pageIndex / perPage) + 1;
    const totalPages = Math.ceil(total / perPage);

    state.menuOptions = {};
    state.menuState = state.pageContext.state;

    let lines = [];
    lines.push(totalPages > 1 ? `${state.pageContext.title} (${pageNum}/${totalPages})` : state.pageContext.title);
    lines.push('');

    slice.forEach((item, idx) => {
        const num = idx + 1;
        lines.push(`${num} ${item.label}`);
        state.menuOptions[String(num)] = item.action;
    });

    lines.push('');
    if (total > perPage) lines.push('9 下一頁');
    lines.push('0 返回');

    addBotMsg(lines.join('\n'));
}

export function nextPage() {
    state.pageIndex += 8;
    if (state.pageIndex >= state.pageItems.length) state.pageIndex = 0;
    renderPage();
}

export function showAreaMenu() {
    const areas = groupByArea();
    const items = [];
    for (const [area, list] of Object.entries(areas)) {
        if (list.length === 0) continue;
        items.push({ label: `${area}(${list.length})`, action: { type: 'area', area, list } });
    }
    showPage(items, 'area', '選擇地區');
}

export function showHospitalsByArea(area, list) {
    state.userArea = area;
    localStorage.setItem('user_area', area);
    const items = list.map(h => ({ label: h.name, action: { type: 'hospital', hospital: h } }));
    showPage(items, 'hospital_list', area);
}

export async function showMainMenu() {
    state.navStack = [];
    state.menuState = 'main';
    state.menuOptions = { '2': 'list_area' };

    // 重新載入收藏
    if (state.lineUserId) {
        try {
            const resp = await fetch(`${API_BASE}/api/liff/favorites/${state.lineUserId}`);
            const data = await resp.json();
            if (data.favorites && data.favorites.length > 0) state.userFavorites = data.favorites;
        } catch (e) {}
    }

    let lines = [];
    if (state.tracks.length > 0) {
        const label = state.tracks.length === 1 ? '1 查追蹤進度' : `1 查追蹤進度 (${state.tracks.length})`;
        lines.push(label);
        state.menuOptions['1'] = 'check_tracking';
    }
    lines.push('2 醫院列表');
    lines.push('');

    const maxSlots = 5;
    const usedCodes = new Set();
    const slots = [];

    for (const f of state.userFavorites) {
        if (slots.length >= maxSlots) break;
        const h = state.hospitals.find(x => x.code === f.hospital_code);
        if (h && !usedCodes.has(h.code)) {
            slots.push({ hospital: h, name: f.hospital_name, star: true });
            usedCodes.add(h.code);
        }
    }

    if (slots.length < maxSlots) {
        const areas = groupByArea();
        if (state.userArea && areas[state.userArea]) {
            for (const h of areas[state.userArea]) {
                if (slots.length >= maxSlots) break;
                if (!usedCodes.has(h.code)) {
                    slots.push({ hospital: h, name: h.name, star: false });
                    usedCodes.add(h.code);
                }
            }
        }
        if (slots.length < maxSlots) {
            const taipei = areas['台北市'] || [];
            for (const h of taipei) {
                if (slots.length >= maxSlots) break;
                if (!usedCodes.has(h.code)) {
                    slots.push({ hospital: h, name: h.name, star: false });
                    usedCodes.add(h.code);
                }
            }
        }
    }

    slots.forEach((s, idx) => {
        const num = idx + 4;
        const mark = s.star ? '⭐' : '';
        lines.push(`${num} ${mark}${s.name}`);
        state.menuOptions[String(num)] = { type: 'hospital', hospital: s.hospital };
    });

    addBotMsg(lines.join('\n'));
}
