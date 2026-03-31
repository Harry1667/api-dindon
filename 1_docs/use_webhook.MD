# Webhook 使用手冊 — 叮咚到號 LINE Bot 轉發

> 所有 webhook 都是 LINE Bot 訊息轉發端點。
> 技術設定請參考 [set_webhook.MD](set_webhook.MD)。

---

## Webhook 列表

| Webhook | 網址 | 狀態 | 說明 |
|---------|------|------|------|
| dindon-deploy | `https://dindon.cleanhome.tw/hooks/dindon-deploy` | 使用中 | LINE Bot 正式環境轉發 |
| dindon-test | `https://dindon.cleanhome.tw/hooks/dindon-test` | 使用中 | LINE Bot 測試環境轉發 |
| linebot-agent1 | `https://dindon.cleanhome.tw/hooks/linebot-agent1` | 預留 | 待定義 |
| linebot-agent2 | `https://dindon.cleanhome.tw/hooks/linebot-agent2` | 預留 | 待定義 |
| linebot-agent3 | `https://dindon.cleanhome.tw/hooks/linebot-agent3` | 預留 | 待定義 |

---

## 共用認證

所有 webhook 都需要帶 header：

```
X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE
```

---

## 呼叫方式

### curl

```bash
# 正式環境
curl -X POST https://dindon.cleanhome.tw/hooks/dindon-deploy \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"

# 測試環境
curl -X POST https://dindon.cleanhome.tw/hooks/dindon-test \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"

# 預留 agent
curl -X POST https://dindon.cleanhome.tw/hooks/linebot-agent1 \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"
```

### Python（LINE Bot 內部呼叫）

從 LINE Bot 內部呼叫走內網（localhost），不經 Nginx：

```python
import httpx

WEBHOOK_SECRET = "NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"
WEBHOOK_BASE = "http://localhost:9000/hooks"
HEADERS = {"X-Webhook-Secret": WEBHOOK_SECRET}

async def call_webhook(hook_id: str, data: dict = None):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{WEBHOOK_BASE}/{hook_id}",
            headers=HEADERS,
            json=data,
        )
        return r.text
```

### LINE Developers 設定

在 LINE Developers Console 設定 Webhook URL：

| 環境 | Webhook URL |
|------|------------|
| 正式 | `https://dindon.cleanhome.tw/hooks/dindon-deploy` |
| 測試 | `https://dindon.cleanhome.tw/hooks/dindon-test` |

---

## 預留 Agent 用途規劃

3 個預留的 webhook 可用於未來擴充 LINE Bot 功能：

| Agent | 可能用途 | 範例 |
|-------|---------|------|
| linebot-agent1 | 排程通知 | 定時推播看診提醒 |
| linebot-agent2 | 外部服務串接 | 接收第三方系統回調 |
| linebot-agent3 | 管理指令 | 管理員遠端操作 |

### 啟用預留 Agent

1. 編輯伺服器上的腳本：

```bash
ssh aapanel "vi /opt/docker/ajz-dingdon/scripts/webhook-agent1.sh"
```

2. 寫入實際邏輯，例如：

```bash
#!/bin/bash
# linebot-agent1 — 排程通知
LOG="/opt/docker/ajz-dingdon/logs/agent.log"
echo "[$(date)] agent1: $1" >> "$LOG"

# 你的邏輯寫在這裡
# 例如呼叫 LINE Bot API 發送推播
```

3. 重啟 webhook daemon：

```bash
ssh aapanel "/opt/docker/ajz-dingdon/webhook/start-webhook.sh"
```

---

## 查看日誌

```bash
# webhook daemon 日誌（所有 hook 的觸發紀錄）
ssh aapanel "tail -30 /opt/docker/ajz-dingdon/logs/webhook.log"

# agent 呼叫日誌
ssh aapanel "tail -30 /opt/docker/ajz-dingdon/logs/agent.log"
```

---

## 安全提醒

- **Secret 不要外洩**：任何人拿到 secret 都能呼叫所有 webhook
- **LINE Bot 內部走內網**：用 `http://localhost:9000` 而非外網 URL，避免繞出去再繞回來
- **每個 agent 可以改成獨立 secret**：在 `hooks.json` 中各設不同 value
