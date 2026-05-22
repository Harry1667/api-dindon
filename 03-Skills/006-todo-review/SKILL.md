---
name: todo-review
description: |
  掃描專案中所有 TODO、FIXME、HACK、XXX、DEPRECATED 並整理清單。
  按嚴重程度分類，標示檔案位置，可選擇性修復。
  Use when: "todo", "fixme", "待辦", "技術債", "scan todos", "查 TODO"
triggers:
  - todo review
  - scan todos
  - 查 TODO
  - 技術債
  - fixme 清單
allowed-tools:
  - Bash
  - Read
  - Edit
---

# /todo-review — 專案 TODO 掃描

掃描整個專案的技術債標記，整理成優先度清單。

## 執行步驟

### 1. 掃描所有標記

```bash
echo "=== 專案 TODO 掃描 ==="
echo "路徑：$(pwd)"
echo ""

EXCLUDES="--exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=build --exclude-dir=.next --exclude-dir=.vite"
INCLUDES="--include=*.ts --include=*.tsx --include=*.js --include=*.jsx --include=*.py --include=*.go --include=*.rs --include=*.md"

echo "🔴 FIXME（需要修復）"
grep -rn "FIXME" $INCLUDES $EXCLUDES . 2>/dev/null | head -30
echo ""

echo "🟡 HACK / XXX（技術債）"
grep -rn "HACK\|XXX" $INCLUDES $EXCLUDES . 2>/dev/null | head -30
echo ""

echo "🔵 TODO（待辦）"
grep -rn "TODO" $INCLUDES $EXCLUDES . 2>/dev/null | head -50
echo ""

echo "⚠️ DEPRECATED"
grep -rn "DEPRECATED\|@deprecated" $INCLUDES $EXCLUDES . 2>/dev/null | head -20
```

### 2. 統計總數

```bash
EXCLUDES="--exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=build"
echo "=== 統計 ==="
echo "FIXME: $(grep -rn "FIXME" $EXCLUDES . 2>/dev/null | wc -l | tr -d ' ') 個"
echo "HACK/XXX: $(grep -rn "HACK\|XXX" $EXCLUDES . 2>/dev/null | wc -l | tr -d ' ') 個"
echo "TODO: $(grep -rn "TODO" $EXCLUDES . 2>/dev/null | wc -l | tr -d ' ') 個"
echo "DEPRECATED: $(grep -rn "DEPRECATED\|@deprecated" $EXCLUDES . 2>/dev/null | wc -l | tr -d ' ') 個"
```

### 3. 輸出格式

```
## TODO 掃描報告 — [專案名] [日期]

### 🔴 FIXME（立即處理）
| 檔案 | 行號 | 內容 |

### 🟡 技術債（HACK / XXX）
...

### 🔵 待辦（TODO）
...

### 統計
- 總計：X 個標記
- 建議優先處理：（列出最重要的 3 個）
```

## 注意事項

- 掃描結果若 >50 個，先列統計，再問使用者要看哪個類型
- 不要自動修改任何 TODO，只整理報告；使用者要修才動手
- 沒指定目錄就從 `pwd` 開始掃
