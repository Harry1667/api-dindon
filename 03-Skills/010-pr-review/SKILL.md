---
name: pr-review
description: |
  Commit 或 PR 前的 code review checklist。檢查命名、安全性、效能、型別、
  死碼清理。不是 git-safety（那個是掃 secret），這個是掃程式碼品質。
  Use when: "code review", "commit 前", "PR 前", "檢查 code", "review 一下"
triggers:
  - code review
  - commit 前檢查
  - PR 前
  - 檢查 code
  - review
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# /pr-review — Commit / PR 前 Code Review

先跑安全掃描，再做 code review：

```bash
# 1. 先確認沒有 secret 洩漏（呼叫 git-safety 的掃描指令）
git diff --cached | grep -iE "(password|secret|token|api[_-]?key|ghp_|sk-|AKIA)"
git ls-files | grep -E '\.env$|\.key$|\.pem$|\.sqlite$'
# 兩個都應該沒有輸出
```

有問題先用 `/git-safety` 處理。

---

## Review Checklist

### 🔴 必過（有任何一項就不能 commit）

```
□ 沒有 console.log / print / debugger 留在 production 路徑
□ 沒有 hardcode 的 API key、密碼、token
□ 沒有 TODO 留在新加的 critical 路徑上
□ API endpoint 有驗證（auth check / token 驗證）
□ 用戶輸入有做基本驗證，不直接塞進 SQL / shell command
```

### 🟡 品質（盡量過）

```
□ 函式名、變數名說清楚它在做什麼（不用縮寫）
□ 一個函式只做一件事（超過 50 行考慮拆）
□ async/await 的 error 有被 catch（不要 silent fail）
□ TypeScript：沒有 any，沒有 as unknown as X
□ 刪掉死碼（被 comment 掉超過一週的、沒人呼叫的 function）
```

### 🔵 效能（視情況）

```
□ 迴圈裡沒有發 API request（N+1 問題）
□ 大量資料有分頁，不是一次 fetch 全部
□ 圖片有壓縮 / lazy load
□ 沒有不必要的 re-render（React useEffect 依賴有寫對）
```

---

## 自動掃描指令

```bash
# 找 console.log
grep -rn "console\.log\|console\.error\|debugger" src/ --include="*.ts" --include="*.tsx" --include="*.js"

# 找 TODO / FIXME
grep -rn "TODO\|FIXME\|HACK\|XXX" src/ --include="*.ts" --include="*.tsx"

# 找 hardcode 的 any（TypeScript）
grep -rn ": any\b\|as any\b" src/ --include="*.ts" --include="*.tsx"

# 找可能忘了 await 的 async call
grep -rn "^\s*[a-zA-Z].*();" src/ --include="*.ts" | grep -v "//\|return\|const\|let\|var\|throw"
```

---

## Commit message 格式

```
<type>: <簡短說明>

類型：
  feat     新功能
  fix      修 bug
  refactor 重構（不改功能）
  style    格式、空白（不改邏輯）
  docs     文件
  chore    設定、依賴更新
  test     測試

範例：
  feat: 新增課程進度追蹤
  fix: 修正 Safari 上公式渲染錯位
  refactor: 拆分 UserCard 成更小的 component
```

---

## 最後推上去前

```bash
# TypeScript 檢查
npx tsc --noEmit

# Lint
npm run lint

# Build 過才推
npm run build
```
