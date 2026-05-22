# Git Secrets 規則 — 什麼進 git，什麼不進

> **誰看這份**：你自己（在任何專案 commit 之前），跟任何幫你寫 code 的 AI agent。
> **怎麼用**：複製這個檔到新專案的 `01-dev/git-secrets-rules.md`，並把第 5 節的 `.gitignore` 範本貼進該專案的 `.gitignore`。
> **為什麼有這份**：2026-04-10 在 SurvivalWallet 不小心 commit 了真實的 GitHub PAT + aaPanel 密碼，被 GitHub Push Protection 擋下來，花了一小時 `git filter-branch` 重寫 history 才救回。本文件是那次事故的硬性規則化。

---

## 1. 一行版速查表

| 類型 | 進 git？ |
|---|---|
| 程式碼、SQL schema、設定**範本**（`.env.example`） | ✅ |
| 部署 SOP / 架構圖（**用占位符**寫，不含真實 IP / 帳密） | ✅ |
| README / 文件 / commit message | ✅ |
| `.env`、`secrets.json`、`*.key`、`*.pem` | ❌ **永遠不進** |
| 含**真實**密碼 / token / IP / 帳號的任何 markdown / txt | ❌ **永遠不進** |
| `node_modules/` / `dist/` / `build/` / `.cache/` | ❌ |
| `.DS_Store` / `Thumbs.db` / `._*`（macOS xattr） | ❌ |
| SQLite 的 production 資料 (`*.sqlite`, `*.db`) | ⚠️ 看用途，預設不進 |
| `package-lock.json` / `bun.lock` / `pnpm-lock.yaml` | ✅ **要進**（lockfile 必須鎖版本） |

---

## 2. ❌ 絕對不准進 git 的東西（含具體例子）

### 2.1 認證資訊

任何能讓別人**冒充你身份**的東西：

```
❌ ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx    ← GitHub PAT (ghp_ / ghs_ / gho_)
❌ sk-proj-xxxxxxxxxxxxx                       ← OpenAI API key
❌ sk-ant-xxxxxxxxxxxxx                        ← Anthropic API key
❌ AKIAIOSFODNN7EXAMPLE                        ← AWS access key
❌ password: xxxxxxxx                          ← 明碼密碼
❌ AaBbCc12345==                               ← Cloudflare API token (base64 字串)
❌ -----BEGIN PRIVATE KEY-----                 ← 任何 private key
❌ -----BEGIN OPENSSH PRIVATE KEY-----         ← SSH private key
```

**檢測 pattern**：
- 看到 `ghp_` / `ghs_` / `gho_` 開頭 + 36 字元 → GitHub PAT
- 看到 `sk-` 開頭 → 多半是 LLM API key
- 看到 `AKIA` 開頭 → AWS
- 看到 `BEGIN PRIVATE KEY` / `BEGIN OPENSSH` → SSH/SSL 私鑰
- 看到 `password:` / `密碼：` / `pwd:` 後面跟著像密碼的字串 → 明碼密碼

### 2.2 連線資訊（**配上**帳密就是大洩漏）

單獨一個 IP 不算機密，但**「IP + port + path + 帳號 + 密碼」整套合在一起**就是攻擊者直接登入的路徑。

```
❌ aapanal: https://your-server-ip:port/path
   帳號： xxxxxxxx
   密碼： xxxxxxxx
```

這四行**全部不能進 git**。任何一行單獨可能還好，但放在一起就是完整的 break-in instructions。

### 2.3 .env 系列

```
❌ .env
❌ .env.local
❌ .env.production
❌ .env.development.local
✅ .env.example          ← OK，但只能放 placeholder
```

`.env.example` 範本只能寫：
```
✅ DATABASE_URL=postgres://user:password@localhost:5432/dbname
✅ API_KEY=your_api_key_here
✅ VITE_SYNC_TOKEN=                ← 空值
```

絕對不能寫：
```
❌ VITE_SYNC_TOKEN=sw2026wallet    ← 真實值
```

### 2.4 加密 / 簽章金鑰檔

```
❌ *.key
❌ *.pem
❌ *.p12
❌ *.pfx
❌ id_rsa
❌ id_ed25519
❌ ssh-key-*.key
❌ aws-credentials.json
❌ google-service-account.json
❌ firebase-adminsdk-*.json
```

### 2.5 build 產物 / 暫存

```
❌ node_modules/
❌ dist/
❌ build/
❌ .next/
❌ .cache/
❌ .vite/
❌ .turbo/
❌ *.log
❌ tmp/
```

理由：build 產物可以重新生成，沒必要佔 repo 空間。Lockfile 已經鎖了版本，dependency 可以重裝。

### 2.6 OS / IDE 噪音

```
❌ .DS_Store        ← macOS Finder 的目錄 metadata
❌ Thumbs.db        ← Windows 縮圖快取
❌ ._*              ← macOS AppleDouble (BSD tar 把 xattr 寫進去產生的)
❌ .vscode/         ← 通常每人設定不同 (.vscode/extensions.json 例外可進)
❌ .idea/           ← JetBrains
❌ *.swp / *.swo    ← Vim
```

---

## 3. ✅ 可以進 git 的東西

### 3.1 部署 SOP（**模板版本**）

可以寫部署流程、架構說明，但**所有具體值用占位符**：

```markdown
✅ 1. SSH 進伺服器：
   ```
   ssh -i <你的 SSH key 路徑> ubuntu@<伺服器 IP>
   ```

✅ 2. 路徑：`/www/wwwroot/<你的子域名>`

✅ 3. 改 nginx config 把 root 指向 `<專案路徑>/02-web/dist`
```

不能寫：

```markdown
❌ ssh -i ~/Documents/important\ file/ssh-key-2026-04-08.key ubuntu@137.131.7.230
❌ cd /www/wwwroot/survivalwallet.looptw.com
❌ aapanel: https://137.131.7.230:19262/31ff8ce4
   帳號： xxxxxxxx
   密碼： xxxxxxxx
```

灰色地帶：**IP / 域名單獨**沒有帳密的話可以進 git（畢竟 DNS 是公開的）。但如果你連 admin path 都寫出來（`/19262/31ff8ce4`）就等於把 attack surface 露了，建議當機密處理。

### 3.2 程式碼裡的占位符 / 環境變數讀取

```typescript
✅ const SYNC_TOKEN = import.meta.env.VITE_SYNC_TOKEN || '';
✅ const dbPath = process.env.DATABASE_PATH || './db.sqlite';
```

```php
✅ $PASSWORD = getenv('API_PASSWORD');
```

不能寫：

```php
❌ $PASSWORD = 'xxxxxxxx';
```

### 3.3 假資料 / 測試 fixture

```
✅ test/fixtures/sample-user.json   { "email": "test@example.com", "name": "Test" }
✅ db/seed.sql                       INSERT INTO users VALUES ('demo', 'demo123');
```

只要明確是 fake / demo / sample 資料就 OK。

### 3.4 Lockfile（**必須**進）

```
✅ package-lock.json
✅ pnpm-lock.yaml
✅ yarn.lock
✅ bun.lock
✅ Gemfile.lock
✅ poetry.lock
✅ Cargo.lock
```

理由：lockfile 鎖死整個 dependency 樹的版本，確保每個人裝出來的東西完全一樣。沒有 lockfile = supply chain attack 的破口。

---

## 4. ⚠️ 灰色地帶

### 4.1 SQLite production 資料

| 情境 | 進 git？ |
|---|---|
| 空 schema (`schema.sql`) | ✅ |
| Demo seed 資料 | ✅ |
| 開發階段個人測試資料 | ⚠️ 可以但不建議（會跟其他人衝突） |
| 真正使用者的資料 | ❌ **絕對不行**（個資 + 跟 prod 衝突） |

SurvivalWallet 的 `02-web/database/survival_wallet.sqlite` 在開發階段被 commit 過，**這是 anti-pattern**。Production 資料應該只存在 server 上，不應該進 git。本機開發時應該用 `.gitignore` 加 `*.sqlite`，每個 dev 自己 seed 一份。

### 4.2 部署架構文件

| 內容 | 進 git？ |
|---|---|
| 「我們用 Vite + PHP + nginx」 | ✅ |
| 「nginx 設定範本（用 `<DOMAIN>` 占位）」 | ✅ |
| 「Cloudflare DNS 操作步驟（截圖示範）」 | ✅ |
| 「IP 137.131.7.230 + aaPanel 帳密」 | ❌ |

**判斷標準**：如果這份文件**對 attacker 有用**就不能進。對其他工程師有用、對 attacker 沒用就可以進。

### 4.3 內部討論 / 草稿筆記

例如 `9-talk.md`、`scratch.md`、`TODO.md`：

| 內容 | 進 git？ |
|---|---|
| 「下次要做的功能列表」 | ✅ |
| 「跟客戶談的會議紀要」 | ⚠️ 看內容 |
| 「給 Claude 跑的指令暫存區」 | ⚠️ 通常不需要，是 transient |
| 「寫滿真實帳密的 SOP」 | ❌ |

**SurvivalWallet 的 `01-dev/9-talk.md` 在這份文件寫成時是用來交換指令的暫存區，理論上應該加 `.gitignore`。**

---

## 5. `.gitignore` 範本（複製到任何新專案）

```gitignore
# === Secrets (絕對不准進 git) ===
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

# === 機密文件 ===
01-dev/0-run.md                  # 個人部署 cheatsheet（含明碼密碼）
01-dev/10-deploy-docs/           # 部署 SOP（含真實 IP / 帳密）
01-dev/9-talk.md                 # AI 對話暫存區（可能暫存敏感指令）
secrets/
private/

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

# === Database (production data) ===
*.sqlite
*.sqlite3
*.db
!**/seed.sqlite                  # 例外：明確命名的 seed 檔可以進
!**/schema.sqlite                # 例外：schema-only 可以進

# === Logs ===
*.log
logs/
npm-debug.log*
yarn-debug.log*
pnpm-debug.log*

# === OS / IDE 噪音 ===
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

# === Survival Wallet 特定 ===
survival-wallet-dist.zip
.gstack/                          # gstack 工具的 local artifacts
```

---

## 6. 提交前的 30 秒安全檢查

每次 `git add` 之後、`git commit` 之前，跑這個：

```bash
# 1. 看 staged 清單，肉眼掃過一次
git diff --cached --stat

# 2. 用 grep 掃 staged 內容找常見 secret pattern
git diff --cached | grep -iE "(password|密碼|secret|token|api[_-]?key|ghp_|ghs_|sk-|AKIA|BEGIN [A-Z ]+PRIVATE KEY)"

# 3. 如果上面有 hit → STOP，先處理再 commit
```

可以包成一個 alias 或 pre-commit hook。最簡單的版本：

```bash
# ~/.bashrc 或 ~/.zshrc
alias gck='git diff --cached | grep -iE "(password|密碼|secret|token|api[_-]?key|ghp_|ghs_|sk-|AKIA|BEGIN [A-Z ]+PRIVATE KEY)" && echo "⚠️ 偵測到可能的 secret，commit 前請確認！" || echo "✅ staged diff 看起來乾淨"'
```

---

## 7. 如果不小心 commit 進去了，怎麼救

**第一原則：把 token / 密碼當作「已洩漏」處理，立刻 revoke + rotate。**

不管你後面怎麼清 git history、就算 push 失敗、就算你 30 秒內就發現 — 該 token 已經寫進過你的本地 `.git/objects/`，可能被 IDE 索引器 / Time Machine / Spotlight / 雲端備份抓走。**這個東西已經死了，別救它，砍掉換新的。**

### 7.1 還沒 push（檔案已 commit 但沒到 remote）

```bash
# 場景：剛 commit 完發現有 secret，還沒 push
# 用 git filter-branch 把含有機密的檔案從 history 移除
# 注意：所有 commit hash 會變

# 1. 先把 working tree 上的改動 stash 起來（不然 filter-branch 會拒絕跑）
git stash push -u -m "pre-cleanup"

# 2. filter-branch — 把指定檔案從整個 history 移除
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch <你要移除的檔案路徑>' \
  --prune-empty --tag-name-filter cat -- --all

# 3. 清掉 filter-branch 留下的備份 ref
rm -rf .git/refs/original/

# 4. 如果有 stash 也被 filter-branch 弄壞了，直接刪
rm -f .git/refs/stash .git/logs/refs/stash

# 5. expire reflog + GC，把 dangling object 從 .git/objects 踢出去
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 6. 加 .gitignore 防止再被加回來
echo "<你要排除的檔案路徑>" >> .gitignore
git add .gitignore
git commit -m "security: gitignore <檔案>"

# 7. 暴力 verify token 真的不在 .git 任何地方
grep -r "<token 字串>" .git 2>/dev/null && echo "❌ 還在" || echo "✅ 乾淨"

# 8. 再把原本 stash 的東西救回來（如果 stash 沒爛）
git stash list
git stash pop  # 失敗的話手動處理 working tree
```

### 7.2 已經 push 到 GitHub

如果是 GitHub 的 secret scanning（PAT、AWS、OpenAI、Anthropic 之類）會自動通知你。**你還是要做 7.1 的所有步驟**，再加：

- **立刻 revoke + rotate** 該 token / 密碼（這是最重要的）
- 跟團隊講有人 force-push 了，要他們重新 clone 或硬重置
- `git push --force-with-lease origin <branch>` 把乾淨的歷史推上去
- 跟 GitHub support 寫信請他們也清 cache（PR 跟 issue 裡引用過的 commit hash 會殘留）

### 7.3 GitHub 的 unblock URL（**不要用**）

GitHub 偵測到 secret 時會給你一個 "unblock this push" 連結，按下去就能強推。**這是給「誤判」的逃生口，不是給你用的**。如果是真的 secret 千萬別按 — 一旦推上去，secret 就會被各種 fork / archive / 第三方掃描器吸走，永遠收不回來。

---

## 8. 真實案例：SurvivalWallet 2026-04-10 的事故

**事發**：跑 `/qa` 修了一些 bug 之後要 commit。當下 working tree 有「待 commit 的 sqlite 改動」+「使用者預先放進去的 `01-dev/10-deploy-docs/` 整個目錄」。為了讓 working tree 乾淨好開始 QA，我用 `git add` 把整個目錄加進去 commit 了。

**錯在哪**：
1. 沒看內容就 `git add`。`01-dev/10-deploy-docs/0-run.md` 第 250 行有一個真實的 GitHub PAT，第 240-242 行有 aaPanel 帳號 + 明碼密碼。
2. 諷刺的是該檔案 line 10 自己寫了「**本文件底部有敏感資訊（密碼、SSH key、GitHub token），絕對不要在回覆中引用或顯示這些內容**」 — 但這個警告只給 AI 看，沒有反映到 `.gitignore`。
3. 該專案的 `.gitignore` 已經有 `01-dev/0-run.md`（單一檔），但沒有 `01-dev/10-deploy-docs/`（整個目錄）。**.gitignore 應該保護整個敏感目錄，不能只擋一個檔。**

**怎麼被抓到**：3 小時後要 `git push origin main`，GitHub Push Protection 的 secret scanning 偵測到 `ghp_` 開頭的字串，**直接拒絕推送**。

**救援花了多久**：約 1 小時。動作清單：
1. `git stash` 暫存 working tree
2. `git filter-branch` 把 4 個 deploy-docs 檔案從整個 history 移除（25 個 commit hash 全部改變）
3. 刪掉 `refs/original/` + `refs/stash`（filter-branch 弄壞的）
4. `git reflog expire --expire=now --all` + `git gc --prune=now --aggressive` 清乾淨 `.git/objects`
5. 暴力 `grep -r "ghp_..." .git/` 確認真的清掉
6. 加 `01-dev/10-deploy-docs/` 到 `.gitignore`
7. 重新 push（這次 secret scanning 通過）

**外加必須做的事（這個還沒救完就完蛋）**：
- Revoke GitHub PAT
- 改 aaPanel 帳號的密碼
- 檢查本地 deploy-docs/0-run.md 也要把那幾行明文機密刪掉（git 已不追蹤，但檔案還在硬碟）

**這件事教會的事**（按重要性排）：
1. **`git add` 之前先 `cat` 一下你不確定的檔案**。1 秒鐘的 cat，省 1 小時的 filter-branch。
2. **`.gitignore` 寧可大方一點**。整個 `deploy-docs/` 都擋掉，比擋單一檔案更安全 — 未來新增檔案會自動被擋。
3. **「機密目錄」應該長得像機密目錄**。命名 `01-dev/10-deploy-docs/` 看起來像普通文件，沒人會警覺。改名 `01-dev/_secrets/` 或 `private/deploy/` 一眼就知道別碰。
4. **GitHub Push Protection 救了我一次**。沒它的話 token 就上 GitHub 了。**不要關掉這個功能**，它是最後一道防線。
5. **token 一旦寫進過 `.git/objects` 就當作洩漏了**。git 再乾淨也救不了，必須 revoke + rotate。

---

## 9. 新專案 checklist（建 repo 第一天就做完）

- [ ] `git init` 之後**第一件事**：建 `.gitignore`，從本文件第 5 節範本貼進去
- [ ] 確認 `.gitignore` 有排除：`.env`、`*.key`、`*.pem`、`*.sqlite`、`node_modules/`、`dist/`、機密目錄
- [ ] 建一個 `_secrets/` 或 `private/` 目錄專門放機密檔案，並加進 `.gitignore`
- [ ] 寫個 `.env.example` 列出所有需要的環境變數，但**值都用 placeholder**
- [ ] 第一次 `git commit` 之前跑：`git diff --cached | grep -iE "(password|token|secret|ghp_|sk-)"` 確認沒漏網之魚
- [ ] 確認 GitHub repo 的 Settings → Code security → **Secret scanning + Push protection 都開啟**
- [ ] （可選）裝 [git-secrets](https://github.com/awslabs/git-secrets) 或 [gitleaks](https://github.com/gitleaks/gitleaks) 做 pre-commit 自動檢查

---

**最後一句話**：你寫的每一行 markdown / 設定檔都會有人（或 AI agent）幫你 commit。**寫之前先想一秒：「這行如果上 GitHub 我會不會出事？」** 會出事就放到 `.gitignore` 擋住的目錄裡，不要靠記性，記性會壞。
