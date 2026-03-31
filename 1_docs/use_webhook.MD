# Webhook 使用手冊 — 叮咚到號

> 本文件說明每個 webhook 的**用途、使用時機、呼叫方式**。
> 技術設定請參考 [set_webhook.MD](set_webhook.MD)。

---

## 快速總覽

| Webhook | 用途 | 適合誰用 | 風險等級 |
|---------|------|---------|---------|
| `dindon-deploy` | 部署更新 | 開發者 | 高 — 會重啟服務 |
| `dindon-test` | 測試環境 LINE Bot | 開發者 | 低 |
| `dindon-restart` | 重啟容器 | 開發者 / 管理員 | 中 — 短暫斷線 |
| `dindon-logs` | 查看即時日誌 | 開發者 / 管理員 | 低 — 唯讀 |
| `dindon-clear-cache` | 清除 Redis 快取 | 開發者 / 管理員 | 中 — 資料暫時消失 |

---

## 共用資訊

**Base URL**：`https://dindon.cleanhome.tw/hooks/`

**認證 Header**（所有 webhook 都需要）：

```
X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE
```

**呼叫方式**：HTTP POST

---

## 1. dindon-deploy — 部署更新

### 什麼時候用

- 推了新程式碼到 Gitea `main` 分支後
- 只改了設定檔（.env、docker-compose 等），不需要重新 build image
- Gitea webhook 自動觸發（如果有設定的話）

### 它會做什麼

1. `git pull origin main` — 拉最新程式碼
2. `docker compose -f docker-compose.prod.yml up -d` — 重啟容器
3. 健康檢查

### 注意事項

- **不會 build image**。如果改了 Python 程式碼，要先在本地跑 `./scripts/deploy-image.sh` 推新 image
- 執行時間約 10-15 秒，期間服務會短暫中斷
- 部署日誌：`ssh aapanel "tail -30 /opt/docker/ajz-dingdon/logs/deploy.log"`

### 呼叫

```bash
curl -X POST https://dindon.cleanhome.tw/hooks/dindon-deploy \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"
```

---

## 2. dindon-test — 測試環境 LINE Bot

### 什麼時候用

- 確認測試環境的 LINE Bot 是否正常運作
- 檢查容器狀態、記憶體、健康狀態
- 部署後快速驗證服務是否正常

### 它會做什麼

1. 呼叫 `/health` 端點
2. 列出所有容器狀態
3. 顯示記憶體使用量
4. 取得 app 最近 5 筆日誌

### 呼叫

```bash
curl -X POST https://dindon.cleanhome.tw/hooks/dindon-test \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"

# 查看結果
ssh aapanel "cat /opt/docker/ajz-dingdon/logs/test-webhook.log | tail -20"
```

### 回傳範例

```
[Health] {"status":"ok","version":"0.1.0","checks":{"redis":true,"database":true}}
[Containers]
medqueue-app Up 4 minutes (healthy)
medqueue-beat Up 4 minutes
medqueue-notify Up 4 minutes
medqueue-redis Up 4 minutes
medqueue-worker Up 4 minutes
[Memory]
Mem: 1.9Gi used 1.1Gi free 71Mi
```

---

## 3. dindon-restart — 重啟容器

### 什麼時候用

- LINE Bot 沒有回應，但伺服器還活著
- 爬蟲卡住不動
- 記憶體異常升高，想快速恢復
- 改了 .env 設定後需要重啟生效

### 它會做什麼

1. `docker compose restart` — 重啟 5 個容器（app、worker、notify、beat、redis）
2. 等待 5 秒
3. 健康檢查

### 注意事項

- 重啟期間（約 5-10 秒）LINE Bot 會斷線，用戶訊息可能遺失
- 不會清除資料，Redis 資料保留
- 正在執行的爬蟲任務會被中斷，下個排程週期會重新跑

### 呼叫

```bash
curl -X POST https://dindon.cleanhome.tw/hooks/dindon-restart \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"

# 確認結果
ssh aapanel "tail -10 /opt/docker/ajz-dingdon/logs/restart.log"
```

### LINE Bot 整合構想

未來可在 LINE Bot 中加入管理員指令：

```
管理員傳送：restart
Bot 回覆：正在重啟服務...
Bot 回覆：重啟完成，Health: OK ✓
```

實作方式：在 LINE Bot 的訊息處理中，管理員發送特定指令時，用 `httpx.post()` 呼叫此 webhook。

---

## 4. dindon-logs — 查看即時日誌

### 什麼時候用

- 用戶回報問題，需要快速查看日誌
- 確認爬蟲是否正常在跑
- 檢查有沒有錯誤訊息
- 不想 SSH 登入伺服器時

### 它會做什麼

取得三個容器的最近日誌：
- `medqueue-app` — FastAPI 主程式（最近 30 筆）
- `medqueue-worker` — 爬蟲任務（最近 15 筆）
- `medqueue-notify` — 推播通知（最近 15 筆）

### 注意事項

- 唯讀操作，完全安全
- 回傳內容會直接輸出到 webhook response body
- 日誌可能包含用戶資料，注意不要外洩

### 呼叫

```bash
# 回傳會直接顯示日誌內容
curl -X POST https://dindon.cleanhome.tw/hooks/dindon-logs \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"
```

### LINE Bot 整合構想

管理員指令查看即時狀態：

```
管理員傳送：logs
Bot 回覆：
=== app (最近 5 筆) ===
INFO: 127.0.0.1 - "POST /webhook" 200
INFO: 127.0.0.1 - "GET /health" 200
...
```

---

## 5. dindon-clear-cache — 清除 Redis 快取

### 什麼時候用

- 爬蟲資料異常（顯示舊資料、數字不對）
- 更換了醫院爬蟲邏輯後，需要清除舊的快取
- Redis 記憶體過高
- 偵錯時需要乾淨的狀態

### 它會做什麼

1. 記錄清除前的 key 數量
2. `FLUSHDB` — 清除整個 Redis DB
3. 記錄清除後的 key 數量

### 注意事項

- **會清除所有快取資料**，包括：
  - 醫院看診進度快取
  - 用戶追蹤狀態的快取
- **不會影響**：
  - MySQL 中的持久化資料（追蹤記錄、用戶資料）
  - Celery 排程（beat 會自動重建）
- 清除後第一次查詢會比較慢（需要重新爬取）
- 正常情況下 1-2 分鐘內快取會自動重建

### 呼叫

```bash
curl -X POST https://dindon.cleanhome.tw/hooks/dindon-clear-cache \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"

# 確認結果
ssh aapanel "tail -10 /opt/docker/ajz-dingdon/logs/clear-cache.log"
```

### 回傳範例

```
Cache cleared. Before: 5286 / After: 0
```

### LINE Bot 整合構想

```
管理員傳送：清除快取
Bot 回覆：已清除 5286 筆快取，資料將在下次爬取時重建
```

---

## LINE Bot 管理員指令整合方案

未來可將 webhook 整合到 LINE Bot，讓管理員直接在 LINE 中操作：

### 指令對照表

| LINE 指令 | 觸發的 Webhook | 說明 |
|-----------|---------------|------|
| `status` | dindon-test | 查看系統狀態 |
| `logs` | dindon-logs | 查看最近日誌 |
| `restart` | dindon-restart | 重啟服務 |
| `清除快取` | dindon-clear-cache | 清除 Redis |
| `deploy` | dindon-deploy | 部署更新 |

### 實作重點

1. **權限控制**：只有 `ADMIN_LINE_USER_ID` 可以執行
2. **呼叫方式**：在 FastAPI 中用 `httpx` 呼叫 `http://localhost:9000/hooks/{id}`（走內網，不經過 Nginx）
3. **回覆格式**：解析 webhook 回傳內容，格式化後回覆給管理員

```python
# 範例：在 LINE Bot 訊息處理中
import httpx

WEBHOOK_SECRET = "NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"
WEBHOOK_BASE = "http://localhost:9000/hooks"

async def handle_admin_command(command: str) -> str:
    headers = {"X-Webhook-Secret": WEBHOOK_SECRET}

    if command == "status":
        r = await httpx.AsyncClient().post(f"{WEBHOOK_BASE}/dindon-test", headers=headers)
        return "系統狀態檢查已觸發，請查看日誌"

    if command == "logs":
        r = await httpx.AsyncClient().post(f"{WEBHOOK_BASE}/dindon-logs", headers=headers)
        return r.text[:2000]  # LINE 訊息上限

    if command == "restart":
        r = await httpx.AsyncClient().post(f"{WEBHOOK_BASE}/dindon-restart", headers=headers)
        return "服務重啟中，約 10 秒後恢復"

    if command == "清除快取":
        r = await httpx.AsyncClient().post(f"{WEBHOOK_BASE}/dindon-clear-cache", headers=headers)
        return f"快取已清除：{r.text}"
```

---

## 常見情境

### 情境 1：LINE Bot 沒回應

```
1. 先呼叫 dindon-test 確認狀態
2. 如果容器掛了 → 呼叫 dindon-restart
3. 如果還是不行 → 呼叫 dindon-logs 看錯誤
4. 如果是快取問題 → 呼叫 dindon-clear-cache
```

### 情境 2：推了新程式碼

```
1. 如果只改了設定檔 → 呼叫 dindon-deploy
2. 如果改了 Python 程式碼 → 先本地跑 ./scripts/deploy-image.sh
3. 部署後呼叫 dindon-test 驗證
```

### 情境 3：用戶說資料不對

```
1. 呼叫 dindon-logs 查看爬蟲日誌
2. 如果爬蟲正常但資料舊 → 呼叫 dindon-clear-cache
3. 等 1-2 分鐘讓快取重建
```

---

## 安全提醒

- **Secret 不要外洩**：任何人拿到 secret 都能觸發部署或清快取
- **LINE Bot 整合時走內網**：用 `http://localhost:9000` 而非外網 URL
- **管理員指令要驗證身份**：用 `ADMIN_LINE_USER_ID` 比對
- **日誌可能含用戶資料**：dindon-logs 的回傳不要直接轉發給非管理員
