# 全局 Skills 詳細說明

自製 skill 在 `001-xxx` ~ `011-xxx`。
這裡是所有從 skills.sh 安裝的 skill，每個都有說明、下載網址、安裝指令。
gstack 生態系內建的 skill 在下方第二區塊。

---

## 換電腦一鍵重裝腳本

```bash
# 複製整段執行，會重新安裝所有外部 skill
BASE_ANTHROPIC="https://raw.githubusercontent.com/anthropics/skills/main/skills"
BASE_VERCEL="https://raw.githubusercontent.com/vercel-labs/agent-skills/main/skills"

for skill in frontend-design skill-creator webapp-testing mcp-builder; do
  mkdir -p ~/.claude/skills/$skill
  curl -sL "$BASE_ANTHROPIC/$skill/SKILL.md" -o ~/.claude/skills/$skill/SKILL.md
  echo "✅ $skill"
done

for skill in react-best-practices web-design-guidelines composition-patterns; do
  mkdir -p ~/.claude/skills/$skill
  curl -sL "$BASE_VERCEL/$skill/SKILL.md" -o ~/.claude/skills/$skill/SKILL.md
  echo "✅ $skill"
done
```

自製 skill（001～011）要另外從 GitHub repo clone 回來，或從備份恢復。

---

## 已安裝的 skills.sh Skills

---

### `/skill-creator`
**是什麼：** 用來開發、測試、改進 skill 的元工具（Anthropic 出品）。引導你從零寫 SKILL.md、建測試案例、跑平行評估、優化觸發描述。

**怎麼用：**

| 情況 | 說法 |
|---|---|
| 從零寫新 skill | 「幫我建一個 skill，功能是 XX」 |
| 改進現有 skill | 「優化 /deploy-sop 的觸發準確度」 |
| 測試 skill 效果 | 「跑 eval 測試 /git-safety」 |

**下載網址：**
```bash
mkdir -p ~/.claude/skills/skill-creator
curl -sL "https://raw.githubusercontent.com/anthropics/skills/main/skills/skill-creator/SKILL.md" \
  -o ~/.claude/skills/skill-creator/SKILL.md
```

---

### `/frontend-design`
**是什麼：** 產出有設計感的前端 UI，避免 AI 通用感（Anthropic，332K 安裝）。

**怎麼用：**

| 情況 | 說法 |
|---|---|
| 建新頁面 | 「幫我設計一個 landing page，產品是 XX」 |
| 美化元件 | 「這個 card component 重新設計一下」 |
| 做 dashboard | 「設計一個數據儀表板」 |

**下載網址：**
```bash
mkdir -p ~/.claude/skills/frontend-design
curl -sL "https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md" \
  -o ~/.claude/skills/frontend-design/SKILL.md
```

---

### `/webapp-testing`
**是什麼：** 針對 web app 的測試 skill，寫測試、跑測試、找問題（Anthropic，54K 安裝）。

**怎麼用：**

| 情況 | 說法 |
|---|---|
| 幫功能寫測試 | 「幫登入流程寫測試」 |
| 找測試缺口 | 「這個 API 有沒有測試沒覆蓋到的地方」 |

**下載網址：**
```bash
mkdir -p ~/.claude/skills/webapp-testing
curl -sL "https://raw.githubusercontent.com/anthropics/skills/main/skills/webapp-testing/SKILL.md" \
  -o ~/.claude/skills/webapp-testing/SKILL.md
```

---

### `/mcp-builder`
**是什麼：** 建立 MCP（Model Context Protocol）server 的工具，讓 Claude 能連接外部工具和 API（Anthropic，43K 安裝）。

**怎麼用：**

| 情況 | 說法 |
|---|---|
| 建新的 MCP server | 「幫我建一個 MCP server，連接 XX API」 |
| 擴充 Claude 工具 | 「我想讓 Claude 能讀我的資料庫」 |

**下載網址：**
```bash
mkdir -p ~/.claude/skills/mcp-builder
curl -sL "https://raw.githubusercontent.com/anthropics/skills/main/skills/mcp-builder/SKILL.md" \
  -o ~/.claude/skills/mcp-builder/SKILL.md
```

---

### `/react-best-practices`
**是什麼：** React / Next.js 效能優化指引，70 條規則（Vercel，345K 安裝）。

**怎麼用：**

| 情況 | 說法 |
|---|---|
| 寫新元件 | 「按 best practices 幫我寫這個 component」 |
| review 現有 code | 「這段有沒有違反 react best practices」 |
| 解效能問題 | 「這個頁面 re-render 太多次」 |

**涵蓋：** Waterfall、Bundle size、Server vs Client Component、useEffect 正確用法、Re-render 優化

**下載網址：**
```bash
mkdir -p ~/.claude/skills/react-best-practices
curl -sL "https://raw.githubusercontent.com/vercel-labs/agent-skills/main/skills/react-best-practices/SKILL.md" \
  -o ~/.claude/skills/react-best-practices/SKILL.md
```

---

### `/web-design-guidelines`
**是什麼：** 對照 Vercel 設計規範自動 review UI code（Vercel，275K 安裝）。

**怎麼用：**

| 情況 | 說法 |
|---|---|
| review 元件 | 「review 一下 src/components/Card.tsx」 |
| 無障礙檢查 | 「check 這頁面的 accessibility」 |

**下載網址：**
```bash
mkdir -p ~/.claude/skills/web-design-guidelines
curl -sL "https://raw.githubusercontent.com/vercel-labs/agent-skills/main/skills/web-design-guidelines/SKILL.md" \
  -o ~/.claude/skills/web-design-guidelines/SKILL.md
```

---

### `/composition-patterns`
**是什麼：** React 元件組合設計模式（Vercel，147K 安裝）。教你怎麼設計可複用、可組合的元件結構。

**怎麼用：**

| 情況 | 說法 |
|---|---|
| 設計元件結構 | 「這個功能用什麼 composition pattern 比較好」 |
| 重構巢狀元件 | 「這個元件太複雜，幫我拆開」 |

**下載網址：**
```bash
mkdir -p ~/.claude/skills/composition-patterns
curl -sL "https://raw.githubusercontent.com/vercel-labs/agent-skills/main/skills/composition-patterns/SKILL.md" \
  -o ~/.claude/skills/composition-patterns/SKILL.md
```

---

## 值得考慮但尚未安裝

| Skill | 出品方 | 安裝數 | 適合你的理由 |
|---|---|---|---|
| `pdf` / `docx` / `xlsx` | Anthropic | 各 60~83K | 需要 AI 讀寫文件時 |
| `canvas-design` | Anthropic | 43K | 做圖形化設計 |
| `supabase` | Supabase | 16K | 如果專案改用 Supabase |
| `stripe-best-practices` | Stripe | — | 如果要加金流 |
| `resend` | Resend | 13K | 如果要發信功能 |

安裝任何一個的指令格式：
```bash
mkdir -p ~/.claude/skills/<name>
curl -sL "https://raw.githubusercontent.com/<owner>/<repo>/main/skills/<name>/SKILL.md" \
  -o ~/.claude/skills/<name>/SKILL.md
```

---

## gstack 生態系（全局內建，不需安裝）

### 瀏覽器 / QA 測試

| 指令 | 是什麼 | 怎麼用 |
|---|---|---|
| `/gstack` | AI 控制的無頭瀏覽器，可截圖、點擊、抓 console error | 「gstack 幫我測 localhost:3000 的登入流程」 |
| `/browse` | 輕量瀏覽器，快速瀏覽和抓資訊 | 「去 https://mentora.looptw.com 看現在的版本」 |
| `/qa` | 系統性 QA，**找到 bug 自動修** | 「qa 測一下 localhost:3000」 |
| `/qa-only` | 只報告，不自動改 code | 同上，但只列清單 |
| `/canary` | 部署後線上監控 | 「canary 監控 https://mentora.looptw.com」 |
| `/design-review` | 設計師視角找視覺問題 | 「design-review localhost:3000」 |
| `/devex-review` | 實際測試開發者體驗 | 「review 一下開發者使用這個 API 的體驗」 |

### 程式碼品質 / 審查

| 指令 | 是什麼 | 怎麼用 |
|---|---|---|
| `/review` | PR 合併前深度 review（SQL 安全、效能、測試） | commit 前直接跑 |
| `/health` | 整合 tsc + lint + test，一次看全貌 | 「/health」不用帶參數 |
| `/investigate` | 系統性 debug，四階段找根本原因 | 「investigate 為什麼這個 API 有時候回 500」 |
| `/retro` | 分析 commit 歷史，週回顧 | 每週結束跑一次 |

### 部署 / 發布

| 指令 | 是什麼 | 怎麼用 |
|---|---|---|
| `/ship` | merge + 跑測試 + bump VERSION + 部署 | 功能做完要發布時 |
| `/land-and-deploy` | merge PR + 等 CI + 確認部署 | PR 已 approve 後 |
| `/document-release` | 發布後更新所有文件 | 部署完後跑 |

### 設計 / 規劃

| 指令 | 是什麼 | 怎麼用 |
|---|---|---|
| `/design-consultation` | 了解產品、研究競品、提設計策略 | 「新功能不知道怎麼設計」 |
| `/design-shotgun` | 一次生成多個設計變體 | 「幫我做 3 種 hero section 設計」 |
| `/design-html` | 產出 production 等級 HTML/CSS | 「做一個 email template」 |
| `/autoplan` | CEO / 設計 / 工程 / DX 四視角 review 計畫 | 「autoplan，我打算這樣做：...」 |
| `/office-hours` | YC Office Hours，找產品盲點 | 「我的產品是 XX，幫我找盲點」 |
| `/plan-eng-review` | 工程主管視角審查計畫 | 有架構計畫要確認時 |

### 安全 / 限制

| 指令 | 是什麼 | 怎麼用 |
|---|---|---|
| `/careful` | 高風險指令執行前強制確認 | session 開始時執行 |
| `/freeze <dir>` | 限制 AI 只能改指定目錄 | 「freeze src/」 |
| `/guard <dir>` | `/careful` + `/freeze` 組合包 | 「guard src/」 |
| `/cso` | 基礎設施完整安全稽核 | 要做安全審查時 |

### 工具 / 工作流

| 指令 | 是什麼 | 怎麼用 |
|---|---|---|
| `/context-save` | 儲存目前工作狀態（git、決定、待辦） | 暫停工作前 |
| `/context-restore` | 還原上次儲存的狀態 | 開新 session 時 |
| `/learn` | 管理專案 learnings，搜尋整理 | 「learn search 關鍵字」 |
| `/benchmark` | 效能回歸偵測 | 改動後確認沒變慢 |
| `/codex` | OpenAI Codex CLI 包裝 | 「codex review 這個 PR」 |
