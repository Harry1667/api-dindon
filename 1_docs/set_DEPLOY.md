# 叮咚到號 — 部署指南

> 最後更新：2026-03-30

## 架構總覽

```
                    LINE Platform
                         │
                         ▼
              ┌─────────────────────┐
              │  Nginx (aaPanel)    │
              │  dindon.cleanhome.tw│
              └────────┬────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
     /webhook       /health      /admin
          │            │            │
          └────────────┼────────────┘
                       ▼
   ┌──────────────────────────────────┐
   │  FastAPI App (app)    :8000     │
   │  app/main.py + app/api/*        │
   └──────────┬───────────────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
┌─────────┐     ┌──────────┐
│ Celery  │     │ Celery   │
│ Worker  │     │ Beat     │
└────┬────┘     └────┬─────┘
     │               │
     └───────┬───────┘
             ▼
      ┌────────────┐       ┌──────────────────┐
      │   Redis    │       │  MySQL (aaPanel)  │
      │   :6379    │       │  57.182.129.192   │
      └────────────┘       └──────────────────┘
```

---

## 兩組環境

| 項目 | 正式環境 | 測試環境 |
|------|---------|---------|
| 位置 | aaPanel 伺服器 | 本機 Linux |
| LINE@ | 正式帳號 | 測試帳號 |
| 環境檔 | `.env` | `.env.dev` |
| Docker Compose | `docker-compose.yml` | `docker-compose.dev.yml` |
| FastAPI port | 8000 (外部) | 8001 (外部) → 8000 (容器) |
| Redis port | 6379 | 6380 (外部) → 6379 (容器) |
| 容器名前綴 | `medqueue-*` | `dindon-dev-*` |
| 可同時跑 | 是（名稱不衝突） | 是 |

---

## Docker 服務

| 服務 | 正式容器名 | 測試容器名 | 說明 |
|------|-----------|-----------|------|
| app | `medqueue-app` | `dindon-dev-app` | FastAPI 主應用 |
| worker | `medqueue-worker` | `dindon-dev-worker` | Celery 爬蟲 + 推播 |
| beat | `medqueue-beat` | `dindon-dev-beat` | Celery 定時排程 |
| redis | `medqueue-redis` | `dindon-dev-redis` | 快取 + 任務佇列 |

---

## 部署步驟

### 正式環境（aaPanel 伺服器）

```bash
# 1. 建置並啟動
docker compose up -d --build

# 2. 確認服務狀態
docker compose ps

# 3. 健康檢查
curl http://localhost:8000/health

# 4. 查看日誌
docker logs -f medqueue-app
docker logs -f medqueue-worker

# 5. 更新 Nginx（如首次部署）
# 在 aaPanel → Website → dindon.cleanhome.tw → Configuration
# 貼入 nginx.conf 的內容
```

### 測試環境（本機 Linux）

```bash
# 1. 啟動測試環境
docker compose -f docker-compose.dev.yml up -d --build

# 2. 確認服務
docker compose -f docker-compose.dev.yml ps

# 3. 健康檢查
curl http://localhost:8001/health

# 4. 查看日誌
docker logs -f dindon-dev-app

# 5. 停止
docker compose -f docker-compose.dev.yml down
```

### 停止服務

```bash
# 正式
docker compose down

# 測試
docker compose -f docker-compose.dev.yml down
```

---

## Nginx 反向代理

域名：`dindon.cleanhome.tw`

所有請求指向 port 8000（FastAPI 主應用）：

| 路徑 | 代理目標 |
|------|---------|
| `/webhook` | `http://127.0.0.1:8000/webhook` |
| `/health` | `http://127.0.0.1:8000/health` |
| `/admin` | `http://127.0.0.1:8000/admin` |
| `/api/hospitals` | `http://127.0.0.1:8000/api/hospitals` |

---

## 環境變數

| 變數 | 正式 (`.env`) | 測試 (`.env.dev`) |
|------|--------------|-------------------|
| `APP_ENV` | `production` | `development` |
| `APP_DEBUG` | `false` | `true` |
| `MYSQL_HOST` | `host.docker.internal` | `57.182.129.192` |
| `ENABLE_MOCK_HOSPITAL` | `false` | `true` |
| `ENABLE_AUTO_CREATE_TABLES` | `false` | `true` |
| `JWT_SECRET_KEY` | 固定值（必設） | 可留空（自動產生） |
| `ADMIN_LINE_USER_ID` | 你的 LINE ID | 可留空 |

---

## 資料庫

| 項目 | 值 |
|------|---|
| 類型 | MySQL (aaPanel 管理) |
| 主機 | `57.182.129.192:3306` |
| 使用者 | `ajz-dindon` |
| 資料庫 | `ajz-dindon` |
| 編碼 | `utf8mb4` |

---

## Celery 排程任務

| 任務 | 頻率 | 說明 |
|------|------|------|
| `scrape_all_hospitals` | 每 60 秒 | 爬取所有醫院看診進度 |
| `check_and_notify` | 每 60 秒 (7:00-21:30) | 檢查追蹤 + 推播通知 |
| `sync_nhi_institutions` | 每日 03:00 | 同步健保機構資料 |
| `sync_master_data` | 每日 04:00 | 同步科別與醫師資料 |

---

## 常用維運指令

```bash
# 查看所有容器
docker compose ps

# 重啟單一服務
docker compose restart app

# 查看 worker 日誌
docker logs -f medqueue-worker

# 進入容器 debug
docker exec -it medqueue-app bash

# 重建單一服務（程式碼更新後）
docker compose up -d --build app

# 清除 Redis 快取
docker exec medqueue-redis redis-cli FLUSHALL

# 資料庫遷移（自動在啟動時執行，也可手動）
docker exec medqueue-app alembic upgrade head

# 查看爬蟲狀態
curl http://localhost:8000/admin/api/dashboard
```

---

## 首次部署 Checklist

- [ ] `.env` 已設定（LINE 金鑰、MySQL 密碼、JWT_SECRET_KEY）
- [ ] `ENABLE_AUTO_CREATE_TABLES=true`（首次建表）或已跑過 `alembic upgrade head`
- [ ] `docker compose up -d --build` 成功
- [ ] `curl http://localhost:8000/health` 回傳 `{"status":"ok"}`
- [ ] Nginx 已更新（貼入 nginx.conf）
- [ ] LINE Developers Console Webhook URL 設為 `https://dindon.cleanhome.tw/webhook`
- [ ] 傳訊息給 LINE Bot 有回應
- [ ] `/admin` 可以登入

---

## 注意事項

1. **切勿將 `.env` / `.env.dev` 提交到 Git**
2. 正式與測試容器名不同，可以同時跑（但正式在 aaPanel，測試在本機）
3. 測試環境掛載原始碼 (`.:/app`)，改 code 自動 reload
4. MySQL 不在 Docker 內，由 aaPanel 管理
5. `line_bot.py` 已退役，所有功能由 `app/main.py` + Celery 接管
