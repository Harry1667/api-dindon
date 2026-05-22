---
name: daily-standup
description: |
  從 git log 自動整理今日工作摘要，產出 standup 格式報告。
  列出今日完成的 commit、修改的檔案、跨專案整合。
  Use when: "standup", "今日進度", "工作摘要", "daily report", "今天做了什麼"
triggers:
  - daily standup
  - 今日進度
  - 工作摘要
  - 今天做了什麼
allowed-tools:
  - Bash
  - Read
---

# /daily-standup — 今日工作摘要

從 git log 整理今天的工作，產出 standup 格式。

## 執行步驟

### 1. 掃描所有 git repo 的今日 commit

```bash
TODAY=$(date +%Y-%m-%d)

echo "=== 今日 Git 活動 ($TODAY) ==="
echo ""

for BASE in ~/Documents/0-Dev ~/Documents; do
  find "$BASE" -name ".git" -maxdepth 5 -type d 2>/dev/null | while read GITDIR; do
    REPO=$(dirname "$GITDIR")
    REPO_NAME=$(basename "$REPO")
    COMMITS=$(git -C "$REPO" log --oneline --since="$TODAY 00:00" --until="$TODAY 23:59" 2>/dev/null)
    if [ -n "$COMMITS" ]; then
      echo "📁 $REPO_NAME"
      echo "$COMMITS" | sed 's/^/  /'
      echo ""
    fi
  done
done
```

### 2. 整理今日修改的檔案

```bash
TODAY=$(date +%Y-%m-%d)

if git rev-parse --git-dir > /dev/null 2>&1; then
  echo "=== 今日修改檔案（當前 repo）==="
  git log --since="$TODAY 00:00" --name-only --pretty="" | sort -u | grep -v '^$'
fi
```

### 3. 輸出格式

根據掃描結果，整理成以下格式後輸出：

```
## 今日完成 (Done)
- [repo 名] 功能/修復描述（來自 commit message）

## 進行中 (In Progress)
- 尚未 commit 的工作（從 git status 推測）

## 遇到的問題 (Blockers)
- 如有發現未解決的 TODO 或 FIXME

## 明日計畫 (Next)
- 根據最後 commit 訊息推測
```

## 注意事項

- 如果今日沒有 commit，說明「今日無 git 活動」
- commit message 直接用原文，不翻譯
- 不要顯示 commit hash，只顯示訊息
- 多個 repo 的 commit 按時間倒序合併
