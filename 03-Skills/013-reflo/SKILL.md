---
name: ruflo
description: |
  使用 Ruflo 多智能體平台協調 AI 智能體完成複雜任務。
  支援：初始化專案、建立任務、啟動 autopilot、管理 swarm、搜尋記憶。
  Use when: "用 ruflo", "多智能體", "autopilot", "swarm", "派任務給 AI", "ruflo 幫我"
triggers:
  - 用 ruflo
  - 多智能體
  - autopilot
  - swarm
  - ruflo 幫我
  - 派任務給 AI
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - mcp__ruflo__task_create
  - mcp__ruflo__task_list
  - mcp__ruflo__agent_spawn
  - mcp__ruflo__agent_list
  - mcp__ruflo__swarm_init
  - mcp__ruflo__swarm_status
  - mcp__ruflo__memory_store
  - mcp__ruflo__memory_search
  - mcp__ruflo__system_health
  - mcp__ruflo__autopilot_enable
---

# /ruflo — 多智能體 AI 任務協調

## 前置確認

先用 MCP 工具檢查系統健康狀態：
- 呼叫 `mcp__ruflo__system_health`
- 若 memory 或 config 顯示 degraded，提示使用者執行初始化步驟

---

## Step 1：確認當前專案是否已初始化

```bash
ls .claude-flow/config.yaml 2>/dev/null && echo "已初始化" || echo "未初始化"
```

**若未初始化**，執行：
```bash
ruflo init --start-all
```

產生的目錄結構：
- `.claude/agents/` — 98 個預建智能體定義
- `.claude/commands/` — 10 個指令
- `.claude-flow/` — 設定、log、session

---

## Step 2：釐清使用者的任務

詢問（或從對話中判斷）：
1. **要完成什麼任務？** — 具體描述，越詳細越好
2. **希望用哪種方式？**
   - A. autopilot（全自動，適合複雜多步驟任務）
   - B. 手動指派（控制每個智能體的工作）

---

## Step 3A：autopilot 模式（推薦）

```bash
# 建立任務
ruflo task create "{使用者的任務描述}"

# 啟動 autopilot — 持續執行直到完成
ruflo autopilot
```

監控進度：
```bash
ruflo task list
ruflo agent list
ruflo status
```

---

## Step 3B：手動多智能體模式

依任務性質生成對應智能體：

| 任務類型 | 智能體類型 |
|----------|-----------|
| 寫程式碼 | `ruflo agent spawn -t coder` |
| 架構分析 | `ruflo agent spawn -t analyzer` |
| 資料蒐集 | `ruflo agent spawn -t researcher` |
| 測試驗證 | `ruflo agent spawn -t tester` |

```bash
ruflo agent list           # 確認智能體已啟動
ruflo task assign <task-id> <agent-id>   # 指派任務
ruflo task list            # 查看進度
```

---

## Step 4：儲存重要資訊到記憶體

完成任務後，把關鍵發現存起來供下次使用：

透過 MCP 工具 `mcp__ruflo__memory_store` 儲存：
- 專案技術棧與架構決策
- 已知問題與解法
- 重要設定值

或用 CLI：
```bash
ruflo memory store "{重要資訊}"
ruflo memory search -q "{關鍵字}"   # 之後搜尋
```

---

## 常見問題排除

| 問題 | 解法 |
|------|------|
| Daemon 沒在跑 | `ruflo daemon start` |
| memory degraded | `ruflo memory init` |
| swarm unknown | `ruflo swarm init --v3-mode` |
| MCP 工具不見 | 重啟 Claude Code |
| 已初始化但要重置 | `ruflo init --force` |

---

## 完成後回報

任務完成時，告訴使用者：
```
✅ Ruflo 任務完成

- 執行的智能體：{N} 個
- 完成任務數：{N}
- 記憶已儲存：{Y/N}
- 下次可用 `ruflo memory search -q "..."` 找回相關記憶
```
