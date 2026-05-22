---
name: hdw-proxycli
description: |
  AI Proxy CLI 管理與除錯。管理 proxy-cli 服務（gRPC + 儀表板），
  多 provider（Claude/Gemini/Codex/...）動態切換、憑證、fallback chain、
  多模態（圖/PDF/影片/音訊/YouTube）路由、媒體生成、部署、觀測、備份/還原。
  Use when: "proxycli", "proxy-cli", "AI proxy", "gRPC proxy",
  "provider fallback", "claude quota", "gemini quota", "openai quota",
  "clip.twloop.com", "port 50051", "port 8091", "effort", "routing",
  "備份 DB", "prometheus metrics", "auto route",
  "/api/chat", "/api/generate", "/api/embed",
  "/api/generate/async", "/api/jobs", "media job", "async job", "job_id",
  "讀圖", "讀 PDF", "youtube_urls", "TTS", "生圖", "多模態",
  "Gemini CLI 讀圖", "codex 讀圖", "codex 生圖", "gpt-image-2",
  "image generation", "image_generation tool", "媒體生成",
  "image-to-image", "variation", "edit image", "改圖",
  "quality tier", "quality fast", "quality best",
  "x-pcli-error-code", "trailing metadata", "gRPC trailers",
  "not_found", "error_code"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - AskUserQuestion
---

# /proxycli — AI Proxy CLI 管理 Skill

管理 proxy-cli 服務（gRPC + dashboard），多 provider 動態切換、觀測、部署。

## 細節資料（progressive disclosure）

主檔保持精簡，以下情境用 Read 載入對應檔案：

| 需要時 Read | 內容 |
|-------------|------|
| `references/troubleshooting.md` | 完整 11 個故障情境（PMTU 黑洞、DSM ACL、crashloop 等）|
| `references/client-examples.md` | Python `use_proxycli` SDK / 直連 gRPC / Node.js / TypeScript 完整範例 |
| `references/config-yaml.md` | `config.yaml` 完整可用範本（所有 provider 鍵值、cache、routing 等）|
| `proxy-cli` repo `docs/api.md` | **完整 REST API spec**（`/api/chat`、`/api/generate`、`/api/embed`、`/api/usage/media` schema + 範例 + error_code 列舉）|

## ⚠️ Claude CLI Provider — ToS 灰區（2026-04-19 大清理）

本專案用 `claude --print` 包裝 Claude Code subscription。這在 Anthropic ToS 上屬灰區，**2026-04 實測帳號被 Anthropic 封鎖**。以下行為**已從程式碼移除，不可重新加回來**：

1. **❌ 偽造 OAuth token 欄位** — `_patch_claude_creds()` 已於 2026-04-19 刪除。不可寫死 `rateLimitTier = "default_claude_max_20x"` 或 `subscriptionType = "max"`；不可主動呼叫 `api.anthropic.com/api/oauth/claude_cli/roles` 抓 `org_uuid` 回寫 token 檔案。
2. **❌ 多組 OAuth slot 輪替** — `_discover_slots` 只載入 slot-0；dashboard 新增 slot API 回 403；OAuth web flow 新帳號會**覆蓋 slot-0**（不再建 slot-N）；SQLite restore 只還原 `slot_id=0`。
3. **❌ 排程式 health probe** — `_probe_task` / `_health_probe_loop` / `health_probe()` 全刪，改走 lazy detection（請求失敗時 `_is_auth_error` / `_is_quarantine_error` 即時偵測）。`config.yaml` 的 `health_probe_interval` 已 deprecated（保留 key 避免破壞舊 config）。
4. **❌ `src/direct.py` 用 OAuth Bearer token 打 Anthropic API** — `_call_claude()` 已改成 `_call_claude_apikey()`，只接受 `ANTHROPIC_API_KEY` env var 付費模式。沒有 env var 時 Claude direct API 路徑直接 return None，流量走 fallback chain。
5. **❌ 單帳號日用量無上限** — `db.py:check_provider_quota` 強制 claude 預設 300k tokens/day cap；超過觸發 fallback chain（自動跳過任何用 Claude OAuth 的路徑）。
6. **🔒 帳號風控訊號偵測** — `_is_quarantine_error` 偵測 `suspended` / `abuse` / `risk review` / `device verification` / `account anomaly` / `challenge` / `policy violation` 等 keyword，命中後 slot 被**永久隔離**（`mark_quarantined`），不進 fallback、不可由 `mark_healthy` 恢復，只能由管理員手動在 dashboard 清除。

**若 Claude 帳號再次被封：**
- 把 Claude 從 `auto_router.py` 主路由移除，讓 direct API provider（DeepSeek / OpenAI / Gemini）接管
- **不要換帳號重跑** — Anthropic 可從 IP + 行為指紋識別
- 考慮付費 Anthropic API Key（設 `ANTHROPIC_API_KEY` env var 啟用 `_call_claude_apikey` 合規路徑）

詳見專案倉庫的 `CLAUDE.md` / `DESIGN.md`「ToS 灰區」章節。

## 服務資訊

| 項目 | 值 |
|------|------|
| 伺服器 | **NAS DS923+（192.168.0.126）**（2026-04-18 從 aapanel 搬回 NAS） |
| Docker 路徑 | `/volume1/docker/proxy-cli/` |
| SSH 別名 | `nas`（key: `~/.ssh/id_ed25519_nas`，port 33333，user `docker`）|
| 本地路徑 | `/Users/macpro-david/Library/CloudStorage/Dropbox/84-WebCode/01-mac/1-info/proxy-cli` |
| 容器名稱 | `ai-proxy`（compose service `proxy`）|
| gRPC port | `0.0.0.0:50051`（NPM `cli.twloop.com` 反代 — ⚠️ **必須用 `grpc_pass`，不是 `proxy_pass`**；見「常見問題」外網 gRPC 段）|
| Dashboard port | `0.0.0.0:8091 → 8080`（NPM `clip.twloop.com` 反代）|
| OAuth relay | container 80 / 1455 EXPOSE，**host 80 已被 DSM 佔用，目前未對外**；creds 從 aapanel 搬來不需重新 OAuth |
| 域名 | `clip.twloop.com` (HTTP) / `cli.twloop.com` (gRPC)，由 NAS NPM 反代 |
| 資源上限 | RAM 2g（NAS kernel 不支援 CPU CFS，無 cpus 限制） |
| 日誌輪轉 | json-file，10MB × 3 份 |
| 舊位置（已停） | aapanel `/opt/docker/proxy-cli/`（容器 stop 但檔案保留作回滾備援） |

### NAS 部署常用指令

```bash
# 部署（rsync + build）— 注意 NAS 用 docker 帳號 PATH 沒 /usr/bin/rsync，要加 --rsync-path
rsync -avz --rsync-path=/usr/bin/rsync \
  --exclude='.env' --exclude='__pycache__' --exclude='.git' \
  --exclude='*.pyc' --exclude='.DS_Store' --exclude='.venv' \
  --exclude='data/' --exclude='creds/' --exclude='certs/' \
  --exclude='deploy-aapanel/' --exclude='*.csv' --exclude='*.log' \
  --exclude='proto/aiproxy_pb2.py' --exclude='proto/aiproxy_pb2_grpc.py' \
  --exclude='.pytest_cache/' --exclude='.claude/' --exclude='.gstack/' \
  -e "ssh -p 33333 -i ~/.ssh/id_ed25519_nas -o StrictHostKeyChecking=no" \
  ./ docker@192.168.0.126:/volume1/docker/proxy-cli/

# build + restart — ⚠️ 必須用 -f deploy-nas/docker-compose.yml
# 專案根目錄的 docker-compose.yml 是 Mac 開發用（有 cpus 限制，NAS kernel 不支援）
ssh nas "cd /volume1/docker/proxy-cli && /usr/local/bin/docker compose -f deploy-nas/docker-compose.yml up -d --build"

# 查 log
ssh nas "/usr/local/bin/docker logs ai-proxy --tail 50"

# 健康檢查
ssh nas "curl -s http://localhost:8091/healthz && curl -s http://localhost:8091/ready"

# 推單一檔案到 NAS（scp 必須加 -O，sftp subsystem 被禁）
scp -O -P 33333 -i ~/.ssh/id_ed25519_nas config.yaml docker@192.168.0.126:/volume1/docker/proxy-cli/config.yaml
```

### NAS-specific 注意事項

- **scp 必須 `-O`**：DSM 把 sftp subsystem 關了，新版 scp 走 sftp 會失敗。
- **rsync 必須 `--rsync-path=/usr/bin/rsync`**：non-interactive ssh PATH 沒帶到 rsync。
- **`rm` 被 docker 帳號 .profile 攔截**：覆寫檔案改用 mv 改名再 scp。
- **CPU CFS 不支援**：compose 不能設 `cpus: "x.x"`，啟動會 `NanoCPUs can not be set` 報錯。
- **OAuth 重登入需先停 DSM**：80/1455 host port 被 DSM 佔用，要重新 OAuth 得改 DSM port 或借容器內網跑。
- **🔴 DSM ACL 會把 bind mount 變 read-only**（2026-04-19 踩到）：host 端 `ls -la` 顯示 `drwxrwxrwx+`（有 `+` = NFSv4 ACL），**但容器內 `app` user 依然寫不了檔**。症狀：
  - codex 每次請求卡 180s timeout，log 出 `failed to create session: Permission denied` on `/home/app/.codex/sessions`
  - gemini token refresh 失敗：`Permission denied: '/home/app/.gemini/oauth_creds.json'`
  - **修法**：`entrypoint.sh` 以 root 啟動時加 `chmod -R u+w,g+w /home/app/.{claude,gemini,codex} 2>/dev/null || true`（已 commit 32d6d56）。診斷指令：`docker exec -u app ai-proxy sh -c 'echo x > /home/app/.codex/test 2>&1'`，若 `Permission denied` 就是中招。

## Provider（10 個）

| Provider | 類型 | CLI 命令 | 憑證位置 | Fallback model |
|----------|------|----------|----------|---------------|
| claude | CLI OAuth + API | `claude` | `~/.claude/.credentials.json` | `claude-haiku-4-5` |
| gemini | CLI OAuth + API | `gemini` | `~/.gemini/oauth_creds.json` | `gemini-2.5-flash` |
| openai | CLI OAuth（codex）| `codex` | `~/.codex/auth.json` | `gpt-4o-mini` |
| deepseek | API Key only | — | API Key 在 dashboard / env | `deepseek-chat` |
| mistral | API Key only | — | 同上 | — |
| groq | API Key only | — | 同上 | — |
| xai | API Key only | — | 同上 | — |
| together | API Key only | — | 同上 | — |
| fireworks | API Key only | — | 同上 | — |
| cohere | API Key only | — | 同上 | — |

> `openai.enabled: true` 是 fallback chain 必要條件；CLI-based 三家都關閉後仍能用 API-only provider（需要 API Key）。

## 客戶端連線方式（兩種情境）

**選對路徑比效能重要** — 走錯路徑可能讓同 NAS 的流量繞出去再繞回來，也可能讓外網連線誤用內網 IP 失敗。

### 情境 1：同 NAS 不同 container → 走 docker network 內網

客戶端跑在 NAS 上另一個 container（e.g. 新開的 web app 想呼叫 ai-proxy）。

**做法：加入同一個 docker network，用容器名連線**

```yaml
# 新 container 的 docker-compose.yml（關鍵片段）
services:
  my-app:
    networks:
      - deploy-nas_default   # 加入 ai-proxy 所在的 network
    environment:
      - PROXY_ADDR=ai-proxy:50051   # ⚠️ 用容器內部 port 50051，不是對外 8091

networks:
  deploy-nas_default:
    external: true           # 外部已存在的 network，不要重建
```

```python
# 客戶端（明碼 gRPC，不走 TLS）
import grpc
channel = grpc.insecure_channel("ai-proxy:50051")
meta = [("authorization", f"Bearer {TOKEN}")]
```

**優點：** 零延遲、不走 NPM、不耗 NAS 對外頻寬。
**替代（IP 直連）：** `grpc.insecure_channel("192.168.32.1:50051")` 可用但 IP 可能隨重啟變動，建議用容器名。

### 情境 1.5：REST 備援（debug 用，非生產推薦）

`POST https://clip.twloop.com/api/chat`（Bearer token）— HTTP/1.1，穿 NPM `proxy_pass` 沒有 gRPC 的 HTTP/2 frame 問題。

```bash
curl -X POST https://clip.twloop.com/api/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"prompt":"hi","project":"debug","group":"test"}'
# 回：{"ok":true,"content":"...","input_tokens":N,"output_tokens":N,"latency_ms":N}
```

**✅ Response shape（2026-04-19 修正後，跟 gRPC 一致）：** 包含 `ok / content / input_tokens / output_tokens / latency_ms / actual_provider / actual_model / tokens_estimated`。fallback 發生時 `actual_provider != provider`，用量記錄也會歸類到真實 provider（之前 `provider=request 值` 會讓 fallback 統計失真，已一併修正）。

**何時可以用：**
- gRPC 通道出問題時的臨時 escape hatch（例如 NPM `grpc_pass` 壞掉）
- 驗證「帳號 / token / provider 是否正常」的純 debug 流量
- 一次性 shell 測試、運維腳本

**何時絕對不要用：**
- 生產 client 不要把 REST 當主要路徑。用 gRPC + 情境 2 的正統做法，否則失去 fallback tracking。
- Anti-pattern：「gRPC 連不上就切換 REST」屬於**應用層繞過基礎設施問題**。正解是去 NPM admin 加 `grpc_pass`（詳見「常見問題 → 外網 gRPC 連不上」），5 分鐘修好，所有 client 一起受惠。

### 情境 2：外網客戶端（Tokyo VPS / 家外 / 他人電腦）→ 走 `cli.twloop.com:443`

客戶端無法進 NAS 內網，必須透過 Cloudflare → NAS NPM → ai-proxy。

**做法：連 `cli.twloop.com:443`（TLS 加密），NPM 端做 `grpc_pass` 轉發**

```python
# 客戶端（TLS gRPC）
import grpc
channel = grpc.secure_channel(
    "cli.twloop.com:443",
    grpc.ssl_channel_credentials(),  # 用系統 CA，Let's Encrypt 自動信任
)
meta = [("authorization", f"Bearer {TOKEN}")]
```

**前提：** NPM 的 `cli.twloop.com` 必須配 `grpc_pass`（不是 `proxy_pass`），詳見「常見問題 → 外網 gRPC 客戶端連不上 / RST_STREAM」。

### 決策表

| 問題 | 情境 1 | 情境 2 |
|------|--------|--------|
| 延遲 | < 1ms | 20-100ms（看外網）|
| 需要 TLS 憑證？ | 不需要（內網明碼）| 需要（`grpc.ssl_channel_credentials()`）|
| 連線字串 | `ai-proxy:50051` | `cli.twloop.com:443` |
| `insecure_channel` vs `secure_channel` | insecure | secure |
| NPM 參與？ | ❌ | ✅ |
| 容器必須加 network？ | ✅（`deploy-nas_default`）| ❌ |
| 失敗症狀 | DNS 解析失敗 / connection refused | RST_STREAM / `unexpected HTTP status` |

### ⚠️ 反模式（不要做）

- **同 NAS container 卻連 `cli.twloop.com:443`**：繞出去再繞回來，多 3 跳、吃頻寬、吃 NPM CPU。
- **外網客戶端卻連 `192.168.32.1:50051`**：連不到（私有 IP），會卡在 SYN 階段 timeout。
- **同 NAS 卻不加 network 直接用容器名**：Docker DNS 查不到，`Name or service not known`。

### gRPC 結構化錯誤（2026-05-03 起，trailing metadata）

server abort 前會 `set_trailing_metadata`，client 從 `RpcError.trailing_metadata()` 拿結構化 error。**舊 client 沒讀也不會壞**（從 `details()` 字串拿訊息），新 client 用 trailers 比 regex 解字串可靠。

| trailer key | 可能值 | 意義 |
|---|---|---|
| `x-pcli-error-code` | `bad_request` / `auth_invalid` / `quota_exhausted` / `provider_down` / `unknown` | 結構化錯誤分類 |
| `x-pcli-retryable` | `"1"` / `"0"` | client 是否該 retry |

```python
try:
    resp = await stub.Complete(req, metadata=md)
    if resp.error_code:
        # success-with-warning（如 fallback 成功），content 仍有效
        log_warning(resp.error_code, resp.error_message)
    return resp.content
except grpc.aio.AioRpcError as e:
    trailers = dict(e.trailing_metadata() or [])
    code = trailers.get("x-pcli-error-code", "unknown")
    retryable = trailers.get("x-pcli-retryable", "0") == "1"
    if retryable:
        await asyncio.sleep(10)
        # retry once
        ...
    raise ProxyError(code, e.details())
```

**為什麼不是 google.rpc.Status / Any error_details？** 那需要多裝 `grpcio-status`、client 解 Any，繁瑣。trailing metadata 是 gRPC 原生機制，server 2 行、client 1 行解決。

## Fallback 機制

請求不指定 `provider` 時（**推薦**）：
1. `usable_providers()` 偵測可用的 pool
2. `resolve_model_for_providers()` 依 tier/quality 挑最合適的
3. 失敗（auth_expired / cli_error / exhausted）→ fallback chain：
   - **優先 CLI pool**（有 codex 憑證就用，吃免費 OAuth 額度）
   - 再試 direct API（需 API Key）

Fallback chain（`claude` 失敗時依序嘗試）：
```
claude → openai(codex) → deepseek → groq → mistral → xai
       → together → fireworks → cohere → gemini
```

## API 端點速查

### 公開（不需 auth）

| 端點 | 用途 |
|------|------|
| `GET /healthz` | Liveness — process alive，永遠 200 |
| `GET /ready` | Readiness — 任一 provider 有 healthy slot 才 200，否則 503 |
| `GET /metrics` | Prometheus exposition format（slots、requests/tokens 24h、latency p50/p95/p99） |
| `GET /api/health` | 詳細 pool 狀態（原有，更完整） |
| `GET /api/usage?days=7` | 用量 + 延遲分位數 |
| `GET /api/recent?limit=20&offset=0&user=&provider=&status=` | 最近請求，支援搜尋/翻頁 |
| `GET /api/breakdown?by=user\|project\|provider\|model&days=7` | 分類統計 |
| `GET /api/routing-stats?days=7` | auto-route 決策分層統計（訓練資料） |
| `GET /api/claude-risk` | Claude ToS 風險卡片資料（今日 token / cap % / 紅綠燈 / 7 日趨勢） |
| `POST /api/chat` | REST 備援入口（Bearer token auth），回 `actual_provider/actual_model`（2026-04-19 修正） |
| `POST /api/chat/stream` | REST SSE streaming，`done` 事件含 `actual_provider/actual_model` |
| `POST /api/chat/tools` | REST function calling（含 `actual_provider/actual_model`） |

### Admin only（需要有 `name: admin` 的 HTTP token）

| 端點 | 用途 |
|------|------|
| `GET /api/backup` | 下載 `usage.db` 快照（VACUUM INTO 保證一致性） |
| `POST /api/restore` | 上傳 `.db` 還原（integrity_check + schema 驗證 + os.replace 原子 swap） |
| `GET /api/users.csv` | 匯出用戶列表（含 token）為 CSV |

> **⚠️ 安全建議：不要建 admin 用戶。**
> admin token 若洩漏 = 整個 SQLite 可被下載（所有用戶 token + 用量歷史）。
> 這些操作都能用 SSH + docker exec 從 NAS 內部完成，SSH 本身已有金鑰認證 +
> port 33333 + docker user 無 sudo 的多層防護，比 HTTP admin token 安全。
>
> **實務：**
> - `config.yaml` 的 `users: [{name: admin, token: ...}]` 只是**檔案種子**，
>   實際 auth 走 SQLite `users` 表。SQLite 沒有 `name='admin'` 這筆時，
>   HTTP admin 功能等同停用（想用的人拿到 Unauthenticated）。
> - 要做備份 / 還原 / CSV 匯出 → 用下方「SSH 版本」指令（不需 HTTP token）。
>
> **SSH 等效指令：**
> ```bash
> # 備份（= /api/backup）
> ssh nas "/usr/local/bin/docker exec ai-proxy sqlite3 /app/data/usage.db \
>   '.backup /tmp/bk.db' && cat /tmp/bk.db" > local-backup.db
>
> # 還原（= /api/restore）
> scp -O -P 33333 -i ~/.ssh/id_ed25519_nas backup.db \
>   docker@192.168.0.126:/volume1/docker/proxy-cli/data/usage.db.new
> ssh nas "/usr/local/bin/docker exec ai-proxy sh -c \
>   'mv /app/data/usage.db.new /app/data/usage.db'"
> ssh nas "/usr/local/bin/docker restart ai-proxy"
>
> # CSV 匯出（= /api/users.csv）
> ssh nas "/usr/local/bin/docker exec ai-proxy sqlite3 -header -csv \
>   /app/data/usage.db 'SELECT * FROM users'" > users.csv
> ```

## 新的請求參數

### `effort`（Claude thinking budget，v3.1.0 SDK）

```python
from proxy import ai
# 簡單分類，降延遲 + 省成本
ai("這段程式碼有 bug 嗎？", effort="low", project="work-A", group="review")

# 標準（預設）
ai("寫一個 Python 排序函式", project="work-A", group="code")

# 深度推理
ai("證明分散式鎖的安全性與活性", effort="high", project="work-A", group="analysis")
```

Server 端映射到 Claude API 的 `thinking.budget_tokens`：
- `low` = 1024 tokens
- `medium` = 8192 tokens
- `high` = 32768 tokens

> **重要**：effort 設定時會**跳過 CLI 直接走 direct API**（CLI 不支援 thinking）。
> 需要在 dashboard 設定 `CLAUDE_API_KEY` 或 `ANTHROPIC_API_KEY` 才會生效，否則失敗 fallback 到下一個 provider。

### `images` / `videos` / `youtube_urls`（多模態）

`/api/chat` 接受三種媒體欄位。Gemini CLI OAuth 模式可讀 image + PDF（用 `@file` 引用 workspace 內檔案），不用花 API key：

```python
# 讀圖（提供 provider=gemini 走最快免費路徑）
ai("what's in this image?", provider="gemini",
   images=[{"mime_type": "image/png", "data": b64}])

# 讀 PDF（Gemini CLI OAuth 也支援）
ai("摘要這份合約", provider="gemini",
   images=[{"mime_type": "application/pdf", "data": b64}])

# 讀影片 / 音訊（OAuth scope 不夠，要 Gemini API Key）
ai("描述這影片", provider="gemini", videos=[{"mime_type": "video/mp4", "data": b64}])
ai("把這段對話轉文字", provider="gemini", videos=[{"mime_type": "audio/mp3", "data": b64}])

# 讀 YouTube 連結（無大小上限）
ai("總結這支影片", provider="gemini", youtube_urls=["https://www.youtube.com/watch?v=xxx"])
```

| 能力 | Claude | Gemini | Codex (OpenAI) |
|------|--------|--------|----------------|
| 讀圖 | 🟡 Gemini API key 代打 | ✅ **CLI 優先（OAuth, 2.5s/5k tokens）** | ✅ CLI（-i flag, 6.8s/21k tokens）|
| 讀 PDF | 🟡 同上 | ✅ **CLI（OAuth, @file 引用）** | ❌ |
| 讀影片（≤20MB inline）| ❌ | ✅ Gemini API Key 路徑 | ❌ |
| 讀音訊（mp3/wav/m4a）| ❌ | ✅ 用 `videos` 欄位丟，mime 帶 `audio/*` | ❌ |
| 讀 YouTube | ❌ | ✅ `youtube_urls` 欄位 | ❌ |

#### 路由邏輯（`src/dashboard.py:_handle_chat`）

優先順序：**Gemini CLI > Codex CLI > Gemini API**（CLI 優先省 API key）

```python
media = images + videos
if media or youtube_urls:
    # 路徑 1a：gemini CLI + image/PDF（OAuth 免費，最快）
    if provider == "gemini" and images and not videos and not youtube_urls:
        cli_pool = self.pool.get_pool("gemini")
        → CLIProcess dump base64 → /home/app/.gemini/tmp/app/proxy-cli-img/
        → gemini -p "<prompt> @path1 @path2..." -m gemini-2.5-flash
        → 失敗回退路徑 2

    # 路徑 1b：codex CLI + 純圖片（subscription 免費）
    elif provider == "openai" and images and not videos and not youtube_urls and not openai_key:
        → pool.execute(..., images=images)
        → CLIProcess dump base64 → /tmp/cli-img-*.{ext} → codex exec -i path

    # 路徑 2：Gemini API Key 多模態（影片 / 音訊 / YouTube / fallback）
    if not cli_pool:
        if gemini_key and provider != "gemini":
            provider = "gemini"  # 自動切換
        → direct.execute_with_media(..., images=media, youtube_urls=youtube_urls)
```

`actual_source` 區分來源：
- `"cli"` = gemini CLI 或 codex CLI 讀（不燒 API token）
- `"api"` = Gemini multimodal API（燒 Gemini free tier / paid token）

#### 關鍵實作細節

- **Gemini CLI workspace 限制**：CLI sandbox 只允許讀 `/app` 或 `/home/app/.gemini/tmp/app/` 內的檔案。proxy-cli 寫到 `/home/app/.gemini/tmp/app/proxy-cli-img/` 然後用 `@/absolute/path` 引用
- **PDF mime 也用 `images` 欄位**：`{"mime_type": "application/pdf", "data": b64}`，不另開欄位
- **`videos` 欄位也吃音訊**：mime 帶 `audio/mp3` / `audio/wav` 等，Gemini API inlineData 統一處理
- **YouTube 走 fileData**：`{fileData: {fileUri, mimeType: "video/youtube"}}`，無大小上限

#### 限制

- **影片 inline ≤ 20MB**：Gemini `inlineData` 上限；長影片要走 Gemini Files API（未實作）
- **Gemini CLI OAuth 不吃 audio/video**：404 returned，這些走 API key
- **`/v1/chat/completions`（OpenAI compat）不吃 videos**：schema 不相容
- **codex CLI 讀圖吃大量 tokens**：~20k/張（gpt-5 視為 context），優先用 Gemini CLI

#### 驗證

```bash
# Gemini CLI 讀圖（最快免費路徑）
curl -X POST https://clip.twloop.com/api/chat \
  -H "Authorization: Bearer <user_token>" \
  -d '{"provider":"gemini","model":"gemini-2.5-flash",
       "prompt":"what color? 3 words",
       "images":[{"mime_type":"image/png","data":"<b64>"}],"project":"..."}'
# 應回 "actual_source":"cli", latency ~2.5s

# 確認路徑（log 訊息對 image / PDF 都通用）
ssh nas "/usr/local/bin/docker logs ai-proxy --tail 30 | grep -E 'gemini CLI 讀|codex CLI 讀'"
# 2026-04-23 10:14:28 [INFO] src.dashboard: gemini CLI 讀圖路徑（OAuth）：1 張圖片
```

### `/api/generate`（媒體生成）

完整 schema 在 `docs/api.md`。常用範例：

```bash
# 最簡單（Gemini 預設，1 張）
POST /api/generate {"prompt":"red apple","type":"image","project":"..."}

# 強制 codex CLI（OAuth 免費，gpt-image-2），16:9，4 張
POST /api/generate {"prompt":"city skyline","type":"image",
                    "provider":"openai","aspect_ratio":"16:9",
                    "style_hint":"realistic, cinematic","n":4,"project":"..."}

# Image-to-image / variation（必走 Gemini gemini-2.5-flash-image）
POST /api/generate {"prompt":"add sunglasses",
                    "type":"image",
                    "images":[{"mime_type":"image/png","data":"<base64>"}],
                    "project":"..."}

# Quality tier（fast 便宜快、best 高品質貴）
POST /api/generate {"prompt":"...","type":"image","quality":"fast","project":"..."}
POST /api/generate {"prompt":"...","type":"image","quality":"best","project":"..."}

# TTS / 影片 / 音樂（強制 Gemini API）
POST /api/generate {"prompt":"hello","type":"tts","project":"..."}
POST /api/generate {"prompt":"...","type":"video|music","project":"..."}
```

欄位（2026-05-02 + 2026-05-03）：

| 欄位 | 說明 |
|------|------|
| `provider` | image only：`openai` 強制 codex CLI；其他預設 Gemini API |
| `aspect_ratio` | `1:1`/`16:9`/`9:16`/`4:3`/`3:4`/`3:2`/`2:3`/`21:9`/`9:21`；image / video |
| `style_hint` | 任意風格描述，編進 prompt |
| `n` | 1-4，image only。proxy 並發 N 次，回 `items[]` 多張 |
| `quality` | image only：`fast`（強制 Gemini flash-image）/ `best`（偏好 codex gpt-image-2）|
| `images` | image only：image-to-image / variation。`[{mime_type, data(base64)}]`。**有此欄位強制走 Gemini gemini-2.5-flash-image**（codex `image_generation` tool 不支援 input image）|

#### 路由優先級（image type）

```
1. images 非空 → 強制 Gemini gemini-2.5-flash-image（image-to-image）
2. quality=fast → 強制 Gemini gemini-2.5-flash-image
3. quality=best 或 provider=openai → codex CLI（gpt-image-2）
4. 預設 → Gemini API
5. 沒 Gemini key 但 codex 可用 → fallback codex
6. codex 失敗有 Gemini key → 反向 fallback Gemini
```

| type | 預設來源 | 模型 | 需要 |
|------|---------|------|------|
| tts | Gemini API | `gemini-2.5-flash-preview-tts` | API key（OAuth scope 不夠）|
| **image** | **codex CLI（`provider=openai`）/ Gemini API（預設）** | `gpt-image-2` / `gemini-2.5-flash-image` | codex 用 OAuth 免費；Gemini 走 API key |
| video | Gemini API | `veo-3.0-generate-001` | API key（付費）|
| music | Gemini API | `lyria-3-clip-preview` | API key（受限）|

**TTS / 影片 / 音樂仍只能走 Gemini API Key**（OAuth scope 不夠）。
**生圖兩條路**：`provider=openai` 走 codex CLI（OAuth 免費，下節詳述）；預設或 `provider=gemini` 走 Gemini API。
TTS 預設聲音 `Zephyr`，可在 `direct.py:_generate_content_media` 改。

#### 失敗時的 error_code 列舉（2026-05-02 上線）

`/api/generate` / `/api/usage/media` 失敗 response：

```json
{
  "ok": false,
  "error": "人類可讀錯誤訊息",
  "error_code": "quota_exhausted",
  "actual_provider": "gemini",
  "retryable": true,
  "details": "原始 API body 前 300 字"
}
```

| `error_code` | 意義 | client 處置 |
|---|---|---|
| `bad_request` | 缺欄位 / 值錯（400）| 修 prompt/payload，**不要 retry** |
| `auth_invalid` | API key 沒設 / OAuth 過期（401/403/503）| 通知管理員，**不要 retry** |
| `not_found` | resource 不存在（如 job_id 不在 / 不屬於你，404，2026-05-03）| **不要 retry**，輸入錯 ID 或別人的 |
| `quota_exhausted` | 配額用完（429/502）| 可換 `provider` retry 或等 1 hr |
| `content_policy` | 被 safety filter 擋（502）| **不要 retry 同 prompt**，要改 prompt |
| `provider_down` | 5xx / timeout（502）| 同 provider retry。**async path proxy 已自動 retry 1 次**（3s 延遲）|
| `unknown` | 沒分類到 | 看 `details`，謹慎 retry |

n>1 部分成功時 200 OK，多帶 `partial_errors[]` 陣列。

範例：要 4 張、3 張成功 1 張被 safety 擋：
```json
{
  "ok": true,
  "n_requested": 4,
  "n_succeeded": 3,
  "items": [<3 個 base64 PNG>],
  "partial_errors": [
    {"error_code": "content_policy", "error_msg": "blocked by safety filter"}
  ]
}
```

client 端建議處理：
```js
if (r.n_succeeded < r.n_requested) {
  showWarning(`${r.n_succeeded}/${r.n_requested} 張生成成功`);
  // partial_errors 拿 error_code 顯示為什麼缺
  const codes = (r.partial_errors || []).map(e => e.error_code);
  if (codes.includes("content_policy")) hintRewordPrompt();
  else if (codes.includes("quota_exhausted")) hintTryLater();
}
// 不需要 retry — proxy 已經並發跑 N 次，partial 失敗是各自獨立原因
```

#### Async 媒體生成（2026-05-03 上線）

`POST /api/generate/async` 立即回 `job_id`，背景跑；client `GET /api/jobs/{id}` 輪詢。
適用 video（分鐘級）+ 大張 image batch（n=4 codex 也會卡 30s+）。

```bash
# 1. 提交
POST /api/generate/async {"prompt":"...","type":"video","project":"..."}
# → {"ok":true,"job_id":"<uuid>","status":"queued","poll_url":"/api/jobs/<uuid>"}

# 2. 輪詢
GET /api/jobs/<uuid>
# 進行中：{"ok":true,"status":"running",...}
# 完成：  {"ok":true,"status":"succeeded","result":{<完整 /api/generate body>}}
# 失敗：  {"ok":true,"status":"failed","error_code":"...","error_msg":"..."}

# 3. 列表（自己的 job）
GET /api/jobs?limit=20&status=succeeded
```

**狀態機**：

| 狀態 | 意義 |
|---|---|
| `queued` | 還沒 start。proxy 重啟也保留，啟動時自動重生 worker 接續跑 |
| `running` | 執行中 |
| `succeeded` | 完成，result 是完整 `/api/generate` body |
| `failed` | 失敗，`error_code` / `error_msg` 在頂層 |
| `lost` | **執行中**撞 proxy 重啟 → 無法安全 resume；client 重送 |

**proxy 自動 retry**：worker 內 `provider_down` 自動 retry 1 次（3s 延遲），其他 error_code 立刻 fail。client 不用自己重送 transient 5xx。

**安全注意**：`GET /api/jobs/{id}` 只能查自己的 job；別人的或不存在都回 `404 + error_code: not_found`（不洩漏存在性）。

**client 範例**（JS）：
```js
const r = await fetch("/api/generate/async", {method: "POST", headers, body}).then(r => r.json());
const jobId = r.job_id;
while (true) {
  await new Promise(r => setTimeout(r, 4000));
  const j = await fetch(`/api/jobs/${jobId}`, {headers}).then(r => r.json());
  if (j.status === "succeeded") return j.result;
  if (j.status === "failed" || j.status === "lost") throw new Error(`${j.error_code}: ${j.error_msg}`);
}
```

#### `/api/usage/media` — 媒體用量查詢

```bash
GET /api/usage/media?type=image&days=1
# 回傳 {"providers": [{provider, model, requests, input_tokens, output_tokens, avg_latency_ms}, ...]}
```

可拿來顯示「今日 codex 已用 X 張、Gemini 已用 Y 張」。free tier 上限 proxy 不 enforce，client 自行對照。

#### Codex CLI 生圖（OAuth 免費路徑，2026-05-02 驗證）

`codex` CLI **v0.123+ 內建 `image_generation` tool**（模型 `gpt-image-2`），用 ChatGPT 訂閱 OAuth 直接呼叫，**不需 OpenAI API Key**：

```bash
# 直接用 codex exec 生圖（容器內或本地 Mac 都可，需 codex login）
codex exec -C "$(pwd)" -s workspace-write --skip-git-repo-check \
  "用 image generation tool 生成紅蘋果在白底，存成 ./apple.png"
```

關鍵細節：
- **吃 Codex CLI usage limits**（不是 ChatGPT 對話池），burn rate 是普通對話的 **3-5×**
- 原圖預設 `~1254×1254`，落 `~/.codex/generated_images/<session-id>/<hash>.png`，需自己 cp + sips 縮放
- 跟 Gemini API 路徑互補：codex 燒 ChatGPT 訂閱、Gemini 燒 API key 配額

**proxy-cli 路由現況（2026-05-02 上線）**：
- `/api/generate type=image` 路由：
  - `provider=openai` → **codex CLI（OAuth 免費，gpt-image-2）**
  - 預設 / `provider=gemini` → Gemini API（imagen / nano-banana）
  - 沒 Gemini API key 時自動 fallback 到 codex CLI
  - codex 失敗有 Gemini key 才 fallback Gemini API
- 實作位於 `pool.py:ProcessPool.generate_image_via_codex()`：codex 跑 read-only sandbox（NAS DSM kernel 不支援 bwrap，所以**不依賴 codex shell tool**），直接從 `~/.codex/generated_images/<thread_id>/*.png` 讀檔回傳
- 實測：~25-30s/張、~25k input + ~30 output tokens、回傳 1254×1254 PNG
- 用法：
  ```bash
  curl -X POST https://clip.twloop.com/api/generate \
    -H "Authorization: Bearer <token>" \
    -d '{"prompt":"red apple","type":"image","provider":"openai","project":"..."}'
  # 回傳 actual_source="cli", actual_provider="openai"
  ```

驗證：
```bash
# 本地測試
codex --version  # 需 ≥0.123（Mac brew 升 npm install -g @openai/codex@latest）
mkdir -p /tmp/codex-img && cd /tmp/codex-img && \
codex exec -C "$(pwd)" -s workspace-write --skip-git-repo-check \
  "用 image generation tool 生成藍色蝴蝶，存成 ./b.png"
ls -la /tmp/codex-img/b.png
```

### Web search / URL fetch（CLI 自動觸發）

**不需任何欄位** — 3 家 CLI 在非互動模式都會 LLM 自決呼叫工具。

```python
# 直接把 URL 塞 prompt
ai("總結 https://en.wikipedia.org/wiki/Helium 1 句話", provider="gemini")
# Gemini CLI 自動呼叫 url_context / google_search

ai("who won FIFA 2022?", provider="claude")
# Claude --print 自動 web search

ai("latest gpt model", provider="openai")
# Codex exec 自動 web tool
```

只有 codex CLI 會回 `actual_source:"cli"`，其他則照原 source 標記。

### 智能路由（`routing.auto`）

`config.yaml` 中 `routing.auto: true` 開啟後，**client 沒指定 `model` 也沒指定 `tier`** 時，
server 依 prompt 自動分類：

| 訊號 | 分流 |
|------|------|
| 簡單關鍵字（yes/no、classify、是否）| `basic` → Haiku |
| 複雜關鍵字（step by step、推理、證明）| `best` → Opus |
| System prompt > 2000 字（agent 場景）| `best` |
| 含 ≥2 個程式碼區塊 | `good` → Sonnet |
| 總長度 < 200 | `basic` |
| 總長度 > 4000 | `best` |
| 其他 | `good` |

每次決策會寫入 `routing_decisions` 表，供未來 ML router 訓練用（`/api/routing-stats` 可查分層成效）。

## 觀測 / Prometheus

```bash
# 直接拉 metrics
ssh nas "curl -s http://localhost:8091/metrics"
```

輸出範例：
```
proxy_slots_healthy{provider="claude"} 3
proxy_slots_total{provider="claude"} 3
proxy_pool_idle{provider="claude"} 4
proxy_requests_total_24h 156
proxy_tokens_total_24h 98234
proxy_request_latency_ms{quantile="0.5"} 11090.0
proxy_request_latency_ms{quantile="0.95"} 51197.0
proxy_request_latency_ms{quantile="0.99"} 78000.0
```

Grafana 接法：Prometheus 設 scrape target `proxy-cli:8080/metrics`，或經 Nginx 反代 `clip.twloop.com/metrics`。

## 備份 / 還原

### Dashboard UI
開 clip.twloop.com → 左側「系統」→「資料庫備份」→ 下載 / 還原 按鈕
（首次會要 admin token）

### 命令列
```bash
# 備份（下載成 .db 檔）
curl -sL -o backup.db -H "Authorization: Bearer $ADMIN_TOKEN" \
    https://clip.twloop.com/api/backup

# 還原
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     -F "file=@backup.db" \
     https://clip.twloop.com/api/restore
```

還原流程：上傳 → 暫存檔 → `PRAGMA integrity_check` + schema 驗證 → 關閉現有連線 → `os.replace` 原子 swap → 重新 init。失敗會保留原 DB。

## 常見問題

> 完整 11 個情境見 `references/troubleshooting.md`。下面只列最常碰到的 3 個。

### `/ready` 回 503
- 表示無 healthy slot。查 `GET /api/health` 看每個 provider 的 `healthy_slots` 和 `auth_ok`
- 多半是 Claude token 過期 → 跑下面的重新登入流程

### Claude token 過期 → 重新登入

**Dashboard 路徑（推薦）**：開 `https://clip.twloop.com` → 側邊欄「登入 Claude」按鈕 → 瀏覽器 OAuth flow，新 token 覆蓋 slot-0。

**容器內 CLI 路徑（dashboard 失效時）**：
```bash
ssh -t nas "/usr/local/bin/docker exec -it ai-proxy su app -c 'claude /login'"
ssh nas "/usr/local/bin/docker restart ai-proxy"
```

**自動同步**（Mac 端 cron）：本機 `~/.local/bin/sync-claude-token-to-nas.sh` 每小時檢查 Mac Keychain，必要時 push 到 NAS + restart。詳見「自動同步 Claude token」段。

### 🔴 外網 gRPC 連不上 / RST_STREAM
**根因**：NPM 用 `proxy_pass` 不能跑 gRPC。要在 NPM `cli.twloop.com` Custom Nginx 寫 `grpc_pass grpc://192.168.32.1:50051`。詳見 `references/troubleshooting.md`。

**驗證**：`grpcurl -d '{}' cli.twloop.com:443 aiproxy.AIProxy/HealthCheck` 回 JSON 即通。

### 其他情境（去 references/troubleshooting.md）
- `Claude CLI 進入 stdin 互動模式`
- 外網 `HealthCheck` 通但 `Complete` hang（PMTU 黑洞 / Bun 版本）
- codex 180s timeout / gemini refresh 失敗（DSM ACL read-only）
- hotfix `docker cp` 後 crashloop（host perms 600 帶進去）
- 工程師回報「claude 過期沒 fallback」/「group 欄位空」
- `actual_source` 欄位語意
- TLS 憑證快到期 / Slot quarantine / Daily cap

## 讀取實際 provider / model

`CompletionResponse` / REST `/api/chat` 都有：
- `actual_provider`：fallback 觸發後實際的 provider
- `actual_model`：實際模型 ID
- `actual_source`：`"cli"` | `"api"` | `"cache"`

**完整 SDK 範例**（Python `use_proxycli`、Node.js / TS、直連 gRPC）見 `references/client-examples.md`。

## 部署流程

### 快速部署（改程式碼）
```bash
cd /Users/macpro-david/Library/CloudStorage/Dropbox/84-WebCode/01-mac/1-info/proxy-cli

rsync -avz --rsync-path=/usr/bin/rsync \
  --exclude='.env' --exclude='__pycache__' --exclude='.git' \
  --exclude='*.pyc' --exclude='.DS_Store' --exclude='data/' --exclude='creds/' \
  --exclude='certs/' --exclude='*.log' --exclude='*.csv' \
  --exclude='.venv/' --exclude='.pytest_cache/' --exclude='.gstack/' \
  --exclude='.claude/' --exclude='deploy-aapanel/' \
  -e "ssh -p 33333 -i ~/.ssh/id_ed25519_nas -o StrictHostKeyChecking=no" \
  ./ docker@192.168.0.126:/volume1/docker/proxy-cli/ && \
ssh nas "cd /volume1/docker/proxy-cli && /usr/local/bin/docker compose -f deploy-nas/docker-compose.yml up -d --build"
```

⚠️ **必須用 `-f deploy-nas/docker-compose.yml`** — 專案根目錄的 `docker-compose.yml` 是 Mac 開發用（含 `cpus` 限制），NAS kernel 不支援 CPU CFS 會啟動失敗。

### 只更新 config.yaml（不重建）
```bash
scp -O -P 33333 -i ~/.ssh/id_ed25519_nas config.yaml docker@192.168.0.126:/volume1/docker/proxy-cli/config.yaml
ssh nas "/usr/local/bin/docker restart ai-proxy"
```

### 部署後驗證 checklist
```bash
# 1. 容器啟動
ssh nas "/usr/local/bin/docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep proxy"

# 2. Liveness + Readiness
ssh nas "curl -s http://localhost:8091/healthz && echo && curl -s http://localhost:8091/ready"

# 3. Provider 狀態
ssh nas "curl -s http://localhost:8091/api/health | python3 -c \"import json,sys; d=json.load(sys.stdin); print({k:v.get('healthy_slots',0) for k,v in d.items() if isinstance(v,dict) and 'healthy_slots' in v})\""

# 4. Metrics
ssh nas "curl -s http://localhost:8091/metrics | head -20"

# 5. Log（找 error / TLS warning）
ssh nas "/usr/local/bin/docker logs ai-proxy --tail 30 2>&1 | grep -iE 'tls|error|warn|ready'"

# 6. 資源消耗
ssh nas "/usr/local/bin/docker stats --no-stream ai-proxy --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'"

# 7. 🔴 外網 gRPC 實際連線（2026-04-19 新增 — 容易漏掉的驗收點）
# 從 Mac 本機（不是 NAS）測試：若 NPM 沒配 grpc_pass 會拿到 RST_STREAM
grpcurl -d '{}' cli.twloop.com:443 aiproxy.AIProxy/HealthCheck
# 預期：回傳 JSON；若錯誤 → 去 NPM UI 修 cli.twloop.com custom location 加 grpc_pass
# 詳見「常見問題 → 外網 gRPC 客戶端連不上 / RST_STREAM」
```

## 憑證管理

> **⚠️ 關鍵：必須用 `app` user 登入，不能用 root**
>
> 容器內服務以 `app` user 執行，憑證必須寫到 `/home/app/.claude/`。
> 用 root 登入會寫到 `/root/.claude/`，服務讀不到。

### 新增 / 重新登入憑證
```bash
# Claude
ssh -t nas "/usr/local/bin/docker exec -it ai-proxy su app -c 'claude /login'"

# Codex (OpenAI)
ssh -t nas "/usr/local/bin/docker exec -it ai-proxy su app -c 'codex login'"

# Gemini
ssh -t nas "/usr/local/bin/docker exec -it ai-proxy su app -c 'gemini auth login'"
```

### 確認憑證路徑
```bash
ssh nas "/usr/local/bin/docker exec ai-proxy ls -la /home/app/.claude/.credentials.json /home/app/.gemini/oauth_creds.json /home/app/.codex/auth.json"
```

### Slots（**多帳號輪替已於 2026-04-19 停用**）

⚠️ **ToS 合規**：本系統**只支援 slot-0 單帳號**。

- `~/.claude/slots/slot-N/` 下的憑證會被 load_slots 忽略，只會 log warning
- Dashboard 新增 slot API 回 403，UI 會隱藏「新增帳號」按鈕
- OAuth web flow 新帳號覆蓋 slot-0（相同 refresh_token 也更新 slot-0）
- SQLite restore 只還原 `slot_id=0`，其他 slot 跳過並 log

**遺留檔案清理**（從 aapanel 搬到 NAS 時可能有殘留 slot-1/slot-2）：
```bash
# docker 帳號無 rm 權限，需用 admin SSH 登入
ssh -p 33333 admin@192.168.0.126 "sudo rm -rf /volume1/docker/proxy-cli/creds/claude/slots /volume1/docker/proxy-cli/creds/gemini/slots"
```

### 從本機推送憑證（dashboard 無法互動式登入時）

**前置：** ssh-key 到 NAS（`ssh-copy-id -p 33333 admin@192.168.0.126`），並在 `~/.ssh/config` 加 alias：
```
Host nas
  HostName 192.168.0.126
  Port 33333
  User docker            # docker 帳號能寫 /volume1/docker/proxy-cli/creds/*（因 DSM ACL 開放 1000:1000）
  IdentityFile ~/.ssh/id_ed25519_nas
Host nas-admin           # sudo 操作用這個
  HostName 192.168.0.126
  Port 33333
  User admin
  IdentityFile ~/.ssh/id_ed25519_nas
```

**Claude（macOS）：** 憑證在 Keychain，不在檔案系統。直接 pipe 上 NAS：
```bash
security find-generic-password -s "Claude Code-credentials" -w | \
  ssh nas "cat > /volume1/docker/proxy-cli/creds/claude/.credentials.json"
```

**Claude（Linux）：** 走檔案路徑：
```bash
scp -O ~/.claude/.credentials.json nas:/volume1/docker/proxy-cli/creds/claude/.credentials.json
```

**Gemini：** 需要 3 個檔案：
```bash
scp -O ~/.gemini/oauth_creds.json ~/.gemini/google_accounts.json ~/.gemini/settings.json \
  nas:/volume1/docker/proxy-cli/creds/gemini/
```

**Codex：** 只要一個：
```bash
scp -O ~/.codex/auth.json nas:/volume1/docker/proxy-cli/creds/codex/auth.json
```

**重啟 + 驗證：**
```bash
ssh nas "/usr/local/bin/docker restart ai-proxy"
sleep 10
curl -s http://192.168.0.126:8091/api/creds | python3 -c "
import json,sys
d=json.load(sys.stdin)
for p in ['claude','gemini','openai']:
    v=d[p]; print(f'{p}: valid={v[\"valid\"]} healthy={v[\"healthy_slots\"]}/{v[\"total_slots\"]}')
"
```
預期 3 個都 `valid=True healthy=1/1`。

**⚠️ 推完憑證後務必端到端測一次**（只看 `/api/creds` 綠燈會漏掉 DSM ACL read-only 坑）：
```bash
TOKEN=<任一 user token>
for P in claude gemini openai; do
  case $P in claude) M=haiku;; gemini) M=gemini-2.5-flash;; openai) M=gpt-4o-mini;; esac
  curl -sS -X POST http://192.168.0.126:8091/api/chat \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"provider\":\"$P\",\"model\":\"$M\",\"prompt\":\"Say PONG\",\"max_tokens\":128,\"project\":\"_activation\"}" \
    --max-time 120
  echo
done
```
openai 卡 180s timeout → 看「codex 每次 180s timeout」那節。

### 🤖 自動同步 Claude token（Mac Keychain → NAS cron，2026-04-23 新增）

**問題**：Claude OAuth access token 8h TTL，Mac Keychain 定時 refresh；NAS 容器裡的 token 會過期且無法自動 refresh（headless CLI 沒瀏覽器，refresh flow 不穩）。

**解法**：Mac cron 每小時檢查，必要時才從 Keychain 推新 token 到 NAS 容器 + restart。

**安裝位置**：`~/.local/bin/sync-claude-token-to-nas.sh`

**邏輯**：
1. 讀 Mac Keychain `Claude Code-credentials` 的 `expiresAt`
2. 讀容器 `/home/app/.claude/.credentials.json` 的 `expiresAt`
3. 只在兩者都滿足才推 + restart：
   - 容器 token 剩 <2h
   - Mac token 比容器的新
4. 否則 SKIP（降低 restart 頻率 ~6-8h 一次）

**cron**：`0 * * * *` + script 內 `sleep $((RANDOM % 3600))` 抖動避規律

**Keychain ACL 坑**：第一次 cron 跑會跳「允許 /usr/bin/security 存取」視窗；要預先在鑰匙圈存取手動「一律允許」，否則 cron 拿不到 token（log 會寫 `Keychain 沒撈到`）。

**觀察**：
```bash
tail -f /tmp/sync-claude-token.log
# 正常多數是 SKIP，每 6-8h 看到一次 PUSH + RESTART
```

**坑（2026-04-23 踩過）**：
- **絕對不要用 `docker cp /dev/stdin`** 寫容器檔案！會變成 symlink `target -> /proc/self/fd/0`，後續 `cat > target` 寫到自己的 stdin。
  - 正確做法：`cat file | ssh nas "/usr/local/bin/docker exec -i container sh -c 'cat > /path'"`
- **Pool slot 狀態卡住**：token 推了但 ProcessPool 記得「上次 failed」還是回 `claude 憑證已過期`。必須 `docker restart` 重建 pool 才會重試新 token。

## config.yaml 完整範本

完整模板見 `references/config-yaml.md`。最常需要改的：
- `users[]`：加用戶 + token（`name: admin` 觸發 HTTP admin 端點，**不建議使用**）
- `projects[]`：加專案
- `providers.*.enabled`：開關 provider
- `pool.race_mode`：單 slot 政策下無意義，保留 false
- `routing.auto`：true = 自動依 prompt 分類選 tier

## Dashboard UI 指引

左側邊欄（clip.twloop.com）：

| 區塊 | 功能 |
|------|------|
| **Claude 風險監控**（2026-04-19 新增） | 今日 token 累積 / 300k cap % + 🟢🟡🔴 紅綠燈 + 連續 3 日 > 200k 警告 banner（30s 刷新）|
| 認證管理 | OAuth 登入按鈕 / 手動上傳憑證（⚠️ 多 slot 功能已停用，新增按鈕已隱藏） |
| 專案 | 切換專案 scope，新增/刪除專案 |
| 系統 | 健康探測 + **資料庫備份**（需建立 admin 用戶才能用；推薦走 SSH 等效指令避免 HTTP token 洩漏風險） |
| 用戶 | 列表 + 新增 + **匯出 CSV（admin）** |
| API Key | 各 provider 的 API Key 設定 + 輪替策略（含 `ANTHROPIC_API_KEY`，啟用後 Claude direct API 走合規付費路徑）|
| 配額 | 用戶/專案級 daily token/request 上限（加上 provider-level cap，預設 claude 300k/day）|
| 模型 | 啟用/停用、per-project 指定 model、刷新 registry |

主內容區：
- 最近請求表支援**搜尋**（user/provider/status）+ **翻頁**（上/下頁按鈕）
- 用量 breakdown：按用戶 / 專案 / 小組 / 模型 / provider / 來源（CLI/API/cache）
- 延遲：avg + p50/p95/p99（來自 `/api/usage`）

## 工具鏈版本

- use_proxycli SDK：`v3.1.0`（`effort` 參數、`group` 必填）
- proto：含 `effort` field
- Dashboard：含備份/還原、搜尋/翻頁、CSV 匯出、智能路由統計
- Python：3.11-slim
- 核心依賴：`aiohttp 3.11`、`aiosqlite 0.20`、`grpcio 1.80`、`tiktoken 0.8`

## 查 log（常用 grep）

```bash
# 全部最新
ssh nas "/usr/local/bin/docker logs ai-proxy --tail 100"

# fallback / error / 授權 / slot 事件
ssh nas "/usr/local/bin/docker logs ai-proxy --tail 200 2>&1 | grep -iE 'fallback|error|warn|授權|slot'"

# auto-route 決策
ssh nas "/usr/local/bin/docker logs ai-proxy --tail 200 2>&1 | grep 'auto-route'"

# TLS 到期
ssh nas "/usr/local/bin/docker logs ai-proxy 2>&1 | grep -iE 'tls|憑證'"

# 最近 30 分鐘
ssh nas "/usr/local/bin/docker logs ai-proxy --since 30m"

# ToS 合規訊號（2026-04-19 新增）— 驗證部署後沒有 regression
# 應該沒有任何輸出
ssh nas "/usr/local/bin/docker logs ai-proxy 2>&1 | grep -iE '健康探測|patch_claude_creds|rateLimitTier'"

# Quarantine 事件（帳號風控訊號命中）
ssh nas "/usr/local/bin/docker logs ai-proxy 2>&1 | grep -iE '被永久隔離|quarantine|account_quarantine'"

# Daily cap 觸發
ssh nas "/usr/local/bin/docker logs ai-proxy 2>&1 | grep -iE 'daily_cap|今日 Token 已達上限|provider.*quota 查詢失敗'"

# 遺留 slot 清理提醒
ssh nas "/usr/local/bin/docker logs ai-proxy 2>&1 | grep -iE '遺留.*slot|ToS 政策忽略'"
```

## 自我更新規則（skill 維護）

**任何人使用此 skill 完成以下操作後，必須立即更新此檔案：**

1. **新增 provider** → 更新「Provider」表格
2. **移除或停用既有行為** → 在對應章節標註「已於 YYYY-MM-DD 刪除 / 停用」並留原因
3. **修改部署方式** → 更新「部署流程」章節
4. **新增 API endpoint** → 更新「API 端點速查」表格
5. **發現新的 ToS 紅旗行為** → 加到頂端「ToS 灰區」禁止清單
6. **Anthropic / Google 新增 telemetry / 錯誤訊息** → 更新 `_is_quarantine_error` keyword 清單

更新方式：直接用 Write 或 Edit 工具修改此檔案 `/Users/macpro-david/.claude/skills/hdw-proxycli/SKILL.md`
