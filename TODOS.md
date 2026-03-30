# 叮咚到號 — 待辦事項

> 最後更新：2026-03-30

## P0 — 阻擋上線

- [x] 輸入驗證：LINE 訊息長度 500 字、掛號號碼上限 9999
- [x] Celery task 重試：max_retries=3, default_retry_delay=30
- [x] main.py 種子資料抽離到 data/seed_hospitals.json + seed_aliases.json

## P1 — MVP 品質

- [x] 結構化日誌（python-json-logger）
- [x] 爬蟲連續失敗 3 次告警管理員
- [x] 過號超過 30 分鐘自動停止追蹤
- [x] 第一次使用 3 步驟引導
- [x] 使用分析埋點 + analytics_events 表
- [x] Admin 儀表板：活躍用戶、追蹤排行、爬蟲成功率、通知數
- [x] 核心路徑 pytest 測試（17 個測試全通過）
- [x] .env.example 更新
- [x] 通知原子性修復（推播失敗不更新 DB）
- [x] Redis 超時 + 錯誤處理（5 秒超時、fallback 空結果）
- [x] Health endpoint（含 Redis/DB 健康檢查）
- [x] JWT secret 獨立化
- [x] DB pool_pre_ping
- [x] Alembic migration 自動化（Docker entrypoint）

## P2 — 上線後迭代

- [ ] PRO 付費功能（同時追蹤 3 位醫師、提前 N 號提醒）
- [ ] 金流串接（LINE Pay / 信用卡）
- [ ] 預估等候時間演算法（需歷史數據累積）
- [ ] CI/CD pipeline（GitHub Actions）
- [ ] ruff linter + pre-commit hook

## P3 — 未來規劃

- [ ] 家庭方案 + 長輩模式（大字體、語音播報）
- [ ] 新增更多醫院（目標 50+ 家）
- [ ] 候診推薦（附近藥局/餐廳）
- [ ] B2B 醫院品牌專頁
- [ ] Telegram Bot 備案
