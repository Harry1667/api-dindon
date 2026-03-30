# Feature Flags 功能開關管理

## 概述

本專案透過 **環境變數** 集中管理功能開關，所有 flag 定義在 `app/config.py` 的 `Settings` 類別中，
並在 `.env`（正式）/ `.env.dev`（測試）中設定值。

這樣做的好處：
- 測試和正式環境跑同一套程式碼，只靠環境變數切換功能
- 所有開關集中在 `config.py`，一目了然
- 不需改 code 就能開關功能（改 `.env` 後重啟即可）

---

## 目前的 Feature Flags

| 環境變數 | 說明 | 測試預設 | 正式預設 |
|---------|------|---------|---------|
| `ENABLE_MOCK_HOSPITAL` | 啟用測試醫院（模擬假資料） | `true` | `false` |
| `ENABLE_WANFANG_SCRAPER` | 啟用萬芳醫院爬蟲（robots.txt 尚未授權） | `true` | `true` |
| `ENABLE_AUTO_CREATE_TABLES` | 啟動時自動建立資料表（正式環境用 Alembic） | `true` | `false` |

### 既有的環境設定（非 Feature Flag，但會影響行為）

| 環境變數 | 說明 | 測試預設 | 正式預設 |
|---------|------|---------|---------|
| `APP_ENV` | 環境名稱 | `development` | `production` |
| `APP_DEBUG` | Debug 模式（影響 log 等級、SQL echo） | `true` | `false` |

---

## 設定方式

### 在 `.env` 或 `.env.dev` 中新增

```env
# === 功能開關 (Feature Flags) ===
ENABLE_MOCK_HOSPITAL=false
ENABLE_WANFANG_SCRAPER=true
ENABLE_AUTO_CREATE_TABLES=false
```

### 在程式碼中使用

```python
from app.config import settings

if settings.enable_mock_hospital:
    # 測試才跑的邏輯
    ...
```

---

## 新增 Feature Flag 步驟

### 1. 在 `app/config.py` 加欄位

```python
@dataclass
class Settings:
    # ...existing fields...

    # 功能開關 (Feature Flags)
    enable_my_new_feature: bool = field(
        default_factory=lambda: os.getenv("ENABLE_MY_NEW_FEATURE", "false").lower() == "true"
    )
```

### 2. 在 `.env` / `.env.dev` / `.env.example` 加設定

```env
# .env（正式）
ENABLE_MY_NEW_FEATURE=false

# .env.dev（測試）
ENABLE_MY_NEW_FEATURE=true

# .env.example（範本）
ENABLE_MY_NEW_FEATURE=false
```

### 3. 在程式碼中使用

```python
from app.config import settings

if settings.enable_my_new_feature:
    do_something()
```

### 4. （選配）在 `app/main.py` 的啟動 log 加上新 flag

讓啟動時能看到所有 flag 狀態，方便排查問題。

---

## 各 Flag 影響範圍

### `ENABLE_MOCK_HOSPITAL`

- **影響檔案**：`demo_chat.py`, `line_bot.py`
- **作用**：開啟後，使用者輸入「測試」或「test」會觸發模擬醫院資料
- **正式環境**：應關閉，避免使用者看到假資料

### `ENABLE_WANFANG_SCRAPER`

- **影響檔案**：`app/scrapers/registry.py`, `app/main.py`（seed 資料）
- **作用**：控制萬芳醫院爬蟲是否啟用
- **注意**：萬芳醫院 `robots.txt` 設定 `Disallow: /`，正式上線前需取得授權或改用官方 API

### `ENABLE_AUTO_CREATE_TABLES`

- **影響檔案**：`app/main.py`（lifespan 函式）
- **作用**：啟動時是否自動執行 `Base.metadata.create_all`
- **正式環境**：應關閉，改用 Alembic migration 管理 schema 變更

---

## 啟動時確認

系統啟動時會在 log 印出所有 Feature Flag 狀態：

```
🚀 醫院掛號排隊通知系統啟動中...
📋 Feature Flags: env=development, mock_hospital=True, wanfang_scraper=True, auto_create_tables=True
```

---

## 環境對照表

| 項目 | `.env.dev`（測試） | `.env`（正式） |
|------|-------------------|---------------|
| `APP_ENV` | development | production |
| `APP_DEBUG` | true | false |
| `ENABLE_MOCK_HOSPITAL` | true | false |
| `ENABLE_WANFANG_SCRAPER` | true | true |
| `ENABLE_AUTO_CREATE_TABLES` | true | false |
| LINE Channel | 測試頻道 | 正式頻道 |
| MySQL Host | 遠端 aaPanel | Docker 內部 |
| Docker Compose | `docker-compose.dev.yml` | `docker-compose.yml` |
