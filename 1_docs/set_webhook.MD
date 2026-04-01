# Webhook 自動部署設定 — aaPanel (57.182.129.192)

> **工具**：[adnanh/webhook](https://github.com/adnanh/webhook) v2.8.0
> **Port**：9000（Nginx 反代 `/hooks/`）
> **設定檔**：`/opt/docker/ajz-dingdon/webhook/hooks.json`

---

## Webhook 列表

| 名稱 | 網址 | 用途 |
|------|------|------|
| dindon-deploy | `https://dindon.cleanhome.tw/hooks/dindon-deploy` | LINE Bot 正式環境轉發 |
| dindon-test | `https://dindon.cleanhome.tw/hooks/dindon-test` | LINE Bot 測試環境轉發 |

**所有 webhook 都需要帶 header：**

```
X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE
```

---

## 使用方式

### 手動觸發部署

```bash
curl -X POST https://dindon.cleanhome.tw/hooks/dindon-deploy \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"
```

### 手動觸發測試

```bash
curl -X POST https://dindon.cleanhome.tw/hooks/dindon-test \
  -H "X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE"

# 查看測試結果
ssh aapanel "cat /opt/docker/ajz-dingdon/logs/test-webhook.log"
```

---

## 架構

```
外網請求
  ↓
Nginx (dindon.cleanhome.tw)
  ↓ /hooks/* 反代到 port 9000
adnanh/webhook (port 9000)
  ↓ 驗證 X-Webhook-Secret header
執行腳本
  ├── webhook-dindon-deploy.sh → LINE Bot 正式環境
  ├── webhook-dindon-test.sh   → LINE Bot 測試環境
```

---

## 伺服器檔案位置

```
/opt/docker/ajz-dingdon/
├── webhook/
│   ├── hooks.json              # webhook 規則設定
│   └── start-webhook.sh        # 啟動腳本
├── scripts/
│   ├── webhook-dindon-deploy.sh  # LINE Bot 正式環境
│   ├── webhook-dindon-test.sh    # LINE Bot 測試環境
└── logs/
    ├── webhook.log               # webhook daemon 日誌
    └── agent.log                 # agent 呼叫日誌
```

---

## 管理指令

```bash
# 查看 webhook 是否在跑
ssh aapanel "ps aux | grep 'webhook -hooks' | grep -v grep"

# 查看 webhook 日誌
ssh aapanel "tail -30 /opt/docker/ajz-dingdon/logs/webhook.log"

# 查看部署日誌
ssh aapanel "tail -30 /opt/docker/ajz-dingdon/logs/deploy.log"

# 重啟 webhook
ssh aapanel "/opt/docker/ajz-dingdon/webhook/start-webhook.sh"

# 停止 webhook
ssh aapanel "pkill -f 'webhook -hooks'"
```

---

## 新增 Webhook

編輯 `/opt/docker/ajz-dingdon/webhook/hooks.json`，在陣列中加入新項目：

```json
{
  "id": "你的hook名稱",
  "execute-command": "/opt/docker/ajz-dingdon/scripts/你的腳本.sh",
  "command-working-directory": "/opt/docker/ajz-dingdon",
  "pass-arguments-to-command": [],
  "trigger-rule": {
    "match": {
      "type": "value",
      "value": "NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE",
      "parameter": {
        "source": "header",
        "name": "X-Webhook-Secret"
      }
    }
  }
}
```

加完後重啟 webhook：

```bash
ssh aapanel "/opt/docker/ajz-dingdon/webhook/start-webhook.sh"
```

新的 webhook 網址就是：`https://dindon.cleanhome.tw/hooks/你的hook名稱`

---

## Gitea 自動部署設定

到 `https://git.twloop.com/david/ajz-dindon/settings/hooks` → **Add Webhook** → **Gitea**：

| 欄位 | 值 |
|------|-----|
| Target URL | `https://dindon.cleanhome.tw/hooks/dindon-deploy` |
| HTTP Method | POST |
| Secret | _(留空)_ |
| Trigger | Push Events |
| Branch filter | `main` |

在 **Headers** 加入：

```
X-Webhook-Secret: NCuHAKTbygEECivqc4IvHx-OH5N7ehnhX28FFee5TLE
```

---

## 部署流程（重要）

> **不要在伺服器上 docker build！** 2GB RAM 會打掛機器。

正確流程：

```bash
# 本地 build + 推 image + 重啟（一鍵）
./scripts/deploy-image.sh
```

此腳本會：
1. 本地 `docker build`
2. `docker save` 匯出 image（約 158MB）
3. `scp` 上傳到伺服器
4. 伺服器 `docker load` + `docker compose up`
5. 健康檢查

Gitea webhook 觸發的 `dindon-deploy` 只會做 `git pull` + `docker compose up`（不 build），適合只改設定檔的情況。如果改了程式碼，要先跑 `deploy-image.sh` 推新 image。

---

## 開機自動啟動

已設定 crontab（claude 帳號）：

```
@reboot /opt/docker/ajz-dingdon/webhook/start-webhook.sh
```

---

## Nginx 設定

在 aaPanel → Website → `dindon.cleanhome.tw` → Config 中的相關區段：

```nginx
# adnanh/webhook — 自動部署
location /hooks/ {
    proxy_pass http://127.0.0.1:9000/hooks/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## 多網址共用 Webhook

webhook daemon 跑在 `0.0.0.0:9000`，同一台伺服器上的**任何域名**都能使用，只要在該網站的 Nginx 加上相同的反代設定。

### 可用的域名（同台伺服器）

| 域名 | 狀態 | Webhook 網址 |
|------|------|-------------|
| `dindon.cleanhome.tw` | 已設定 | `https://dindon.cleanhome.tw/hooks/{hook-id}` |
| `dev-dindon.cleanhome.tw` | 需設定 | `https://dev-dindon.cleanhome.tw/hooks/{hook-id}` |
| `cleanhome.tw` | 需設定 | `https://cleanhome.tw/hooks/{hook-id}` |
| `aiaeoscan.com` | 需設定 | `https://aiaeoscan.com/hooks/{hook-id}` |
| 其他 aaPanel 網站 | 需設定 | 同理 |

> 所有域名共用同一個 webhook daemon 和 hooks.json，hook ID 和 secret 相同。
> 差別只在從哪個域名進來（方便區分用途或給不同專案用）。

### 設定步驟

在 aaPanel → Website → **你要的網站** → Config，加入：

```nginx
# adnanh/webhook
location /hooks/ {
    proxy_pass http://127.0.0.1:9000/hooks/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

儲存後即可使用 `https://該域名/hooks/{hook-id}`。

### 進階：不同專案用不同 hook

如果要讓 `aiaeoscan.com` 有自己的部署 webhook，在 `hooks.json` 加入新的 hook：

```json
{
  "id": "aiaeoscan-deploy",
  "execute-command": "/opt/docker/arkmesa-aiaeoscan/scripts/deploy.sh",
  "command-working-directory": "/opt/docker/arkmesa-aiaeoscan",
  "trigger-rule": {
    "match": {
      "type": "value",
      "value": "另一組secret",
      "parameter": {
        "source": "header",
        "name": "X-Webhook-Secret"
      }
    }
  }
}
```

然後在 `aiaeoscan.com` 的 Nginx 加上反代，就能用：
```
https://aiaeoscan.com/hooks/aiaeoscan-deploy
```

每個 hook 可以有**獨立的 secret**，互不影響。
