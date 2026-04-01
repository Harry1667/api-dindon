# Webhook 使用手冊 — LINE Bot 轉發

> 本文件教你怎麼新增 chatbot agent 的 webhook 轉發。
> 基礎設定請參考 [set_webhook.MD](set_webhook.MD)。

---

## 現有端點

| 名稱 | 外網網址 | 內部轉發到 | 說明 |
|------|---------|-----------|------|
| dindon-deploy | `https://dindon.cleanhome.tw/hooks/dindon-deploy` | — | LINE Bot 正式環境 |
| dindon-test | `https://dindon.cleanhome.tw/hooks/dindon-test` | — | LINE Bot 測試環境 |

---

## 新增 Chatbot Agent 轉發（Nginx 方式）

LINE webhook 需要完整的 raw body + `X-Line-Signature` header 做 HMAC 驗證。
**不要用 shell script 轉發**，會破壞 body。直接用 Nginx 反代最乾淨。

### 架構

```
LINE Platform
  ↓ POST https://dindon.cleanhome.tw/webhook/beauty-salon
Nginx
  ↓ proxy_pass（完整轉發 body + 所有 headers）
http://127.0.0.1:3000/webhook/beauty-salon
```

### 步驟

#### 1. 確認你的 chatbot agent 在伺服器上跑起來了

```bash
# 確認 port 有在聽
ssh aapanel "curl -s http://127.0.0.1:3000/health"
```

#### 2. 加 Nginx 設定

登入 aaPanel → Website → `dindon.cleanhome.tw` → Config

在 `location / {` **上方**加入：

```nginx
# chatbot-agent: 美容院（轉發到 port 3000）
location /webhook/beauty-salon {
    proxy_pass http://127.0.0.1:3000/webhook/beauty-salon;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Line-Signature $http_x_line_signature;
    proxy_pass_request_body on;
    proxy_read_timeout 30s;
}
```

儲存。Nginx 會自動 reload。

#### 3. 到 LINE Developers 設定 Webhook URL

```
https://dindon.cleanhome.tw/webhook/beauty-salon
```

#### 4. 驗證

```bash
# 從外網測
curl -s -X POST https://dindon.cleanhome.tw/webhook/beauty-salon \
  -H "Content-Type: application/json" \
  -d '{"events":[]}'
```

---

## 範例：加第二個 agent

假設你有第二個 chatbot 跑在 port 3001，路徑是 `/webhook/clinic`：

```nginx
# chatbot-agent: 診所（轉發到 port 3001）
location /webhook/clinic {
    proxy_pass http://127.0.0.1:3001/webhook/clinic;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Line-Signature $http_x_line_signature;
    proxy_pass_request_body on;
    proxy_read_timeout 30s;
}
```

LINE Developers Webhook URL：
```
https://dindon.cleanhome.tw/webhook/clinic
```

---

## Nginx 模板（複製貼上改 3 個地方）

```nginx
# chatbot-agent: __名稱__（轉發到 port __PORT__）
location /webhook/__路徑__ {
    proxy_pass http://127.0.0.1:__PORT__/webhook/__路徑__;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Line-Signature $http_x_line_signature;
    proxy_pass_request_body on;
    proxy_read_timeout 30s;
}
```

要改的地方：

| 佔位符 | 改成 | 範例 |
|--------|------|------|
| `__名稱__` | agent 說明 | 美容院 |
| `__PORT__` | chatbot 服務 port | 3000 |
| `__路徑__` | webhook 路徑 | beauty-salon |

---

## 完整新增流程 Checklist

```
□ 1. chatbot agent 在伺服器跑起來（docker 或直接跑）
□ 2. 確認內部可達：curl http://127.0.0.1:{PORT}/health
□ 3. 複製 Nginx 模板，改好 3 個佔位符
□ 4. 貼到 aaPanel → dindon.cleanhome.tw → Config → 儲存
□ 5. LINE Developers → Webhook URL 填 https://dindon.cleanhome.tw/webhook/{路徑}
□ 6. 點 Verify → 顯示 Success
□ 7. 用手機 LINE 傳訊息測試
```

---

## 常見問題

### Q: 為什麼不用 adnanh/webhook 轉發？

adnanh/webhook 是透過 shell script 執行指令，會把 HTTP body 當參數傳給 script。
LINE webhook 驗證需要 raw body 做 HMAC-SHA256，經過 shell 轉發後 body 會被改變，
導致簽名驗證失敗。Nginx 反代是完整轉發，不會動到 body。

### Q: 多個 agent 可以共用同一個域名嗎？

可以。靠路徑區分：

```
https://dindon.cleanhome.tw/webhook/beauty-salon  → port 3000
https://dindon.cleanhome.tw/webhook/clinic         → port 3001
https://dindon.cleanhome.tw/webhook/restaurant     → port 3002
```

每個 agent 用不同的 LINE Channel，設不同的 Webhook URL。

### Q: 可以用不同域名嗎？

可以。在另一個網站的 Nginx 加同樣的 location 就好：

```
https://other-domain.com/webhook/xxx → 同一台伺服器的 port 3000
```

### Q: 怎麼看 agent 有沒有收到請求？

```bash
# 看 Nginx access log
ssh aapanel "tail -20 /www/wwwlogs/dindon.cleanhome.tw.log | grep webhook"

# 看 chatbot agent 自己的日誌
ssh aapanel "docker logs {container-name} --tail 20"
```

---

## 安全提醒

- LINE webhook 的安全性靠 `X-Line-Signature` HMAC 驗證，每個 LINE Channel 有自己的 Channel Secret
- Nginx 只負責轉發，**不需要額外的 secret header**
- chatbot agent 自己要驗證 `X-Line-Signature`，不要信任未驗證的請求
- 建議限制 Nginx 只接受 POST：在 location 裡加 `limit_except POST { deny all; }`
