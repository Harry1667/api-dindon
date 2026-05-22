# config.yaml 完整範本

> 主檔 SKILL.md 不再放完整範本，需要時 Read 進來。


```yaml
server:
  grpc_port: 50051
  dashboard_port: 8080
  tls_enabled: false
  tls_cert: certs/server.crt
  tls_key: certs/server.key

users:
- name: admin
  token: <admin-token>         # 備份/還原/CSV 匯出 需要的就是這個 token
- name: user1
  token: <user1-token>

projects:
- web-app
- data-pipeline

pool:
  min_size: 2                  # 目前未生效（保留）
  max_size: 4
  max_queue_depth: 10
  request_timeout: 60
  queue_timeout: 30            # 目前未生效（保留）
  # health_probe_interval: 已 deprecated（2026-04-19 ToS 合規：排程 probe 全部移除）
  # 保留 key 避免破壞舊 config，但系統不再讀取。
  race_mode: false             # true = 多 slot 並行競速（⚠️ 單 slot 政策下無意義，保留 flag 不會觸發）

routing:
  auto: false                  # true = client 未指定 model+tier 時依 prompt 自動分類

providers:
  claude:
    enabled: true              # false = 不初始化 pool
    command: claude
    fallback_model: claude-haiku-4-5
  gemini:
    enabled: true
    command: gemini
    fallback_model: gemini-2.5-flash
  openai:
    enabled: true              # 必須 true 才能用 codex fallback
    command: codex
    fallback_model: gpt-4o-mini

cache:
  max_size: 200
  ttl: 300                     # 秒

security:
  rate_limit_per_minute: 0     # 0 = 不限流
  max_tokens_per_request: 8192
```

