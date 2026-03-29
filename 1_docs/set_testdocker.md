# 叮咚到號 — Linux 本地測試環境建置

> 本文檔說明如何在 Linux 本地（Docker Desktop）建立獨立的開發測試環境，
> 與正式環境（VPS）完全隔離，互不干擾。

---

## 架構總覽

```
                        正式環境                              開發環境
                    ┌─────────────┐                    ┌──────────────────┐
                    │  LINE 正式帳號  │                    │  LINE DEV 帳號     │
                    └──────┬──────┘                    └────────┬─────────┘
                           │                                    │
                           ▼                                    ▼
              https://dindon.cleanhome.tw          https://dev-dindon.cleanhome.tw
                           │                                    │
                           ▼                                    ▼
                  ┌─── VPS (aaPanel) ───┐              ┌─── VPS Nginx ───┐
                  │  Nginx → :8000      │              │  反向代理 → :9000  │
                  │  Docker Compose     │              └────────┬─────────┘
                  │  MySQL (aaPanel)    │                       │
                  └─────────────────────┘              SSH 反向隧道 (:9000)
                                                               │
                                                               ▼
                                                    ┌─── 本地 Linux ────┐
                                                    │  Docker Desktop    │
                                                    │  ├─ FastAPI :8001  │
                                                    │  ├─ Celery Worker  │
                                                    │  ├─ Celery Beat    │
                                                    │  └─ Redis          │
                                                    └────────────────────┘
```

### 正式 vs 開發 環境對照

| 項目 | 正式環境 | 開發環境 |
|------|---------|---------|
| LINE Channel | `叮咚到號` | `叮咚到號-DEV`（新建） |
| Webhook URL | `https://dindon.cleanhome.tw/webhook` | `https://dev-dindon.cleanhome.tw/webhook` |
| MySQL | VPS aaPanel MySQL | VPS aaPanel MySQL（共用） |
| Redis | Docker 內部 | Docker 內部 |
| docker-compose | `docker-compose.yml` | `docker-compose.dev.yml` |
| .env | `.env` | `.env.dev` |
| 本地 Port | 8000 | 8001（避免與其他專案衝突） |
| 爬蟲頻率 | 60 秒 | 60 秒 |
| 推播對象 | 所有用戶 | 只有你自己 |

---

## Step 1：建立 LINE DEV Channel

### 1a. 進入 LINE Developers Console

1. 打開 https://developers.line.biz/console/
2. 選擇現有的 **Provider**（和正式帳號同一個 Provider 即可）
3. 點 **Create a new channel** → 選 **Messaging API**

### 1b. 填寫 Channel 資訊

| 欄位 | 填入內容 |
|------|---------|
| Channel type | Messaging API |
| Channel name | `叮咚到號-DEV` |
| Channel description | 開發測試用 |
| Category | 醫療 / Health |
| Subcategory | 自選 |

### 1c. 取得 credentials

建立完成後：

1. **Basic settings** → 複製 `Channel secret`
2. **Messaging API** → 點 **Issue** 產生 `Channel access token (long-lived)`
3. **Messaging API** → 把 **Auto-reply messages** 關閉
4. **Messaging API** → Webhook URL 先空著（後面設定）

> 記下這兩組 key，後面要填到 `.env.dev`

### 1d. 加入 DEV 好友

用手機 LINE 掃描 DEV Channel 的 QR Code 加入好友，這樣測試推播只會發給你。

---

## Step 2：Cloudflare DNS 設定

到 Cloudflare Dashboard → `cleanhome.tw` → DNS：

| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| A | `dev-dindon` | `57.182.129.192` | 看情況（見下方說明） | Auto |

> **Proxy 開或關？**
> - **DNS only（灰雲）**：最簡單，SSH 隧道直接通，建議開發用這個
> - **Proxied（橙雲）**：多一層 Cloudflare CDN，可能干擾 webhook 驗證，開發環境不需要

---

## Step 3：VPS aaPanel 設定

### 3a. 新增網站

1. aaPanel → **Website** → **Add site**
2. 域名填：`dev-dindon.cleanhome.tw`
3. 不選 PHP、不選資料庫
4. 建立後 → **SSL** → **Let's Encrypt** → 申請 → 開啟**強制 HTTPS**

### 3b. 設定 Nginx 反向代理

aaPanel → Website → `dev-dindon.cleanhome.tw` → **Config**

找到 `location / {`，**替換整個 location / 區塊**為：

```nginx
location / {
    proxy_pass http://127.0.0.1:9000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_read_timeout 60s;
    proxy_connect_timeout 10s;
}
```

儲存後 Nginx 會自動 reload。

### 3c. VPS SSH 設定（允許遠端綁定）

SSH 登入 VPS，確認 `/etc/ssh/sshd_config` 包含：

```
GatewayPorts clientspecified
```

如果沒有或是 `no`，改成上面的值後重啟：

```bash
sudo systemctl restart sshd
```

> 這允許 SSH -R 綁定到 `127.0.0.1:9000`（預設就可以，只綁 localhost 是安全的）

---

## Step 4：修改本地開發環境檔案

### 4a. 更新 `.env.dev`

```env
# === LINE Official Account ===
LINE_CHANNEL_SECRET=<你的Channel-Secret>
LINE_CHANNEL_ACCESS_TOKEN=<你的Channel-Access-Token>

# === MySQL（連遠端 aaPanel）===
MYSQL_HOST=57.182.129.192
MYSQL_PORT=3306
MYSQL_USER=ajz-dindon
MYSQL_PASSWORD=<你的密碼>
MYSQL_DATABASE=ajz-dindon

# === Redis（Docker 內部）===
REDIS_URL=redis://redis:6379/0

# === 應用設定 ===
APP_ENV=development
APP_DEBUG=true
SCRAPE_INTERVAL_SECONDS=60
NOTIFY_THRESHOLD=5

# === 管理後台 ===
ADMIN_USERNAME=admin
ADMIN_PASSWORD=dindon2024
```

> **重點：**
> - MySQL 連遠端 VPS aaPanel（正式與開發共用資料庫）
> - LINE credentials 填入你的 Channel 資訊

### 4b. 更新 `docker-compose.dev.yml`

```yaml
version: "3.8"

services:
  # === FastAPI 主應用（開發模式）===
  app:
    build: .
    container_name: medqueue-app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8001:8000"
    env_file:
      - .env.dev
    depends_on:
      - redis
    volumes:
      - .:/app
      - ./logs:/app/logs
    restart: unless-stopped

  # === Celery Worker ===
  worker:
    build: .
    container_name: medqueue-worker
    command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
    env_file:
      - .env.dev
    depends_on:
      - redis
    volumes:
      - .:/app
      - ./logs:/app/logs
    restart: unless-stopped

  # === Celery Beat ===
  beat:
    build: .
    container_name: medqueue-beat
    command: celery -A app.tasks.celery_app beat --loglevel=info
    env_file:
      - .env.dev
    depends_on:
      - redis
    volumes:
      - .:/app
      - ./logs:/app/logs
    restart: unless-stopped

  # === Redis ===
  redis:
    image: redis:7-alpine
    container_name: medqueue-redis
    ports:
      - "6380:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

volumes:
  redis_data:
```

> **和正式版的差異：**
> - 本地 port 用 8001（避免與其他專案衝突）
> - MySQL 不在 Docker 內，連遠端 VPS aaPanel MySQL
> - FastAPI 加 `--reload`（改 code 自動重啟）
> - 掛載原始碼 volume（熱更新）
> - Redis port 用 6380 避免和本機衝突

---

## Step 5：啟動開發環境

### 5a. 啟動 Docker 服務

```bash
cd /home/linux/Dropbox/84-WebCode/00-gemini/6-linux/5-ajz/linebot-medicalqueue

# 建置 + 啟動
docker compose -f docker-compose.dev.yml up --build -d

# 確認所有容器都跑起來
docker compose -f docker-compose.dev.yml ps
```

應該看到 4 個容器都是 `Up`：

```
medqueue-app      ... Up   0.0.0.0:8001->8000/tcp
medqueue-worker   ... Up
medqueue-beat     ... Up
medqueue-redis    ... Up   0.0.0.0:6380->6379/tcp
```

> **注意：** 本地 port 用 8001，因為 8000 可能被其他專案佔用

### 5b. 驗證本地服務

```bash
# 測試 API
curl http://localhost:8001/health

# 測試 Redis
docker exec medqueue-redis redis-cli ping
```

---

## Step 6：建立 SSH 反向隧道

### 6a. 啟動隧道

```bash
ssh -R 9000:localhost:8001 root@57.182.129.192 -N -o ServerAliveInterval=60
```

| 參數 | 說明 |
|------|------|
| `-R 9000:localhost:8001` | VPS 的 9000 port → 本地的 8001 port |
| `-N` | 不開 shell，只建隧道 |
| `-o ServerAliveInterval=60` | 每 60 秒送心跳，防止斷線 |

### 6b. 驗證隧道

開另一個終端，SSH 到 VPS 測試：

```bash
ssh root@57.182.129.192 "curl -s http://127.0.0.1:9000/health"
```

應該回傳 `{"status":"ok",...}`

然後從外網測試：

```bash
curl https://dev-dindon.cleanhome.tw/health
```

### 6c. 設定快捷指令（建議）

在 `~/.bashrc` 加入：

```bash
# 叮咚到號 開發隧道
alias dev-tunnel='ssh -R 9000:localhost:8001 root@57.182.129.192 -N -o ServerAliveInterval=60'

# 叮咚到號 開發環境 啟動/停止
alias dev-up='cd /home/linux/Dropbox/84-WebCode/00-gemini/6-linux/5-ajz/linebot-medicalqueue && docker compose -f docker-compose.dev.yml up --build -d'
alias dev-down='cd /home/linux/Dropbox/84-WebCode/00-gemini/6-linux/5-ajz/linebot-medicalqueue && docker compose -f docker-compose.dev.yml down'
alias dev-logs='cd /home/linux/Dropbox/84-WebCode/00-gemini/6-linux/5-ajz/linebot-medicalqueue && docker compose -f docker-compose.dev.yml logs -f'
```

生效：

```bash
source ~/.bashrc
```

---

## Step 7：設定 LINE DEV Webhook

1. 打開 https://developers.line.biz/console/
2. 進入 `叮咚到號-DEV` Channel → **Messaging API**
3. Webhook URL 填：

```
https://dev-dindon.cleanhome.tw/webhook
```

4. 點 **Verify** → 應該顯示 **Success**
5. 確認 **Use webhook** 已開啟
6. 確認 **Auto-reply messages** 已關閉

---

## Step 8：測試

用手機 LINE 打開 `叮咚到號-DEV`，送出訊息測試：

| 輸入 | 預期回覆 |
|------|----------|
| `說明` | 使用說明 |
| `萬芳 精神科` | 精神科看診進度 |
| `追蹤 萬芳 精神科 許元彰 我是60號` | 開始追蹤 |
| `我的追蹤` | 追蹤清單 |
| `取消追蹤` | 取消所有追蹤 |

---

## 日常開發流程

### 每天開始開發

```bash
# 1. 啟動 Docker 服務
dev-up

# 2. 開隧道（另一個終端視窗）
dev-tunnel

# 3. 開始寫 code，FastAPI 自動 reload
```

### 改了 Celery 相關的 code

```bash
docker compose -f docker-compose.dev.yml restart worker beat
```

### 改了 requirements.txt

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

### 結束開發

```bash
# 關隧道：Ctrl+C
# 關 Docker
dev-down
```

---

## 常用除錯指令

```bash
# 看所有 log
docker compose -f docker-compose.dev.yml logs -f

# 只看 app
docker compose -f docker-compose.dev.yml logs -f app

# 只看 worker（爬蟲 log）
docker compose -f docker-compose.dev.yml logs -f worker

# 進入 app 容器 debug
docker exec -it medqueue-app bash

# 進入 Redis
docker exec -it medqueue-redis redis-cli

# 手動觸發爬蟲測試
docker exec medqueue-app python -c "
from app.scrapers.registry import adapter_registry
import asyncio

async def test():
    adapter = adapter_registry.get_adapter('wanfang')
    results = await adapter.fetch_all_progress()
    for r in results[:3]:
        print(f'{r.department} {r.doctor_name} {r.clinic_room} 目前: {r.current_number}')

asyncio.run(test())
"
```

---

## 故障排除

### SSH 隧道斷線

```bash
# 重新連
dev-tunnel
```

如果頻繁斷線，可改用 autossh（自動重連）：

```bash
# 安裝
sudo apt install autossh

# 使用（會自動重連）
autossh -M 0 -R 9000:localhost:8001 root@57.182.129.192 -N -o ServerAliveInterval=60 -o ServerAliveCountMax=3
```

加到 alias：

```bash
alias dev-tunnel='autossh -M 0 -R 9000:localhost:8001 root@57.182.129.192 -N -o ServerAliveInterval=60 -o ServerAliveCountMax=3'
```

### Port 衝突

```bash
# 確認 port 是否被佔用
sudo lsof -i :8001
sudo lsof -i :6380
```

### LINE Webhook Verify 失敗

1. 確認隧道有開：`curl https://dev-dindon.cleanhome.tw/health`
2. 確認 `.env.dev` 裡的 LINE credentials 是 DEV Channel 的
3. 確認 app 容器有跑起來：`docker compose -f docker-compose.dev.yml ps`

---

## 安全提醒

- `.env` 和 `.env.dev` 已在 `.gitignore` 中，不會被提交
- SSH 隧道只綁定 VPS 的 `127.0.0.1:9000`，外部無法直接存取
- 開發環境與正式環境共用 MySQL，修改資料時請注意
