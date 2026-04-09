# 部署指南

## 環境資訊

| 項目 | 值 |
|------|-----|
| 域名 | `dd.dl-app.com` |
| 主機 | AWS Lightsail Tokyo（`ssh aapanel`） |
| 路徑 | `/www/wwwroot/dd.dl-app.com` |
| 對外 Port | 8045（容器內 8000） |
| Redis Port | 6399（容器內 6379） |
| 面板 | aaPanel |

## 首次部署

### 1. 在伺服器上 clone 專案

```bash
ssh aapanel
cd /www/wwwroot
git clone <your-repo-url> dd.dl-app.com
cd dd.dl-app.com
```

### 2. 設定環境變數

```bash
cp .env.example .env
nano .env
```

必填項：
- `LINE_CHANNEL_SECRET` — LINE Bot 設定
- `LINE_CHANNEL_ACCESS_TOKEN` — LINE Bot 設定
- `MYSQL_PASSWORD` — MySQL 密碼
- `JWT_SECRET_KEY` — `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `API_BEARER_TOKEN` — `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `ADMIN_LINE_USER_ID` — 管理員 LINE ID（接收告警）

### 3. 建立 MySQL 資料庫

在 aaPanel → Database → 新增：
- 資料庫名: `medical_queue`
- 用戶名: `medqueue`
- 編碼: `utf8mb4`

### 4. aaPanel 設定域名

aaPanel → Website → Add site：
- 域名: `dd.dl-app.com`
- SSL: Let's Encrypt（自動續期）
- Configuration: 貼入 `nginx.conf` 的內容

### 5. 啟動 Docker

```bash
cd /www/wwwroot/dd.dl-app.com
docker compose build
docker compose up -d
```

### 6. 驗證

```bash
# 健康檢查
curl https://dd.dl-app.com/health

# API 測試（帶 token）
curl -H "X-API-Key: <your-token>" https://dd.dl-app.com/api/hospitals

# 查看 log
docker logs -f medqueue-app
docker logs -f medqueue-worker
```

### 7. 設定 LINE Webhook URL

LINE Developers Console → Messaging API → Webhook URL:
```
https://dd.dl-app.com/webhook
```

## 更新部署

```bash
cd /www/wwwroot/dd.dl-app.com
git pull
docker compose build
docker compose up -d
```

## 常用指令

```bash
# 查看容器狀態
docker compose ps

# 查看爬蟲 log
docker logs -f medqueue-worker

# 查看 API log
docker logs -f medqueue-app

# 重啟
docker compose restart

# 在容器內跑測試
docker compose exec app python -m pytest tests/ -v

# 進入容器 shell
docker compose exec app bash
```

## 服務架構

```
dd.dl-app.com (Nginx + SSL)
  │
  ├── /webhook        → medqueue-app:8000  (LINE Bot)
  ├── /api/*          → medqueue-app:8000  (公開 API，需 X-API-Key)
  ├── /admin/*        → medqueue-app:8000  (管理後台，需 JWT)
  ├── /health         → medqueue-app:8000  (健康檢查)
  │
  ├── medqueue-worker (Celery: 爬蟲 + 通知 + 排程)
  └── medqueue-redis  (快取 + 任務佇列，port 6399)
```

## 休診排程

爬蟲自動在以下時段停止（節省伺服器資源）：
- 每天 22:00 ~ 07:00（夜間無看診）
- 週日全天
- 台灣國定假日（元旦、228、清明、兒童節、勞動節、國慶、農曆新年、端午、中秋）

週六照常爬蟲（動態頻率控制會自動降速沒看診的醫院）。
