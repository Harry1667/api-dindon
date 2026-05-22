# env-check

**指令：** `/env-check`

## 是什麼

一鍵檢查本地開發環境的健康狀態。
跑起來前先確認環境正常，省得 debug 半天才發現是 Docker 沒開或 port 被佔了。

## 怎麼用

在 Claude Code 輸入 `/env-check`，不需要帶任何參數。

Skill 會自動檢查：
1. **Runtime 版本**：Node / npm / Python3 / Docker / git 是否安裝、版本號
2. **Docker 容器**：正在跑哪些、哪些已停止
3. **Port 佔用**：掃描 3000、3001、3002、8080、8091、50051 等常用 port
4. **.env 完整性**：比對 `.env` 和 `.env.example`，找出缺少的 key
5. **磁碟空間**：根目錄剩多少、Docker 佔了多少

輸出範例：
```
## 環境檢查報告 2026-04-24 10:30

### ✅ 正常
- Node v22.3.0, npm 10.8.1
- Docker：2 個容器運行中

### ⚠️ 需注意
- Port 3000 被 node (PID 12345) 佔用
- .env 缺少 OPENAI_API_KEY

### ❌ 問題
- 磁碟使用率 92%
```
