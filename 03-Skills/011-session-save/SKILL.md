---
name: session-save
description: |
  儲存目前工作階段的摘要，方便下次繼續。整理完成事項、未完成、決策紀錄、下次起點，
  寫入 SESSION_NOTES.md。
  Use when: "save", "update", "bye", "結束", "儲存進度", "工作階段結束"
triggers:
  - save
  - update
  - bye
  - 結束
  - 儲存進度
  - 工作階段結束
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# /session-save — 工作階段儲存

不用問使用者任何問題，直接根據目前對話內容整理並寫入檔案。

---

## Step 1：整理摘要

從目前對話中整理出以下內容：

```
日期：{今天日期，格式 YYYY-MM-DD}
專案：{從對話判斷正在做哪個專案，無法判斷寫「跨專案」}

## ✅ 本次完成
- {列出這次對話裡做完的事，每條一行}

## 🔄 未完成 / 進行中
- {列出開始了但還沒做完的事}

## 💡 重要決策 / 發現
- {這次對話裡做的重要決定、找到的關鍵問題、學到的事}

## 🚀 下次起點
{下次開啟工作時應該從哪裡繼續，越具體越好，包含檔案路徑或指令}

## 📁 相關檔案
- {這次修改或建立的重要檔案路徑}
```

---

## Step 2：寫入 SESSION_NOTES.md

找出要寫入的位置：
1. 如果對話中有明確的專案目錄 → 寫到該專案的 `SESSION_NOTES.md`
2. 如果是跨專案或 skills 相關工作 → 寫到 `~/Documents/0-Dev/0-WebDev/03-Skills/SESSION_NOTES.md`

```bash
# 確認目標路徑存在
ls <目標目錄>/SESSION_NOTES.md 2>/dev/null || echo "新建"
```

寫入格式：**新的紀錄加在檔案最上面**（最新的在最前面），舊的往下推。

---

## Step 3：確認完成

寫入後回覆使用者：

```
✅ 已儲存到 <路徑>/SESSION_NOTES.md

本次摘要：
- 完成：X 件事
- 未完成：X 件事
- 下次起點：{一句話描述}
```
