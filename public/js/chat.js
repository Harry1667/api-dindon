// 主聊天邏輯：processMessage / sendMessage / init
import { state, MAX_TRACKS, API_BASE } from './state.js';
import { addBotMsg, addUserMsg } from './ui.js';
import { playTap, playSend } from './audio.js';
import { showMainMenu, showAreaMenu, showHospitalsByArea, nextPage } from './menu.js';
import { fetchProgress, showDeptList, showDeptProgress, showSearchResults, findHospital } from './hospital.js';
import {
    startTracking, checkTrackingNow, showTrackDetail,
    stopTrack, showTrackList,
} from './tracking.js';

const msgInput = document.getElementById('msgInput');

// 初始化：載入醫院列表 + 收藏 + 顯示主選單
export async function init() {
    // 從 URL 取 line_user_id
    const urlParams = new URLSearchParams(location.search);
    if (urlParams.get('uid')) localStorage.setItem('line_user_id', urlParams.get('uid'));
    state.lineUserId = localStorage.getItem('line_user_id') || '';
    state.userArea = localStorage.getItem('user_area') || '';

    try {
        const resp = await fetch(`${API_BASE}/api/hospitals`);
        const data = await resp.json();
        state.hospitals = data.hospitals || [];
    } catch (e) {
        addBotMsg('無法連線，請稍後再試');
        return;
    }

    if (state.lineUserId) {
        try {
            const resp = await fetch(`${API_BASE}/api/liff/favorites/${state.lineUserId}`);
            const data = await resp.json();
            if (data.favorites && data.favorites.length > 0) state.userFavorites = data.favorites;
        } catch (e) {}
    }

    await showMainMenu();
}

// 數字按鈕（單鍵直送）
export function tapNum(n) {
    if (state.sending) return;
    playTap();
    msgInput.value = n;
    sendMessage();
}

// 多位數輸入
export function tapMulti(n) {
    playTap();
    msgInput.value += n;
    msgInput.focus();
}

export function tapMultiDel() {
    playTap();
    msgInput.value = msgInput.value.slice(0, -1);
}

export function setMultiMode(on) {
    document.getElementById('numRow').style.display = on ? 'none' : 'flex';
    document.getElementById('numRowMulti').style.display = on ? 'flex' : 'none';
    if (on) {
        msgInput.value = '';
        msgInput.placeholder = '輸入掛號號碼...';
    } else {
        msgInput.placeholder = '輸入數字或醫院名稱...';
    }
}

export async function sendMessage() {
    if (state.sending) return;
    const text = msgInput.value.trim();
    if (!text) return;
    state.sending = true;
    playSend();
    addUserMsg(text);
    msgInput.value = '';
    await new Promise(r => setTimeout(r, 500));
    try {
        await processMessage(text);
    } catch (e) {
        console.error('processMessage error:', e);
        addBotMsg('查詢失敗，請稍後再試\n\n0 返回');
        state.menuState = 'error';
    }
    state.sending = false;
}

async function processMessage(text) {
    const m = text.trim();

    // 返回
    if (m === '0' || m === '回') {
        if (state.waitingForNumber) {
            state.waitingForNumber = false;
            setMultiMode(false);
            state.pendingTrack = null;
        }
        if (state.navStack.length > 0) {
            const back = state.navStack.pop();
            await back();
        } else {
            await showMainMenu();
        }
        return;
    }

    // 等待輸入掛號號碼
    if (state.waitingForNumber) {
        if (m === '999') {
            state.waitingForNumber = false;
            setMultiMode(false);
            startTracking(null);
            return;
        }
        const num = parseInt(m);
        if (num > 0) {
            state.waitingForNumber = false;
            setMultiMode(false);
            startTracking(num);
            return;
        }
        addBotMsg('請輸入掛號號碼（數字）\n或輸入 999 僅追蹤');
        return;
    }

    // 下一頁
    if (m === '9' && state.pageItems.length > 8) {
        nextPage();
        return;
    }

    // 數字選擇
    if (state.menuOptions[m]) {
        const action = state.menuOptions[m];

        if (action === 'check_tracking') {
            await checkTrackingNow();
            return;
        }
        if (typeof action === 'object' && action.type === 'track_view') {
            await showTrackDetail(action.track);
            return;
        }
        if (typeof action === 'object' && action.type === 'stop_track') {
            stopTrack(action.track);
            addBotMsg(`${action.track.doctor} 追蹤已停止`);
            await new Promise(r => setTimeout(r, 300));
            await showMainMenu();
            return;
        }
        if (action === 'list_area') {
            state.navStack.push(() => showMainMenu());
            showAreaMenu();
            return;
        }
        if (typeof action === 'object' && action.type === 'area') {
            state.navStack.push(() => showAreaMenu());
            showHospitalsByArea(action.area, action.list);
            return;
        }
        if (typeof action === 'object' && action.type === 'hospital') {
            state.navStack.push(() => showMainMenu());
            await fetchProgress(action.hospital);
            return;
        }
        if (typeof action === 'object' && action.type === 'dept') {
            state.navStack.push(() => showDeptList(state.lastHospital));
            showDeptProgress(state.lastHospital, action.dept);
            return;
        }
        // 選醫師 → 開始追蹤流程
        if (typeof action === 'object' && action.type === 'doctor') {
            const doc = action.doctor;
            if (state.tracks.length >= MAX_TRACKS) {
                addBotMsg(`已達追蹤上限 ${MAX_TRACKS} 位\n請先停止其他追蹤\n\n0 返回`);
                return;
            }
            const exists = state.tracks.find(t =>
                t.hospitalCode === state.lastHospital.code &&
                t.doctor === doc.doctor_name &&
                t.room === doc.clinic_room
            );
            if (exists) {
                addBotMsg(`${doc.doctor_name} ${doc.clinic_room} 已在追蹤中\n\n0 返回`);
                return;
            }
            state.pendingTrack = {
                id: Date.now() + Math.random(),
                hospital: state.lastHospital,
                hospitalCode: state.lastHospital.code,
                dept: doc.department,
                doctor: doc.doctor_name,
                room: doc.clinic_room,
                currentNumber: doc.current_number,
                userNumber: null,
                intervalId: null,
                skippedRemindCount: 0,
                skippedTimerId: null,
            };
            state.waitingForNumber = true;
            setMultiMode(true);
            addBotMsg(
                `${doc.doctor_name} ${doc.clinic_room}\n` +
                `目前看診：#${doc.current_number}\n\n` +
                `請輸入您的掛號號碼\n或輸入 999 僅追蹤\n\n0 返回`
            );
            return;
        }
    }

    // 文字輸入：找醫院
    if (state.menuState === 'wait_hospital' || state.menuState === 'main') {
        const hospital = findHospital(m);
        if (hospital) {
            state.navStack.push(() => showMainMenu());
            await fetchProgress(hospital);
            return;
        }
        const matched = state.hospitals.filter(h => h.name.includes(m));
        if (matched.length > 0) {
            state.navStack.push(() => showMainMenu());
            showSearchResults(matched);
            return;
        }
        addBotMsg(`找不到「${m}」\n0 返回`);
        return;
    }

    // 不認識的輸入 → 回主選單
    await showMainMenu();
}

// 鍵盤 Enter
msgInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.isComposing) sendMessage();
});

// 啟動
init();
