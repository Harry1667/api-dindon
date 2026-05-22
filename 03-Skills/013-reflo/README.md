# ruflo

**指令：** `/ruflo`（或說「用 ruflo 幫我做 XX」）

## 是什麼

Ruflo 多智能體 AI 協調平台的使用 skill。
讓 Claude 幫你初始化 Ruflo、建立任務、協調多個 AI 智能體一起工作。

## 安裝（一次性）

```bash
npm install -g ruflo@latest
claude mcp add ruflo -- npx ruflo@latest mcp start
# 重啟 Claude Code
```

## 每個新專案初始化

```bash
cd 你的專案目錄
ruflo init --start-all
```

## 怎麼用

說以下任何一句都會觸發：

```
/ruflo
用 ruflo 幫我建立財小幫的 MVP
用多智能體幫我分析這個專案
用 autopilot 幫我完成任務
```

Claude 會自動：
1. 確認 Ruflo 已初始化
2. 建立任務描述
3. 啟動 autopilot 或手動指派智能體
4. 監控進度並儲存記憶

## 主要指令速查

```bash
ruflo status                          # 系統狀態
ruflo task create "任務描述"           # 建立任務
ruflo autopilot                       # 自動執行到完成
ruflo agent spawn -t coder            # 生成程式碼智能體
ruflo memory store "重要資訊"          # 儲存記憶
ruflo memory search -q "關鍵字"        # 搜尋記憶
ruflo daemon start                    # 啟動背景 Daemon
```

## 適合用在

- 複雜多步驟的開發任務（如：從 PRD 到產生 scaffold）
- 需要多種角色協作的工作（coder + analyzer + tester）
- 跨 session 需要保留知識的長期專案
