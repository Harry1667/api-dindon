---
name: git-safety
description: |
  Git 安全規則：commit 前掃描 secret、.gitignore 範本、敏感檔處理、事故救援。
  來自 2026-04-10 SurvivalWallet 真實事故的硬性規則化。
  Use when: "git commit", "git add", "commit 前", "敏感資訊", "secret 掃描",
  "gitignore", "PAT 洩漏", "git filter-branch", "push protection"
triggers:
  - git commit 前
  - secret 掃描
  - gitignore 範本
  - PAT 洩漏
  - 敏感資訊 commit
  - git 安全
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# /git-safety — Git 安全規則

來自 2026-04-10 SurvivalWallet 真實事故的硬性規則化。

---

## 一行版速查

| 類型 | 進 git？ |
|---|---|
| 程式碼、SQL schema、`.env.example`（只有 placeholder）| ✅ |
| 部署 SOP（用占位符，不含真實 IP/帳密）| ✅ |
| Lockfile（`package-lock.json`, `bun.lock`）| ✅ **必須進** |
| `.env`、`.env.*`（除 `.env.example`）| ❌ **永遠不進** |
| 含**真實**密碼/token/IP/帳號的任何檔案 | ❌ **永遠不進** |
| `*.key`、`*.pem`、SSH private key | ❌ **永遠不進** |
| `node_modules/`、`dist/`、`build/`、`.cache/` | ❌ |
| `.DS_Store`、`Thumbs.db`、`._*` | ❌ |
| SQLite production 資料 | ⚠️ 預設不進 |

---

## commit 前 30 秒安全檢查

**每次 `git add` 之後、`git commit` 之前跑這個：**

```bash
# 1. 看 staged 清單，肉眼掃一遍
git diff --cached --stat

# 2. grep 掃常見 secret pattern
git diff --cached | grep -iE "(password|密碼|secret|token|api[_-]?key|ghp_|ghs_|sk-|AKIA|BEGIN [A-Z ]+PRIVATE KEY)"

# 3. 有 hit → STOP，先處理再 commit
```

加成 alias（貼到 `~/.zshrc`）：

```bash
alias gck='git diff --cached | grep -iE "(password|密碼|secret|token|api[_-]?key|ghp_|ghs_|sk-|AKIA|BEGIN [A-Z ]+PRIVATE KEY)" && echo "⚠️ 偵測到可能的 secret！" || echo "✅ staged diff 看起來乾淨"'
```

---

## Secret Pattern 辨識

```
ghp_ / ghs_ / gho_ 開頭 + 36 字元 → GitHub PAT
sk- 開頭 → LLM API key（OpenAI / Anthropic）
AKIA 開頭 → AWS access key
BEGIN PRIVATE KEY / BEGIN OPENSSH PRIVATE KEY → SSH/SSL 私鑰
password: / 密碼：/ pwd: 後面跟密碼字串 → 明碼密碼
```

---

## .gitignore 範本

```gitignore
# === Secrets（絕對不准進 git）===
.env
.env.*
!.env.example
*.key
*.pem
*.p12
*.pfx
id_rsa
id_ed25519
ssh-key-*
*-credentials.json
service-account*.json

# === 機密目錄 ===
_secrets/
private/
01-dev/0-run.md
01-dev/10-deploy-docs/
01-dev/9-talk.md

# === Build 產物 ===
node_modules/
dist/
build/
.next/
out/
.cache/
.vite/
.turbo/
.svelte-kit/

# === Database（production data）===
*.sqlite
*.sqlite3
*.db
!**/seed.sqlite
!**/schema.sqlite

# === Logs ===
*.log
logs/
npm-debug.log*

# === OS / IDE ===
.DS_Store
Thumbs.db
._*
.vscode/*
!.vscode/extensions.json
.idea/
*.swp
*.swo

# === 暫存 ===
tmp/
temp/
*.tmp
.scratch/
.gstack/
```

---

## 新專案第一天 checklist

```
□ git init 後第一件事：建 .gitignore（從上面範本貼）
□ 建 _secrets/ 或 private/ 目錄，加進 .gitignore
□ 寫 .env.example（值全用 placeholder）
□ 第一次 commit 前跑 secret 掃描
□ 確認 GitHub repo → Settings → Code security → Secret scanning + Push protection 都開啟
```

---

## 如果不小心 commit 了 secret

**第一原則：token / 密碼當作「已洩漏」，立刻 revoke + rotate。**

### 還沒 push（只在本地）

```bash
# 1. stash working tree
git stash push -u -m "pre-cleanup"

# 2. 從 history 移除檔案
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch <你要移除的檔案路徑>' \
  --prune-empty --tag-name-filter cat -- --all

# 3. 清 filter-branch 備份
rm -rf .git/refs/original/
rm -f .git/refs/stash .git/logs/refs/stash

# 4. 清 reflog + GC
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 5. 驗證 token 真的不見了
grep -r "<token 字串>" .git 2>/dev/null && echo "❌ 還在" || echo "✅ 乾淨"

# 6. 加 .gitignore
echo "<檔名>" >> .gitignore
git add .gitignore
git commit -m "security: gitignore <檔案>"

# 7. 還原 stash
git stash pop
```

### 已經 push 到 GitHub

1. **立刻 revoke + rotate** token / 密碼
2. 跑以上所有步驟
3. `git push --force-with-lease origin <branch>`
4. 通知團隊重新 clone

**⚠️ GitHub「unblock this push」連結不要按** — 那是給誤判用的。

---

## 真實事故記錄（2026-04-10 SurvivalWallet）

用 `git add` 把整個 `01-dev/10-deploy-docs/` 目錄加進去 commit，裡面有真實的 GitHub PAT + aaPanel 帳密。3 小時後 push 時被 GitHub Push Protection 擋下。花了 1 小時救援。

**教訓：**
1. `git add` 前先 `cat` 不確定的檔案（1 秒省 1 小時）
2. `.gitignore` 要擋整個目錄，不能只擋單一檔案
3. 機密目錄命名要明顯（`_secrets/`、`private/`）
4. GitHub Push Protection 不要關掉
5. token 一旦寫進過 `.git/objects` 就當作洩漏，必須 revoke + rotate

---

**最後一句話：寫之前先想「這行如果上 GitHub 我會不會出事？」會出事就放到 `.gitignore` 擋住的目錄裡。**
