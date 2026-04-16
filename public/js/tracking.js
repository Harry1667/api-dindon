// 追蹤看診號碼模組（多醫師，最多 3 位）
import { state, MAX_TRACKS, API_BASE } from './state.js';
import { addBotMsg } from './ui.js';
import { playDing, playDingDong } from './audio.js';
import { showMainMenu } from './menu.js';

// 取得或產生訪客 ID（儲存在 localStorage）
function getGuestId() {
    let id = localStorage.getItem('dd_guest_id');
    if (!id) {
        id = 'g_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
        localStorage.setItem('dd_guest_id', id);
    }
    return id;
}

// 儲存追蹤到 DB（背景呼叫，失敗不影響前端）
async function saveTrackToDB(track) {
    try {
        const resp = await fetch(`${API_BASE}/api/track/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                guest_id: getGuestId(),
                hospital_code: track.hospitalCode,
                department: track.dept,
                doctor_name: track.doctor,
                clinic_room: track.room,
                session: track.session || null,
                user_number: track.userNumber || 0,
            }),
        });
        const data = await resp.json();
        if (data.ok) track.dbId = data.track_id;
    } catch (_) { /* 背景記錄失敗不影響前端 */ }
}

// 更新 DB 追蹤狀態（背景呼叫）
async function updateTrackInDB(track, reason) {
    if (!track.dbId) return;
    try {
        await fetch(`${API_BASE}/api/track/${track.dbId}/stop`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ guest_id: getGuestId(), reason }),
        });
    } catch (_) { /* 忽略 */ }
}

export function startTracking(userNumber) {
    if (!state.pendingTrack) return;
    if (state.tracks.length >= MAX_TRACKS) {
        addBotMsg(`已達追蹤上限 ${MAX_TRACKS} 位`);
        state.pendingTrack = null;
        return;
    }
    const track = state.pendingTrack;
    state.pendingTrack = null;
    track.userNumber = userNumber;
    track.intervalId = setInterval(() => pollTracking(track), 30000);
    state.tracks.push(track);
    saveTrackToDB(track);  // 背景存 DB

    state.menuState = 'tracking';
    state.menuOptions = {};
    state.navStack = [];

    const cur = track.currentNumber;
    const next = cur + 1;
    let msg = `開始追蹤\n`;
    msg += `醫院：${track.hospital.name}\n`;
    msg += `科別：${track.dept}\n`;
    msg += `醫生：${track.doctor}\n`;
    msg += `診間：${track.room}\n`;
    msg += `目前號碼：#${cur}\n`;
    msg += `下一號：#${next}`;
    if (userNumber) {
        const remaining = userNumber - cur;
        if (remaining > 0) {
            msg += `\n\n您是 ${userNumber} 號，前面還有約 ${remaining} 位`;
        } else {
            msg += `\n\n您是 ${userNumber} 號，已到或過號`;
        }
    }
    msg += `\n\n每 30 秒自動更新 (追蹤中 ${state.tracks.length}/${MAX_TRACKS})\n0 回主頁`;
    addBotMsg(msg);
}

export async function checkTrackingNow() {
    if (state.tracks.length === 0) {
        addBotMsg('目前沒有追蹤');
        return;
    }
    if (state.tracks.length === 1) {
        await showTrackDetail(state.tracks[0]);
        return;
    }
    showTrackList();
}

export function showTrackList() {
    state.menuState = 'track_list';
    state.menuOptions = {};
    let lines = [`追蹤中 (${state.tracks.length}/${MAX_TRACKS})`, ''];
    state.tracks.forEach((t, i) => {
        const num = i + 1;
        const cur = t.currentNumber;
        const un = t.userNumber;
        const status = un ? `#${cur} / 您${un}` : `#${cur}`;
        lines.push(`${num} ${t.doctor} ${t.room} ${status}`);
        state.menuOptions[String(num)] = { type: 'track_view', track: t };
    });
    lines.push('');
    lines.push('0 回主頁');
    addBotMsg(lines.join('\n'));
}

export async function showTrackDetail(track) {
    if (!state.tracks.includes(track)) {
        addBotMsg('此追蹤已結束');
        return;
    }
    try {
        const resp = await fetch(`${API_BASE}/api/progress/${track.hospitalCode}`);
        const data = await resp.json();
        if (!data.data) { addBotMsg('查詢失敗'); return; }
        const found = data.data.find(d =>
            d.doctor_name === track.doctor && d.clinic_room === track.room
        );
        if (!found) {
            addBotMsg(`${track.doctor} 看診已結束`);
            stopTrack(track);
            return;
        }
        track.currentNumber = found.current_number;
        const cur = found.current_number;
        const next = cur + 1;
        let msg = `追蹤中\n`;
        msg += `醫院：${track.hospital.name}\n`;
        msg += `科別：${track.dept}\n`;
        msg += `醫生：${track.doctor}\n`;
        msg += `診間：${track.room}\n`;
        msg += `目前號碼：#${cur}`;
        if (found.is_current_skipped) msg += '(過號)';
        msg += `\n下一號：#${next}`;

        if (track.userNumber) {
            const un = track.userNumber;
            if (cur === un) {
                msg += `\n\n🔔 輪到您了！${un} 號正在叫號`;
            } else if (cur > un) {
                msg += `\n\n⚠️ 您是 ${un} 號，已過號`;
            } else {
                msg += `\n\n您是 ${un} 號，還剩約 ${un - cur} 位`;
            }
        }

        msg += '\n\n7 停止此追蹤\n0 回主頁';
        state.menuState = 'tracking_detail';
        state.menuOptions = { '7': { type: 'stop_track', track } };
        addBotMsg(msg);
    } catch (e) {
        addBotMsg('查詢失敗');
    }
}

export async function pollTracking(track) {
    if (!state.tracks.includes(track)) return;
    try {
        const resp = await fetch(`${API_BASE}/api/progress/${track.hospitalCode}`);
        const data = await resp.json();
        if (!data.data) return;

        const found = data.data.find(d =>
            d.doctor_name === track.doctor && d.clinic_room === track.room
        );
        if (!found) {
            addBotMsg(`${track.doctor} ${track.room} 看診已結束`);
            stopTrack(track);
            return;
        }

        const prev = track.currentNumber;
        track.currentNumber = found.current_number;

        if (found.current_number === prev) return;

        if (track.userNumber && found.current_number > track.userNumber) {
            startSkippedReminder(track);
            return;
        }

        let msg = `${track.doctor} ${track.room}\n目前：#${found.current_number}`;
        if (found.is_current_skipped) msg += '(過號)';

        let soundType = 'ding';

        if (track.userNumber) {
            const un = track.userNumber;
            if (found.current_number === un) {
                msg += `\n\n🔔 輪到您了！${un} 號正在叫號！`;
                soundType = 'dingdong';
                stopTrack(track, 'completed');
            } else {
                const remaining = un - found.current_number;
                msg += `\n\n您是 ${un} 號，還剩約 ${remaining} 位`;
                if (remaining <= 2) soundType = 'dingdong';
            }
        }

        if (soundType === 'dingdong') playDingDong();
        else playDing();

        addBotMsg(msg);
    } catch (e) {
        console.error('pollTracking error:', e);
    }
}

export function stopTrack(track, reason = 'cancelled') {
    if (!track) return;
    if (track.intervalId) clearInterval(track.intervalId);
    if (track.skippedTimerId) clearInterval(track.skippedTimerId);
    const idx = state.tracks.indexOf(track);
    if (idx >= 0) state.tracks.splice(idx, 1);
    updateTrackInDB(track, reason);  // 背景更新 DB
}

export function stopAllTracks() {
    state.tracks.forEach(t => {
        if (t.intervalId) clearInterval(t.intervalId);
        if (t.skippedTimerId) clearInterval(t.skippedTimerId);
    });
    state.tracks = [];
}

export function startSkippedReminder(track) {
    if (!track || track.skippedTimerId) return;
    if (track.intervalId) {
        clearInterval(track.intervalId);
        track.intervalId = null;
    }
    track.skippedRemindCount = 0;
    sendSkippedReminder(track);
    track.skippedTimerId = setInterval(() => sendSkippedReminder(track), 60000);
}

function sendSkippedReminder(track) {
    if (!track || !state.tracks.includes(track)) return;
    track.skippedRemindCount++;
    const n = track.skippedRemindCount;
    const un = track.userNumber;
    addBotMsg(
        `⚠️ 您是 ${un} 號，已過號\n` +
        `${track.doctor} ${track.room}\n` +
        `提醒 ${n}/3`
    );
    playDingDong();
    if (n >= 3) {
        stopTrack(track);
        addBotMsg(`${track.doctor} 追蹤已結束`);
    }
}
