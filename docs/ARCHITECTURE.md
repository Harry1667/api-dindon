# 叮咚到號 — 系統架構文件

> 最後更新：2026-03-30
> 版本：MVP v1

---

## 專案目標

透過 LINE Bot 讓台灣醫院看診病患即時追蹤叫號進度，快到號時主動推播通知。
目標用戶：帶小孩看病的媽媽、老人家。

## v1 範圍

- 28 家醫院即時看診進度爬蟲
- LINE Bot 對話式查詢 + 追蹤
- 3 種通知模式（每號/輕量/最後）
- Admin 後台（統計 + 爬蟲健康 + 回饋）
- 使用分析埋點 + 漏斗

## 技術棧

| 層 | 技術 | 用途 |
|---|------|------|
| Web Framework | FastAPI 0.115+ | 非同步 API 伺服器 |
| Task Queue | Celery 5.4+ + Redis | 排程爬蟲 + 通知 |
| Database | MySQL 8.0+ (aiomysql) | 持久化資料 |
| ORM | SQLAlchemy 2.0+ async | 資料模型 |
| Migration | Alembic 1.14+ | DB schema 版本管理 |
| Cache | Redis 7 | 看診進度快取 (5min TTL) |
| HTTP Client | httpx 0.28+ | 非同步爬蟲請求 |
| HTML Parser | BeautifulSoup4 + lxml | 醫院網頁解析 |
| LINE SDK | line-bot-sdk 3.11+ | LINE Messaging API v3 |
| Container | Docker Compose 3.8 | 部署 |
| Reverse Proxy | Nginx (aaPanel) | HTTPS + 反向代理 |

## 系統架構圖

```
                         ┌──────────────┐
                         │  LINE User   │
                         │ (媽媽/老人)   │
                         └──────┬───────┘
                                │
                         LINE Messaging API
                                │
                    ┌───────────▼───────────┐
                    │   FastAPI (port 8000)  │
                    │                       │
                    │  POST /webhook ──► demo_chat.handle_message()
                    │  GET  /health  ──► Redis + DB 健康檢查
                    │  POST /admin/* ──► JWT auth + 管理功能
                    └───────┬───────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
     ┌────────▼──────┐ ┌───▼────┐ ┌──────▼──────┐
     │    MySQL      │ │ Redis  │ │ Celery Beat │
     │  12 tables    │ │ cache  │ │  + Workers  │
     │               │ │ (5min  │ │             │
     │  tracking_    │ │  TTL)  │ │ every 60s:  │
     │  tasks        │ │        │ │ - scrape    │
     │  clinic_      │ │ queue  │ │ - notify    │
     │  progress     │ │ (broker│ │             │
     │  users        │ │  for   │ │ daily:      │
     │  analytics    │ │ celery)│ │ - nhi_sync  │
     │  ...          │ │        │ │ - master    │
     └───────────────┘ └────────┘ └──────┬──────┘
                                         │
                              ┌──────────▼──────────┐
                              │  28 Hospital Scrapers│
                              │                     │
                              │  HTML parse (BS4)   │
                              │  JSON API (httpx)   │
                              │  POST AJAX (httpx)  │
                              └─────────────────────┘
```

## 資料庫 Schema

| 表 | 用途 | 主要欄位 |
|---|------|---------|
| hospitals | 醫院登錄（28 筆） | code(PK), name, adapter_name, is_active |
| users | LINE 用戶 | line_user_id(unique), display_name |
| tracking_tasks | 追蹤任務 | user_id, hospital_code, user_number, status, notify_mode |
| clinic_progress | 看診進度快照 | hospital_code, doctor_name, current_number, fetched_at |
| hospital_aliases | 醫院別名 | hospital_code(FK), alias |
| tracking_feedback | 追蹤回饋 | task_id, end_reason, is_correct |
| nhi_institution | 衛福部機構資料 | 每日同步 |
| user_query_history | 查詢歷史 | user_id, hospital_code, use_count |
| department | 科別主檔 | hospital_code, name |
| doctor | 醫師主檔 | hospital_code, department, name |
| notification | 通知紀錄 | task_id, type, sent_at |
| analytics_events | 使用分析 | user_id, event_type, metadata, created_at |

## 核心資料流

```
1. 爬蟲循環（每 60 秒）
   Celery Beat → scrape_all_hospitals()
   → 各 adapter.fetch_all_progress()
   → Redis cache (5min TTL) + MySQL clinic_progress

2. 通知循環（每 60 秒，7:00-21:30）
   Celery Beat → check_and_notify()
   → 查詢 active tracking_tasks
   → 比對 clinic_progress.current_number vs task.user_number
   → LINE push notification → 更新 task status

3. 用戶查詢
   LINE message → webhook → demo_chat.handle_message()
   → 查詢 Redis cache → 回覆 LINE
   → 如果要追蹤 → 建立 tracking_task
```

## 爬蟲系統

- **Base class:** `app/scrapers/base.py` — `BaseHospitalAdapter`
- **Registry:** `app/scrapers/registry.py` — 集中註冊所有 adapter
- **三種抓取模式:**
  - HTML parse (BeautifulSoup4): cathay, mackay, wanfang, femh, chgh, fjuh
  - JSON API (httpx): changgung(7院), newtaipei_united, shinkong, tzuchi, kaohsiung_united
  - POST AJAX (httpx): ntuh, tsgh, tpvgh
- **動態頻率:** 連續 3 次空結果 → 降頻到 5 分鐘

## 通知模式

| 模式 | 觸發條件 | 適用場景 |
|------|---------|---------|
| NORMAL | 每次叫號變動 | 需要密切關注 |
| LIGHT (預設) | 剩 10、5、3、1、0 號 | 一般使用 |
| FINAL | 剩 3 號內 | 不想被打擾 |

## Docker 服務

| Service | 角色 | Port |
|---------|------|------|
| app | FastAPI webhook | 8000 |
| linebot | demo_chat 伺服器 | 5000 |
| worker | Celery workers | - |
| beat | Celery Beat 排程器 | - |
| redis | Task queue + cache | 6379 |
| mysql | 外部管理 (aaPanel) | 3306 |

## 環境變數

見 `.env.example`。關鍵變數：
- `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN` — LINE API 憑證
- `MYSQL_*` — 資料庫連線
- `REDIS_URL` — Redis 連線
- `JWT_SECRET_KEY` — Admin JWT 簽名金鑰
- `ADMIN_LINE_USER_ID` — 管理員 LINE ID（接收告警）
- `ENABLE_*` — Feature flags

## 目前進度

- [x] 28 家醫院爬蟲
- [x] LINE Bot 串接 + 對話引擎
- [x] 追蹤 + 通知系統
- [x] Admin 後台
- [x] Docker 部署配置
- [x] 通知原子性修復
- [x] Redis 超時 + 錯誤處理
- [x] Health endpoint（含 Redis/DB 健康檢查）
- [x] JWT 獨立化
- [x] 輸入驗證（訊息長度 500 字、號碼上限 9999）
- [x] Celery 重試（notify task）
- [x] 結構化日誌（python-json-logger）
- [x] 爬蟲告警（連續失敗 3 次通知管理員）
- [x] 過號自動處理（30 分鐘超時停止）
- [x] 第一次使用引導（歡迎訊息改版）
- [x] 使用分析埋點（analytics_events 表）
- [x] Admin 儀表板增強（/admin/api/dashboard）
- [x] 核心路徑測試（17 個測試全通過）
- [x] DB pool_pre_ping
- [ ] main.py 種子資料抽離到 JSON
- [ ] Alembic migration 自動化

## 設計決策

| 決策 | 選擇 | 原因 |
|------|------|------|
| 對話引擎 | demo_chat.py (in-memory state) | 快速原型，未來可遷移到 Redis state |
| 快取策略 | Redis 5min TTL | 平衡即時性和醫院伺服器負擔 |
| 通知載體 | LINE Bot | 台灣 2100 萬用戶，免安裝 |
| 分析 | MySQL analytics_events 表 | 不依賴外部服務，資料完整控制 |
| 爬蟲模式 | Adapter pattern + Registry | 容易新增醫院 |
