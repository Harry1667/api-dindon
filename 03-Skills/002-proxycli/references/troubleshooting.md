# Troubleshooting — proxy-cli 完整排錯手冊

主檔 SKILL.md 只放最常見 3 個。這份是完整版（11 個情境），遇到比較少見的故障時 Read 進來。

### `Claude CLI 進入 stdin 互動模式`
- 原因：Claude CLI 認為需要互動式輸入（通常 auth 失效或版本問題）
- 錯誤類型 `cli_error`，會觸發 fallback chain
- **確認**：`config.yaml` 中 `openai.enabled: true`，fallback 會自動試 codex

> **⚠️ 陷阱 1**：`codex exec` 正常輸出也會有 `Reading additional input from stdin...`，
> 這**不是錯誤**。`_is_stdin_prompt_notice` 已限定只對 `provider == "claude"` 生效。
> 若日後改 stdin 偵測邏輯，務必保持此 provider 判斷。

> **⚠️ 陷阱 2**：`_parse_codex_output` 解析 JSON Lines：
> - 內容來自 `item.completed` 事件的 `item.text`（`type == "agent_message"`）
> - token 數來自 `turn.completed` 事件的**頂層** `usage`，不在 `turn` 裡面
> - codex 版本更新輸出格式時需同步更新

> **⚠️ 陷阱 3**：`/api/health` 的 `available: true` ≠ auth 有效。
> pool 初始化後 available 為 true，但憑證過期時實際請求仍 401。
> 確認 auth 真的可用：`echo test | claude --print`

### `/ready` 回 503
- 表示無 healthy slot（所有 provider 憑證都失效或 disabled）
- 查 `GET /api/health` 看每個 provider 的 `healthy_slots` 和 `auth_ok`
- 多半是 Claude token 過期 → 跑下面的重新登入流程

### Claude token 過期 → 重新登入

> **處理方式**：
> - `creds_incomplete` 錯誤 → 直接降級為 `auth_expired`
> - Dashboard 顯示「憑證欄位缺失，請重登」紅燈
> - 使用者走 OAuth web flow（`clip.twloop.com` 側邊欄「登入 Claude」按鈕），新 token 覆蓋 slot-0
>
> ToS 合規規則見頂部「Claude CLI Provider — ToS 灰區」章節。

**重新登入流程（容器內互動式，需終端機）**：
```bash
# 方法 1：Dashboard（推薦，最簡單）
# 開 https://clip.twloop.com → 側邊欄「登入 Claude」按鈕 → 瀏覽器 OAuth flow

# 方法 2：容器內 CLI 登入（方法 1 失效時）
ssh -t nas "/usr/local/bin/docker exec -it ai-proxy su app -c 'claude /login'"
# 完成後：
ssh nas "/usr/local/bin/docker restart ai-proxy"
```

**驗證新 token 可用**：
```bash
ssh nas "/usr/local/bin/docker exec ai-proxy bash -c 'HOME=/home/app claude --print --output-format json --model claude-haiku-4-5 \"hi\" 2>&1 | python3 -c \"import json,sys; print(json.load(sys.stdin).get(\\\"result\\\",\\\"\\\")[:60])\"'"
```

### 🔴 外網 gRPC 客戶端連不上 / RST_STREAM（NPM 需 grpc_pass，不是 proxy_pass）

**症狀：**
- 外網 gRPC 客戶端（e.g. Tokyo VPS 上的 agent-social）打 `cli.twloop.com:443` 收到 `RST_STREAM` / `INTERNAL_ERROR`
- 內網直連 `192.168.0.126:50051` 正常
- Dashboard（`clip.twloop.com`）HTTP 路徑也正常

**原因：**
NPM 預設用 `proxy_pass`（HTTP/1.1 & HTTP/2 一般 request），gRPC frame 會被當普通 HTTP/2 訊息處理 → 後端拒絕 → RST_STREAM。

**修法（NPM Admin UI，推薦）：**

1. 開 http://192.168.0.126:9081 （admin 帳號密碼登入）
2. Hosts → Proxy Hosts → 找到 `cli.twloop.com` → Edit
3. **Custom locations** tab → 新增一個 location 或改既有的：
   - Location: `/`
   - Scheme: **不要選 http/https，這裡要手刻**（NPM UI 沒有 grpc scheme 選項）
4. 切到 **Advanced** tab → **Custom Nginx Configuration** 貼入：

   ```nginx
   # gRPC 反代（HTTP/2 + gRPC frame 正確處理）
   location / {
       grpc_pass grpc://192.168.32.1:50051;   # 容器內網 IP，見下方註記
       grpc_read_timeout 300s;
       grpc_send_timeout 300s;
       error_page 502 = /error502grpc;
   }

   location = /error502grpc {
       internal;
       default_type application/grpc;
       add_header grpc-status 14;
       add_header content-length 0;
       return 204;
   }
   ```
5. **SSL** tab → 確認已發 Let's Encrypt 憑證、勾 **Force SSL**、勾 **HTTP/2 Support**
6. Save → NPM 會自動 reload nginx

**⚠️ 重要：`grpc://` 不是 `grpcs://`**
專案 `config.yaml` 的 `tls_enabled: false`，gRPC 伺服器明碼跑（NPM 端做 TLS 終止 + 明碼轉發給容器）。如果寫 `grpcs://` 會 handshake 失敗。

**Backend IP（`192.168.32.1`）怎麼確認：**
```bash
# 從 docker log 看容器訪問來源 IP（NPM 容器發出的）
ssh nas "/usr/local/bin/docker logs ai-proxy --tail 20 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | sort -u"
# 或查 docker 網路
ssh nas "/usr/local/bin/docker network inspect bridge | grep -A2 ai-proxy"
```
DSM 的 docker bridge 網段通常是 `192.168.32.0/20`，ai-proxy 容器常拿到 `192.168.32.X`。若 NPM 跟 ai-proxy 在**同一個 compose network**（`deploy-nas_default`）則可直接用 `ai-proxy:8080` 但 gRPC port 是 50051 不是 8080，且 NPM 容器不一定連到該網路 → 保險用 host network IP `192.168.32.1:50051`（host 側 port mapping）。

**驗證（本機 Mac）：**
```bash
# 用 grpcurl 測試外網 gRPC 連線
grpcurl -d '{}' cli.twloop.com:443 aiproxy.AIProxy/HealthCheck
# 預期：回傳 healthy 狀態 JSON
# 若回 RST_STREAM 或 "unexpected HTTP status code" → NPM 還沒生效
```

**為什麼 clip.twloop.com（HTTP dashboard）沒事？**
因為它是一般 HTTP/HTTPS，NPM 的 `proxy_pass` 處理得了。gRPC 才需要特殊 handling。

### 🔴 外網 `HealthCheck` 通但 `Complete` hang（多向量診斷法，2026-04-19 踩過）

**症狀：** 工程師從 Tokyo VPS 報 Bun + `@grpc/grpc-js`：
- HealthCheck ~200ms OK
- Complete 60s deadline exceeded，container log 沒有任何 Complete 進來的痕跡
- 同 token 同 VPS REST `/api/chat` 4s 正常

**第一反應 ≠ root cause**：不要急著改 NPM `grpc_pass` 配置或改 server trailer handling。大概率是 **client vantage 特有問題**（網路路徑、client lib 版本、MTU），不是 server 或 NPM bug。

**三向量測試**（用來切分責任）：

| 向量 | 指令 | 解讀 |
|---|---|---|
| A) 容器內 localhost | `docker exec ai-proxy python3 -c "...stub.Complete(...)"` | 通 → backend 沒問題 |
| B) Mac 外網 grpcurl | `grpcurl -d '{...}' -H "authorization: Bearer $T" cli.twloop.com:443 aiproxy.AIProxy/Complete` | 通 → NPM 沒問題 |
| C) 工程師 VPS grpcurl | 同上在他那台機跑 | 若這個也 hang → 100% 是他端網路 / MTU |

**A 和 B 都通 = NPM/backend 清白**，責任推回 client 端。

**client 端 checklist（給工程師）：**

1. **PMTU 黑洞**（Lightsail ↔ 台灣 IP 常見）：路徑中某跳 drop ICMP，大 DATA frame silent drop。小 response (HealthCheck) 通、大 response (Complete ~500 bytes 含 headers+trailers) 死。
   ```bash
   sudo ip route change default via <GW> dev <IF> advmss 1200
   # 或 sysctl net.ipv4.tcp_mtu_probing=1
   ```

2. **`@grpc/grpc-js` / Bun 版本**：我方驗證 Bun 1.3.11 + `@grpc/grpc-js` 1.10+ 都通。升最新試。

3. **Proto 同步**：對 MD5。v3.1 之後 `CompletionResponse` 新增 `actual_provider`/`actual_model` 兩欄。不同步不會 hang（forward-compat），但可以順便對。

4. **GRPC_TRACE debug**：`GRPC_TRACE=http,flowctl GRPC_VERBOSITY=DEBUG` 跑一次，看是 SETTINGS/WINDOW_UPDATE 之後死（flow control）還是 DATA frame 發不出（MTU）。

**千萬不要做的事：**
- 不要因為這個徵狀就去改 NPM `grpc_pass` 配置（前面別節已講解正確配置，再改也不會好）
- 不要改 `server.py` Complete handler 加 flush/trailer hack（handler 跟 HealthCheck 同 servicer class，代碼路徑只差一個 await）
- 不要降 deadline 或加 retry（根因是網路 drop，retry 只是把 timeout 變更久）

### 🔴 codex 每次 180s timeout / gemini refresh 寫入失敗（DSM ACL read-only bind mount）

**症狀：**
- `POST /api/chat` 指定 `provider=openai` 卡 ~180s 後 `curl: (28) Operation timed out`
- log 有 `failed to create session: Permission denied (os error 13)` on `/home/app/.codex/sessions`
- 或 `Permission denied: '/home/app/.gemini/oauth_creds.json'`（token refresh 寫回失敗）
- claude 可能正常（讀 token 就夠），但 long-term 也會因為 refresh 失敗壞掉

**根因：** Synology DSM 的 NFSv4 ACL。host 看起來 `drwxrwxrwx+`，但 bind mount 進容器後 `app` user 實際是 read-only。POSIX perm bits 騙人。

**一分鐘快檢：**
```bash
ssh nas "/usr/local/bin/docker exec -u app ai-proxy sh -c 'echo x > /home/app/.codex/test 2>&1'"
# "Permission denied" → 中招
```

**修法（已 commit 32d6d56）：** `entrypoint.sh` root 啟動時 `chmod -R u+w,g+w /home/app/.{claude,gemini,codex}`。重啟後即修復。

**臨時 hotfix（來不及 rebuild）：**
```bash
ssh nas "/usr/local/bin/docker exec -u root ai-proxy chmod -R u+w,g+w /home/app/.claude /home/app/.gemini /home/app/.codex"
```

### 🔴 hotfix 部署 src/*.py 後容器 crashloop（`PermissionError: '/app/src/*.py'`）

**症狀：** 用 `scp → docker cp` 熱更新 Python 檔（不走 rebuild）後容器起不來，log 連環出：
```
PermissionError: [Errno 13] Permission denied: '/app/src/server.py'
```

**根因：** DSM ACL 同一個坑的變形 — host 側 scp 出來的檔案 perms 是 `600`（只 root 讀），`docker cp` 進 image 時保留 600，app user 讀不到。entrypoint 的 chmod 只管 `/home/app/*` 不管 `/app/src`。

**修法：**
```bash
# 1. host 端先 chmod 644（關鍵！docker cp 會帶 perms 進去）
ssh nas "chmod 644 /volume1/docker/proxy-cli/src/*.py /volume1/docker/proxy-cli/proto/*.py"

# 2. stop → cp → chown → start
ssh nas "\
  /usr/local/bin/docker stop ai-proxy && \
  /usr/local/bin/docker start ai-proxy && sleep 3 && \
  /usr/local/bin/docker cp /volume1/docker/proxy-cli/src/server.py ai-proxy:/app/src/server.py && \
  /usr/local/bin/docker cp /volume1/docker/proxy-cli/src/dashboard.py ai-proxy:/app/src/dashboard.py && \
  /usr/local/bin/docker exec -u root ai-proxy sh -c 'chown -R app:app /app/src /app/proto && chmod -R u+r,g+r /app/src /app/proto' && \
  /usr/local/bin/docker restart ai-proxy"
```

**正規做法（日後 rebuild 就沒這問題）：** `docker compose -f deploy-nas/docker-compose.yml up -d --build`（Dockerfile 的 COPY + `chown -R app:app /app` 搞定）。熱更新只是 debug 加速手段，**不是生產流程**。

### 工程師回報「claude 過期時沒 fallback，錯誤直接回 client」

**症狀：** client 收到「claude 憑證已過期」，按理應 fallback 到其他 provider。

**先別改 fallback 邏輯 — 99% 是以下三種狀況之一：**

1. **Fallback chain 全部失效**：`execute_with_fallback` 流程是 CLI → direct API → project fallback_model → FALLBACK_CHAIN。若 chain 上所有 provider CLI 都壞（典型 = DSM ACL bug 那段時間 codex/gemini 都寫不了 session/token），且沒設對應的 API Key env var，chain 回 None，原 claude error 被退回 client。**不是 fallback 邏輯 bug**，是真的沒備援了。驗證：看 `/api/creds` 是否全綠。

2. **瞬時 race**：claude token 剛過期 → 先打到的 request 會走完 fallback，但同一秒內先撈到 `pool.available=True`（slot 還沒被 `mark_failed`）的 request 會走短路徑。回避：client 側保留 retry-once（engineer 已加）。

3. **設定錯**：`config.yaml` 或 env 沒給 fallback provider 可用憑證。`/api/creds` 看哪些 provider `healthy_slots=0`。

**code reference：**
- `src/pool.py:970` `execute_with_fallback` 主流程
- `src/pool.py:1086` `_try_fallback_chain` 跑 chain
- `src/pool.py:835` `FALLBACK_CHAIN` 順序

### 工程師回報「/api/recent 的 group 欄位空字串」

**不是 bug，欄位名稱看錯**。server 回的是 `group_name`（snake_case），不是 `group`。

驗證：
```bash
curl -s "http://192.168.0.126:8091/api/recent?limit=3&project=agent-social" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | grep group_name
# 預期看到 "group_name": "<value>"
```

SQLite 欄位也是 `group_name` 不是 `group`（`group` 是 SQL keyword 會衝突）。Client SDK 如果 typed 成 `r.group` 會永遠 undefined，改用 `r.group_name`。

### `actual_source` 欄位（2026-04-19 新增）

`CompletionResponse` / REST `/api/chat` response 都有 `actual_source: "cli" | "api" | "cache"`：

- `cli`：走 Claude Code / Gemini CLI / codex OAuth（免費額度，ToS 灰區）
- `api`：走付費 API Key（`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / ...）
- `cache`：記憶體 prompt 快取命中（無實際 provider call）

Client 要分開計「免費 OAuth 流量 vs 付費 API 流量」就讀這欄。Commit 7015a1b。

### TLS 憑證快到期
啟動時 log 會顯示剩餘天數，`<30 天` warning、`<7 天` error：
```
TLS 憑證將在 15 天內到期 (2026-05-02T00:00:00+00:00)
```
更新憑證後 `docker restart ai-proxy`。

### Slot 被 quarantine（帳號風控訊號，2026-04-19 新增）

**症狀：** log 出現 `CRITICAL ... slot-N 被永久隔離（帳號風控訊號）`，或 dashboard Claude 風險卡片顯示 🔴 紅燈 + 錯誤訊息含「suspended」/「abuse」/「risk review」等字串。

**意義：** Anthropic backend 對該 OAuth 帳號發出風控訊號。再繼續用會觸發更嚴厲的封鎖（全面停權）。

**處理步驟：**
1. **不要急著清除 quarantine** — 先確認真的是誤判，還是 Anthropic 真的在查
2. 停止該帳號**至少 24 小時**（讓流量行為消失在 risk engine 的觀察窗口）
3. 檢查 `/api/recent?provider=claude` 看最近 24h 流量模式（是否超過 cap？有沒有異常 spike？）
4. 如確認是誤判，手動清除 quarantine：目前**無 dashboard UI，需直接操作容器**
   ```bash
   ssh nas "/usr/local/bin/docker restart ai-proxy"
   # 重啟會清掉記憶體中的 quarantined 狀態（但 risk 訊號會再來 = 沒根治）
   ```
5. 若持續觸發 → 換到 Anthropic 付費 API Key（`ANTHROPIC_API_KEY` env var，走 `_call_claude_apikey` ToS 合規路徑）

### Daily cap 被觸發

**症狀：** log 出現 `Provider claude 今日 Token 已達上限 (NNN/300000)`，dashboard 風險卡片顯示 🟡 或 🔴。

**意義：** 今日累積 Claude token 超過預設 300k cap（避免被 Anthropic 認定為異常使用）。流量會**自動 fallback** 到其他 provider（DeepSeek / OpenAI / Gemini），使用者應看得到回應。

**處理：**
- 若 cap 設太低：dashboard「配額」→ 新增 `target_type=provider, target_name=claude, daily_tokens=500000`（調高）
- 若 cap 合理但被異常流量吃光：查 `/api/recent?provider=claude&days=1` 看是誰在狂用
- 等午夜 UTC 00:00（台灣 08:00）counter 自動重置

