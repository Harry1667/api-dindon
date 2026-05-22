---
name: worklog
description: 上傳或更新工作日誌到 worklog.looptw.com
triggers:
  - 上傳工作日誌
  - 寫工作日誌
  - 記錄工作
  - 更新工作日誌
  - 續寫工作日誌
  - log work
  - worklog
---

## Worklog Skill

這個 skill 會將當前工作內容記錄到 https://worklog.looptw.com。

### 設定

- API: `https://worklog.looptw.com/api/log`
- Token: `83683276`
- 台灣時區 (UTC+8)

### 執行步驟

**Step 1 — 取得今天日期（台灣時間 UTC+8）**

```bash
TODAY=$(TZ=Asia/Taipei date +%Y-%m-%d)
echo "TODAY: $TODAY"
```

**Step 2 — 取得專案資訊**

```bash
PROJECT_PATH=$(pwd)
PROJECT_NAME=$(basename "$PROJECT_PATH")
GIT_REMOTE=$(git remote get-url origin 2>/dev/null || echo "no-git")
GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
GIT_STATUS=$(git status --short 2>/dev/null | head -20 || echo "no changes")
GIT_LOG=$(git log --oneline -5 2>/dev/null || echo "no commits")
echo "PROJECT: $PROJECT_NAME"
echo "BRANCH: $GIT_BRANCH"
echo "REMOTE: $GIT_REMOTE"
echo "STATUS: $GIT_STATUS"
echo "RECENT COMMITS: $GIT_LOG"
```

**Step 3 — 查詢今天是否已有該專案的日誌**

```bash
EXISTING=$(curl -s \
  -H "Authorization: Bearer 83683276" \
  "https://worklog.looptw.com/api/log?date=$TODAY")
echo "EXISTING ENTRIES: $EXISTING"
```

**Step 4 — 判斷模式並生成日誌內容**

根據以下資訊生成自然語言的工作日誌（繁體中文，簡潔專業）：
- 觸發語句（"上傳" vs "更新"）
- 現有日誌條目（Step 3 的結果）
- 當前對話中討論的工作內容
- Git 狀態與最近 commit（Step 2 的結果）
- 專案名稱與路徑

**CREATE 模式**（觸發語句含「上傳」、「寫」、「記錄」，或今天沒有任何條目）：
- 總結今天在這個專案完成的工作
- 格式：`[專案名] 工作摘要，包含主要完成項目、解決問題、技術細節`

**UPDATE 模式**（觸發語句含「更新」、「續寫」，且今天已有條目）：
- 查看現有條目內容，找出上次記錄後新完成的工作
- 格式：`（續）新完成的工作項目`

**Step 5 — 發送到 worklog**

```bash
# 將 CONTENT 替換為 Step 4 生成的實際內容
CONTENT="<Step 4 生成的內容>"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "https://worklog.looptw.com/api/log" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 83683276" \
  -d "{\"content\": $(echo "$CONTENT" | jq -Rs .), \"date\": \"$TODAY\"}")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [[ "$HTTP_CODE" == "201" ]]; then
  ID=$(echo "$BODY" | jq -r '.id // "unknown"')
  echo "✓ 日誌已記錄 [${TODAY}] id=${ID}"
else
  echo "✗ 失敗 (HTTP ${HTTP_CODE}): $BODY"
fi
```

**Step 6 — 回報結果**

告訴使用者：
- 日期與專案名稱
- 記錄的內容摘要
- 若成功：entry ID 和 worklog 連結 `https://worklog.looptw.com/${TODAY}`
- 若失敗：錯誤原因
