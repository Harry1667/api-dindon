# 架構審查與升級建議

> 審查日期：2026-03-30
> 範圍：整體專案架構、安全性、程式品質、部署與可維護性

---

## 一、整體評估

| 面向 | 現況評級 | 說明 |
|---|---|---|
| 專案結構 | A | 清楚的分層：models / services / scrapers / api |
| 安全性 | D | 多項重大問題需立即處理 |
| 錯誤處理 | C+ | 基本 try-catch，缺乏重試與告警 |
| 測試覆蓋 | F | tests/ 目錄為空，無自動化測試 |
| 文件品質 | A | 中文文件完整，架構說明清楚 |
| 擴展性 | B | async 架構良好，受限於部分寫死設定 |
| 配置管理 | A | 環境變數 + feature flags 設計佳 |
| 資料庫設計 | A- | 正規化完整、有外鍵約束 |
| 部署就緒度 | B | Docker 完備，但缺少自動 migration |

---

## 二、安全性問題（必須優先處理）

### 2.1 敏感資訊外洩風險 (沒有問題,Git是自己的服務器)

**問題：** `.env` 檔案包含 LINE secret、MySQL 密碼、Admin 密碼等，若不慎提交到 Git 將導致全面洩漏。

**建議：**
- 確認 `.gitignore` 包含 `.env`、`.env.dev`（目前 `.env.dev` 已被 Git 追蹤）
- 生產環境改用 Docker secrets 或 HashiCorp Vault
- 立即輪換已暴露的密鑰

### 2.2 Admin JWT 金鑰強度不足

**問題：** `app/api/admin.py` 中 JWT secret 直接由 admin 密碼 SHA256 產生：
```python
SECRET_KEY = hashlib.sha256(settings.admin_password.encode()).hexdigest()
```
若密碼為弱密碼（如 `changeme`），JWT 也極易被破解。

**建議：**
- 新增獨立的 `JWT_SECRET_KEY` 環境變數，使用 `secrets.token_hex(32)` 產生
- Admin 密碼與 JWT secret 完全解耦

### 2.3 缺少輸入驗證 (未來再處理)

**問題：** 使用者透過 LINE 傳送的文字（醫院名、科別、號碼）未經驗證即進入系統。

**建議：**
- 在 `line_bot.py` 的 `_handle_track_command()` 加入 Pydantic schema 驗證
- 限制號碼為正整數、醫院代碼需存在於資料庫
- 對使用者輸入做 strip / 長度限制

### 2.4 缺少 CORS 設定

**問題：** 若未來加入前端管理介面，目前無 CORS 白名單。

**建議：**
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["https://your-domain.com"])
```

---

## 三、可靠性與錯誤處理

### 3.1 Celery Task 無重試機制

**問題：** `app/tasks/` 中的爬蟲與通知任務失敗後不會重試，單次失敗即遺失。

**建議：**
```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def scrape_hospital(self, hospital_code):
    try:
        ...
    except Exception as exc:
        raise self.retry(exc=exc)
```

### 3.2 Redis 斷線無恢復

**問題：** `CacheService` 啟動時建立 Redis 連線，若 Redis 中途斷開不會自動重連。

**建議：**
- 使用 `redis.asyncio` 的 `retry_on_error` 參數
- 或在每次操作時 wrap try-catch，失敗時 fallback 到直接查 DB

### 3.3 爬蟲靜默失敗

**問題：** Scraper 失敗只 `logger.warning()`，不會觸發告警，管理者無法得知。

**建議：**
- 連續失敗 N 次後發送 LINE 通知給管理員
- 在 `/admin/api/stats` 加入各醫院爬蟲最後成功時間

### 3.4 Healthcheck 端點不存在

**問題：** `docker-compose.yml` 定義了 healthcheck 但 FastAPI 中沒有 `/health` endpoint。

**建議：**
```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

## 四、程式碼組織

### 4.1 main.py 過於肥大

**問題：** `app/main.py` 包含 106 筆醫院種子資料（約 200+ 行），混雜在啟動邏輯中。

**建議：**
- 將醫院資料抽出到 `scripts/seed_hospitals.json` 或 `scripts/seed_hospitals.py`
- `main.py` 只負責載入設定、註冊路由、管理生命週期

### 4.2 醫院別名寫死在程式碼中

**問題：** `app/services/line_bot.py` 中 `HOSPITAL_ALIASES` 字典寫死，目前只有萬芳。

**建議：**
- 已有 `HospitalAlias` model，應改為從資料庫讀取
- 啟動時載入到記憶體快取，定期重新整理
```python
# 改為從 DB 載入
aliases = await session.execute(select(HospitalAlias))
HOSPITAL_ALIASES = {a.alias: a.hospital_code for a in aliases.scalars()}
```

### 4.3 時區處理不一致

**問題：** 多處自行定義 `TW_TZ = timezone(timedelta(hours=8))`，未統一。

**建議：**
- 在 `config.py` 統一定義：
```python
from zoneinfo import ZoneInfo
TW_TZ = ZoneInfo("Asia/Taipei")
```
- 全專案 import 此常數

---

## 五、測試與 CI/CD

### 5.1 無自動化測試

**問題：** `tests/` 目錄為空，`test_all_scrapers.py` 是獨立腳本，無 pytest 整合。

**建議（分階段）：**

**Phase 1 — 核心邏輯單元測試：**
- `services/line_bot.py` 的指令解析
- `services/tracker.py` 的追蹤建立/取消
- `scrapers/` 的 HTML 解析（用固定 HTML fixture）

**Phase 2 — API 整合測試：**
- 使用 `httpx.AsyncClient` + `TestClient` 測試 webhook
- Mock LINE API 回應

**Phase 3 — CI 整合：**
- GitHub Actions 執行 `pytest` + 覆蓋率報告
- PR 合併前必須通過測試

### 5.2 缺少 Linter / Formatter

**建議：**
- 加入 `ruff` 作為 linter + formatter
- 加入 `pyproject.toml` 統一工具設定
- pre-commit hook 確保程式碼品質

---

## 六、資料庫與效能

### 6.1 連線池設定需調整

**現況：** pool_size=10, max_overflow=20

**建議：**
- 加入 `pool_pre_ping=True` 防止連線過期
- 加入 `pool_recycle=3600` 避免 MySQL wait_timeout 斷線
```python
engine = create_async_engine(
    url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)
```

### 6.2 Migration 流程需明確化

**問題：** 生產環境 `ENABLE_AUTO_CREATE_TABLES=false`（正確），但沒有自動執行 Alembic migration。

**建議：**
- 在部署腳本中加入 `alembic upgrade head`
- 或在 Dockerfile 的 entrypoint 中執行

### 6.3 爬蟲頻率缺乏彈性

**問題：** 所有醫院統一 60 秒爬一次，但 Hospital model 已有 `scrape_interval` 欄位。

**建議：**
- Celery beat 改為讀取各醫院的 `scrape_interval` 動態排程
- 冷門時段（深夜）降低頻率以節省資源

---

## 七、監控與可觀測性

### 7.1 缺少結構化日誌

**建議：**
- 使用 `structlog` 或 `python-json-logger` 輸出 JSON 格式日誌
- 包含 request_id、hospital_code、user_id 等欄位
- 方便後續接入 ELK / Loki

### 7.2 缺少應用指標

**建議：**
- 加入 `prometheus-fastapi-instrumentator` 自動收集 HTTP metrics
- 自訂 metrics：爬蟲成功率、通知送達率、活躍追蹤數

### 7.3 缺少 Webhook 請求日誌

**問題：** 無法追蹤 LINE 傳送了什麼、系統回覆了什麼。

**建議：**
- 加入 FastAPI middleware 記錄 request/response
- 敏感資料（signature）需脫敏

---

## 八、建議優先順序

| 優先級 | 項目 | 預估工作量 |
|---|---|---|
| P0 | 修復 `.env.dev` 被 Git 追蹤 | 10 分鐘 |
| P0 | 加入 `/health` endpoint | 5 分鐘 |
| P0 | JWT secret 獨立化 | 30 分鐘 |
| P1 | 使用者輸入驗證 | 2 小時 |
| P1 | Celery task 重試機制 | 1 小時 |
| P1 | Redis 斷線恢復 | 1 小時 |
| P1 | 醫院種子資料抽離 main.py | 1 小時 |
| P2 | 醫院別名改為 DB 驅動 | 2 小時 |
| P2 | 統一時區處理 | 30 分鐘 |
| P2 | 核心邏輯單元測試 | 4 小時 |
| P2 | 連線池加入 pool_pre_ping | 10 分鐘 |
| P3 | 結構化日誌 | 3 小時 |
| P3 | Prometheus metrics | 2 小時 |
| P3 | 動態爬蟲頻率 | 3 小時 |
| P3 | Linter / pre-commit hook | 1 小時 |
