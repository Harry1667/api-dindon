# todo-review

**指令：** `/todo-review`

## 是什麼

掃描專案裡所有的技術債標記（TODO、FIXME、HACK、XXX、DEPRECATED），
整理成按嚴重程度排序的清單，讓你知道目前有多少欠債、哪些最緊急。

## 怎麼用

在 Claude Code 輸入 `/todo-review`，不需要帶任何參數。

Skill 會自動：
1. 掃描當前專案目錄（排除 `node_modules`、`dist`、`build`、`.git`）
2. 依嚴重程度分類：
   - 🔴 FIXME — 需要修復的 bug
   - 🟡 HACK / XXX — 已知技術債
   - 🔵 TODO — 待辦功能
   - ⚠️ DEPRECATED — 已棄用的 API
3. 列出檔案路徑 + 行號，方便直接跳過去看

> 只整理報告，不自動修改任何 TODO。要修某個才動手。
