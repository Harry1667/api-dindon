// UI 渲染模組
const chatBody = document.getElementById('chatBody');

function escapeHtml(t) {
    return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
}

function scrollDown() {
    requestAnimationFrame(() => { chatBody.scrollTop = chatBody.scrollHeight; });
}

export function addBotMsg(text) {
    const row = document.createElement('div');
    row.className = 'msg-row bot';
    row.innerHTML = `<div class="bubble-avatar">🏥</div><div class="bubble">${escapeHtml(text)}</div>`;
    chatBody.appendChild(row);
    scrollDown();
}

export function addUserMsg(text) {
    const row = document.createElement('div');
    row.className = 'msg-row user';
    row.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
    chatBody.appendChild(row);
    scrollDown();
}

export function copyMsg(btn, encoded) {
    const text = decodeURIComponent(encoded);
    navigator.clipboard.writeText(text).then(() => {
        btn.textContent = '✓ 已複製';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = '複製'; btn.classList.remove('copied'); }, 1500);
    });
}
