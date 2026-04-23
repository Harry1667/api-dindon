// PWA：Service Worker 註冊 + Web Push 訂閱
(function () {
    'use strict';

    const _qs = new URLSearchParams(location.search);
    const _lineUid = _qs.get('uid') || _qs.get('line_user_id') || null;

    const LS_PUSH_ASKED   = 'dindon_push_asked';
    const LS_INSTALL_HINT = 'dindon_install_hint_shown';

    const ua           = navigator.userAgent;
    const isIOS        = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
    const isAndroid    = /Android/.test(ua);
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches
                      || window.navigator.standalone === true;

    async function registerSW() {
        if (!('serviceWorker' in navigator)) return null;
        try {
            const reg = await navigator.serviceWorker.register('/api/pwa/sw', { scope: '/' });
            console.log('[PWA] SW registered:', reg.scope);
            return reg;
        } catch (e) {
            console.error('[PWA] SW register failed:', e);
            return null;
        }
    }

    function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        const rawData = atob(base64);
        const out = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) out[i] = rawData.charCodeAt(i);
        return out;
    }

    async function subscribePush(reg) {
        if (!reg || !('PushManager' in window)) return null;
        let vapidKey;
        try {
            const r = await fetch('/api/push/vapid-key');
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const data = await r.json();
            vapidKey = data.public_key;
        } catch (e) {
            console.error('[PWA] 取 VAPID key 失敗:', e);
            return null;
        }
        let sub;
        try {
            sub = await reg.pushManager.getSubscription();
            if (!sub) {
                sub = await reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(vapidKey),
                });
            }
        } catch (e) {
            console.error('[PWA] subscribe 失敗:', e);
            return null;
        }
        try {
            const r = await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    line_user_id: _lineUid,
                    guest_id: localStorage.getItem('dd_guest_id') || null,
                    subscription: sub.toJSON(),
                    user_agent: navigator.userAgent,
                    platform: isIOS ? 'ios' : (isAndroid ? 'android' : 'desktop'),
                }),
            });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            console.log('[PWA] subscribe 已送後端');
            return sub;
        } catch (e) {
            console.error('[PWA] 送後端失敗:', e);
            return null;
        }
    }

    async function maybeAskPermission(reg) {
        if (!('Notification' in window)) return;
        if (Notification.permission === 'granted') { await subscribePush(reg); return; }
        if (Notification.permission === 'denied') return;
        if (localStorage.getItem(LS_PUSH_ASKED) === 'yes') return;
        if (isIOS && !isStandalone) return;
        try {
            const perm = await Notification.requestPermission();
            localStorage.setItem(LS_PUSH_ASKED, 'yes');
            if (perm === 'granted') await subscribePush(reg);
        } catch (e) {
            console.error('[PWA] requestPermission failed:', e);
        }
    }

    function showIOSInstallHint() {
        if (!isIOS || isStandalone) return;
        if (localStorage.getItem(LS_INSTALL_HINT) === 'yes') return;
        setTimeout(() => {
            const banner = document.createElement('div');
            banner.style.cssText = `
                position: fixed; bottom: 0; left: 0; right: 0;
                background: white; border-top: 2px solid #06C755;
                padding: 14px 16px; font-size: 13px; color: #333;
                z-index: 9999; box-shadow: 0 -4px 12px rgba(0,0,0,0.1);
                line-height: 1.5;
            `;
            banner.innerHTML = `
                <div style="display:flex;align-items:center;gap:10px;">
                    <div style="flex:1;">
                        💡 想收到看診叫號通知嗎?<br>
                        點下方 <strong>分享 ⬆️</strong> → 選「<strong>加入主畫面</strong>」
                    </div>
                    <button id="dindon-hint-close" style="
                        background: #06C755; color: white; border: none;
                        padding: 8px 14px; border-radius: 8px; font-size: 13px;
                    ">知道了</button>
                </div>
            `;
            document.body.appendChild(banner);
            document.getElementById('dindon-hint-close').onclick = () => {
                banner.remove();
                localStorage.setItem(LS_INSTALL_HINT, 'yes');
            };
        }, 4000);
    }

    async function initPWA() {
        const reg = await registerSW();
        if (!reg) return;
        const askOnce = async () => {
            document.removeEventListener('click', askOnce);
            document.removeEventListener('touchstart', askOnce);
            await maybeAskPermission(reg);
        };
        document.addEventListener('click', askOnce, { once: true });
        document.addEventListener('touchstart', askOnce, { once: true });
        showIOSInstallHint();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPWA);
    } else {
        initPWA();
    }
})();
