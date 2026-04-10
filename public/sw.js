// 叮咚到號 — Service Worker
// 處理 PWA 安裝、Web Push 通知、通知點擊跳轉

const VERSION = 'v1';
const CACHE_NAME = `dindon-${VERSION}`;

// 安裝:跳過等待,立即接管
self.addEventListener('install', (event) => {
    self.skipWaiting();
});

// 啟動:接管所有開啟中的分頁
self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        // 清掉舊版 cache
        const keys = await caches.keys();
        await Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)));
        await self.clients.claim();
    })());
});

// Push 事件:收到後端推送的訊息,顯示通知
self.addEventListener('push', (event) => {
    let data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch (e) {
        data = { title: '叮咚到號', body: event.data ? event.data.text() : '' };
    }

    const title = data.title || '叮咚到號';
    const options = {
        body: data.body || '',
        icon: '/api/pwa/icon/192',
        badge: '/api/pwa/icon/192',
        tag: data.tag || 'dindon-default',  // 同 tag 會合併,不重複跳通知
        renotify: true,                      // 同 tag 也要再響
        requireInteraction: data.urgent || false,  // 重要通知不自動消失
        data: {
            url: data.url || '/chat',
            track_id: data.track_id || null,
        },
        vibrate: [200, 100, 200],
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

// 通知點擊:把對應的分頁帶到前景,沒開過就開新的
self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    const targetUrl = (event.notification.data && event.notification.data.url) || '/chat';

    event.waitUntil((async () => {
        const allClients = await self.clients.matchAll({
            type: 'window',
            includeUncontrolled: true,
        });

        // 找已開啟的分頁
        for (const client of allClients) {
            if (client.url.includes('/chat') && 'focus' in client) {
                await client.focus();
                if ('navigate' in client && client.url !== targetUrl) {
                    try {
                        await client.navigate(targetUrl);
                    } catch (e) {
                        // navigate 跨 origin 會失敗,忽略
                    }
                }
                return;
            }
        }

        // 沒開過就開新的
        if (self.clients.openWindow) {
            await self.clients.openWindow(targetUrl);
        }
    })());
});

// pushsubscriptionchange:訂閱失效時(例如 push service 換 endpoint)
// 後端會處理 InvalidToken,這邊先不做 auto-resubscribe
self.addEventListener('pushsubscriptionchange', (event) => {
    // TODO Phase 2:呼叫後端重新註冊
    console.log('[sw] push subscription changed');
});
