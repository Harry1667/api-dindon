# 🚀 通用網站部署 SOP

> 任何 Git 專案 → VPS（aaPanel + PM2 + Nginx + Cloudflare）
> 涵蓋 4 種專案類型 + 常見地雷

**適用：** macOS 開發 + Ubuntu 24.04 ARM/x64 伺服器 + Node 20+/24+ + PM2 6+ + aaPanel

---

## 目錄

- [0. 用這份 SOP 之前](#0-用這份-sop-之前)
- [1. 專案類型矩陣](#1-專案類型矩陣)
- [Phase A：伺服器一次性設定](#phase-a伺服器一次性設定)
- [Phase B：專案結構檢查](#phase-b專案結構檢查)
- [Phase C：Cloudflare DNS + SSL](#phase-ccloudflare-dns--ssl)
- [Phase D：第一次部署（4 條分支）](#phase-d第一次部署4-條分支)
- [Phase E：後續更新](#phase-e後續更新)
- [Phase F：常見錯誤排除](#phase-f常見錯誤排除)
- [Phase G：回滾策略](#phase-g回滾策略)
- [附錄 A：常見地雷清單](#附錄-a常見地雷清單)
- [附錄 B：環境變數位置 cheatsheet](#附錄-b環境變數位置-cheatsheet)
- [附錄 C：PM2 指令對照](#附錄-cpm2-指令對照)
- [附錄 D：通用一鍵部署 script](#附錄-d通用一鍵部署-script)

---

## 0. 用這份 SOP 之前

### 你需要的東西

| 項目 | 說明 |
|---|---|
| Mac/Linux terminal + ssh key | 用 `ssh -i <key> user@host` 連伺服器 |
| VPS 伺服器（IP + sudo 權限） | Oracle Cloud / Linode / DigitalOcean 等都可 |
| aaPanel 後台 | 瀏覽器登入 |
| Cloudflare 帳號 + 主域名 | DNS 管理 |
| 專案 Git repo | GitHub / GitLab / Bitbucket |

### ssh 連線範本

```bash
ssh -i ~/path/to/your-ssh-key user@<SERVER_IP>
sudo su   # 切 root（aaPanel 站點目錄需要）
```

> **建議：** 把連線指令存成 shell alias 或 `~/.ssh/config`，避免每次打長指令。

---

## 1. 專案類型矩陣

**先判斷你的專案屬於哪一類，再走對應的部署路徑。**

| 類型 | 特徵 | 部署路徑 |
|---|---|---|
| **A. 純 Next.js** | 一個 Next.js app，前後端一體，無本地檔案儲存 | git pull |
| **B. SPA + Node backend** | 前端 Vite/CRA + 後端獨立 Express，可能含 SQLite | git pull 或 tarball |
| **C. 純前端 SPA** | 只有前端，build 出靜態檔，後端打外部 API | nginx serve dist/ |
| **D. 含副服務** | 主應用 + Python uvicorn / Worker / Cron | git pull + 多 PM2 |

### 怎麼判斷？

```bash
# 在專案根目錄跑
ls package.json next.config.* vite.config.* server.mjs server.js *.proto 2>/dev/null
ls **/venv 2>/dev/null
grep -l "sqlite\|leveldb\|local-db" package.json 2>/dev/null
```

| 看到什麼 | 是哪一類 |
|---|---|
| `next.config.*`，沒 server.mjs/server.js | A |
| `vite.config.*` + `server.mjs` 之類獨立 backend | B |
| 只有 `vite.config.*` | C |
| 有 `venv/` 或 Python 檔案 | D |
| `package.json` 有 sqlite/leveldb | B/D（有狀態） |

---

## Phase A：伺服器一次性設定

**這段每台新伺服器只跑一次。** 不要每次部署都做。

### A.1 安裝 Node（用 nvm，避免系統 Node）

```bash
# 安裝 nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
source ~/.bashrc

# 裝 LTS Node
nvm install --lts
nvm use --lts
nvm alias default node

# 確認
node -v
which node
# 應該是 .../nvm/versions/node/vXX.x.x/bin/node
# ❌ 不應該是 /usr/bin/node（系統 Node 會跟 nvm 衝突）
```

### A.2 解掉 nvm + .npmrc 衝突 ⚠️ 必做

aaPanel 預設裝的 npm 會在 `~/.npmrc` 寫 `prefix=` 跟 `globalconfig=`，**這跟 nvm 不相容**，會導致 PM2 用錯 Node 找不到 node_modules。

```bash
# 看 .npmrc
cat ~/.npmrc

# 如果有 prefix= 或 globalconfig=，解掉
nvm use --delete-prefix $(node -v) --silent
# 或直接刪除衝突行
sed -i '/^prefix=/d; /^globalconfig=/d' ~/.npmrc
```

### A.3 全域裝 PM2

```bash
which npm   # 確認指向 nvm 路徑
npm install -g pm2

# 確認 pm2 也是 nvm 的
which pm2
```

### A.4 設定 PM2 開機自啟

```bash
pm2 startup
# ↑ 會印出一行類似：
#   sudo env PATH=$PATH:/nvm/.../bin pm2 startup systemd -u root --hp /root
# ⚠️ 必須複製貼上跑那行指令！pm2 startup 自己不會幫你做
```

### A.5 安裝其他系統工具

```bash
apt update
apt install -y git build-essential python3-pip
# build-essential：sqlite3 等 native 套件編譯需要
# python3-pip：如果有 Python 副服務需要
```

### A.6 站點根目錄

```bash
mkdir -p /www/wwwroot
chown root:root /www/wwwroot
```

---

## Phase B：專案結構檢查

每個新專案都要確認以下幾點。

### B.1 .gitignore 必備項目

```gitignore
# Node.js
node_modules/
.next/
dist/
build/
out/
*.tsbuildinfo

# 環境變數（含密鑰）
.env
.env.local
.env.*.local
*.env.local

# 資料庫 / 本地檔案儲存
*.sqlite
*.sqlite3
*.db
uploads/
data/

# macOS / Windows
.DS_Store
Thumbs.db

# 編輯器
.vscode/
.idea/
*.swp

# 日誌
*.log
npm-debug.log*

# Python（如有副服務）
__pycache__/
*.pyc
venv/
.venv/

# 部署相關（含 SSH 細節）
deploy.config
dist-aapanel/
```

### B.2 確認沒有敏感檔被追蹤

```bash
git ls-files | grep -E '\.env$|\.env\.local|key$|pem$|sqlite$|\.db$'
# 應該完全沒有輸出
```

### B.3 如果不小心 commit 了敏感檔

```bash
git rm --cached <檔名>
echo "<檔名>" >> .gitignore
git add .gitignore
git commit -m "chore: remove sensitive file"
git push

# ⚠️ 如果是密鑰，立刻去服務商後台撤銷重生
```

### B.4 必有檔案

```
專案根目錄/
├── .gitignore                  ← 必要
├── README.md                   ← 怎麼啟動
├── package.json
├── package-lock.json           ← 必要，鎖定版本
├── .env.example                ← 環境變數範本（值留空）
└── src/ 或 app 目錄
```

---

## Phase C：Cloudflare DNS + SSL

### C.1 加 DNS 記錄

1. 登入 Cloudflare → 你的主域名
2. **DNS** → **新增記錄**
3. 填入：
   - 類型：`A`
   - 名稱：子域名（例如 `app`）
   - IPv4：你的伺服器 IP
   - **Proxy 狀態：灰色雲朵（DNS Only）** ← 重要！
   - TTL：自動

### C.2 灰雲 vs 橘雲（決定 SSL 來源）

| 雲朵 | SSL 來源 | 適用 |
|---|---|---|
| **灰雲（DNS Only）** | Let's Encrypt（aaPanel 申請） | 一般情況，推薦 |
| **橘雲（Proxied）** | Cloudflare Origin Cert | 要 Cloudflare CDN/防火牆 |

**不能混用。** 灰雲配 Let's Encrypt，橘雲配 Origin Cert。搞錯會 SSL handshake 失敗。

### C.3 等 DNS 生效

```bash
# 在本機跑
ping <子域名>.<主域名>
# 看到正確 IP 就 OK，1-5 分鐘
```

---

## Phase D：第一次部署（4 條分支）

**先讀 Phase A 確認伺服器設定 OK，然後選你的專案類型對應的分支。**

### 共通：上 SSH 並 clone

```bash
ssh -i <ssh-key> user@<server-ip>
sudo su

# 第一次 clone 前，先設 git safe.directory
git config --global --add safe.directory /www/wwwroot/<專案>.<域名>

cd /www/wwwroot/

# 公開 repo
git clone https://github.com/<帳號>/<repo>.git <專案>.<域名>
# 私有 repo：伺服器裝了 gh 就 `gh repo clone <帳號>/<repo> <專案>.<域名>`，
# 否則用 token：`git clone https://<帳號>:<TOKEN>@github.com/<帳號>/<repo>.git ...`（用完清掉）
cd <專案>.<域名>
```

> 💡 本機建立並推上 GitHub 建議用 gh CLI（取代手動在網頁建 repo）：
> ```bash
> gh auth status
> gh repo create <repo> --private --source=. --remote=origin --push
> ```

---

### 🔵 路徑 A：純 Next.js

```bash
cd <app-dir>   # 你的 Next.js 目錄

# 安裝依賴
npm install

# 建立 .env.local
nano .env.local
# 貼上所有環境變數
chmod 600 .env.local

# 建置
npm run build

# 啟動 PM2（注意 --interpreter）
pm2 start npm \
  --name <project>-web \
  --interpreter $(which node) \
  --cwd $(pwd) \
  -- start

pm2 save

# 驗證
sleep 2
pm2 list
pm2 logs <project>-web --lines 20 --nostream
curl -I http://127.0.0.1:3000
```

接著 **Phase D.5** 設 Nginx。

---

### 🟢 路徑 B：SPA + Node backend

例如 Vite 前端 + Express 後端，可能含 SQLite。

```bash
cd <app-dir>

# 安裝依賴
npm install --omit=dev

# .env 位置：注意！server 程式可能讀的位置不一樣
# 確認 server 程式裡 dotenv 怎麼讀
grep -n "envPath\|\.env\|dotenv" server.mjs server.js 2>/dev/null

# 建立 .env 在 server 程式期望的位置
nano .env   # 或 ../.env，看程式怎麼讀
chmod 600 .env

# 建置前端
npm run build
ls dist/   # 確認有東西

# 啟動 PM2
pm2 start server.mjs \
  --name <project>-web \
  --interpreter $(which node) \
  --cwd $(pwd)

pm2 save

# 驗證
sleep 2
pm2 list
pm2 logs <project>-web --lines 20 --nostream
curl -I http://127.0.0.1:3001
```

接著 **Phase D.5** 設 Nginx，proxy_pass 指向 backend port。

---

### 🟡 路徑 C：純前端 SPA（不需 PM2）

例如 landing page、文件站。

```bash
cd <app-dir>
npm install
npm run build
ls dist/   # 或 build/
```

**這類專案不用 PM2，aaPanel 直接 serve 靜態檔。Phase D.5 用「靜態站點」設定。**

---

### 🟣 路徑 D：含 Python/副服務（多 PM2 process）

```bash
# 1. 主應用先按路徑 A/B 部署起來

# 2. 副服務：Python venv
cd /www/wwwroot/<專案>/<python-subdir>
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. PM2 啟動 Python 服務
pm2 start ./venv/bin/python \
  --name <project>-bridge \
  --cwd $(pwd) \
  --interpreter none \
  -- -m uvicorn server:app --host 127.0.0.1 --port 8765

pm2 save

# 4. 驗證
pm2 list
curl -I http://127.0.0.1:8765
```

> **`--interpreter none`** 很重要：告訴 PM2「這不是 Node script，直接 exec」。

---

### Phase D.5 — aaPanel Nginx 反向代理（A/B/D 共用）

1. aaPanel 後台 → **網站** → **添加站點**
2. 填：
   - 域名：`<專案>.<域名>`
   - 根目錄：`/www/wwwroot/<專案>.<域名>`
   - PHP：純靜態
3. 儲存後 → 點站點名 → **配置文件**
4. 把 `location /` 改成：

```nginx
location / {
    proxy_pass http://127.0.0.1:3000;   # 改成你的 backend port
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # SSE / 串流支援
    proxy_buffering off;
    proxy_cache off;

    # 大檔上傳
    client_max_body_size 50M;
}

# 防爬隱藏檔（.env、.git）
location ~ /\. {
    deny all;
    return 404;
}
```

5. 儲存
6. **SSL** → **Let's Encrypt** → 申請憑證 → 開啟「強制 HTTPS」

> **路徑 C 差別：** 不要設 reverse proxy，直接設「網站根目錄」指向 `dist/` 或 `build/`。

### Phase D.6 — 從外部驗證

```bash
# 在本機
curl -I https://<子域名>.<域名>
# 應該回 200 / 301 / 307

# 開瀏覽器訪問
```

---

## Phase E：後續更新

### E.1 git pull 模式（推薦給 A/D）

**前提：** 專案沒有本地檔案需要保留。

```bash
# 本機 push
git add .
git commit -m "feat: 你的修改"
git push

# 伺服器
ssh ...
sudo su
cd /www/wwwroot/<專案>.<域名>
git pull
cd <app-dir>
npm install --omit=dev   # 有新依賴才需要
npm run build
pm2 restart <project>-web --update-env   # ⚠️ --update-env 才會重讀 .env
pm2 logs <project>-web --lines 20 --nostream
```

### E.2 tarball 模式（推薦給 B 含 SQLite，或想避開 server build）

```bash
# 本機
cd <project>
npm run build
mkdir -p dist-deploy
cp -R <app-dir>/dist <app-dir>/server.mjs <app-dir>/package.json <app-dir>/package-lock.json dist-deploy/
COPYFILE_DISABLE=1 tar --no-xattrs -czf <project>-$(date +%Y%m%d).tar.gz dist-deploy

# 上傳
scp -i <ssh-key> <project>-*.tar.gz user@<server-ip>:/tmp/

# 伺服器
ssh ...
sudo su
cd /www/wwwroot/<專案>.<域名>

# 備份目前
mv <app-dir> <app-dir>.backup-$(date +%Y%m%d-%H%M)

# 解壓新版
mkdir -p .deploy-tmp
tar -xzf /tmp/<project>-*.tar.gz -C .deploy-tmp
mv .deploy-tmp/dist-deploy <app-dir>

# 復用 backup 的 node_modules
cp -R <app-dir>.backup-*/node_modules <app-dir>/node_modules 2>/dev/null

# 復用 backup 的資料檔（重要！）
cp <app-dir>.backup-*/src/database/*.sqlite <app-dir>/src/database/ 2>/dev/null

rm -rf .deploy-tmp /tmp/<project>-*.tar.gz

# 確認 .env 還在
ls -la .env || ls -la <app-dir>/.env

# 重啟
pm2 restart <project>-web --update-env
```

### E.3 哪個模式選哪個？

| 情境 | 推薦 |
|---|---|
| 純 Next.js / 無狀態 | git pull |
| 含 SQLite / uploads/ | tarball |
| 想避開伺服器跑 build | tarball |
| 多人協作 / CI/CD | git pull |
| 個人專案、想清楚的 backup | tarball |

---

## Phase F：常見錯誤排除

### F.1 Node / PM2 環境

#### ❌ `Cannot find package 'express'`（明明裝了）

**原因：** PM2 daemon 用錯 Node（系統 Node 而非 nvm Node），找不到 node_modules。

**解法：**
```bash
# 1. 確認 which node 是 nvm 路徑
which node

# 2. 完全砍掉 PM2 daemon
pm2 kill

# 3. 重啟 process，加 --interpreter
cd /www/wwwroot/<專案>/<app-dir>
pm2 start <script> --name <name> --interpreter $(which node) --cwd $(pwd)
pm2 save
```

#### ❌ PM2 ↺ 重啟次數爆增（800+）

**原因 1：** 兩個 PM2 process 跑同一支程式搶 port。
```bash
pm2 list
# 看有沒有重複 name（如 myapp + myapp-web）
pm2 delete <重複的 name>
```

**原因 2：** server crash loop。
```bash
pm2 stop <name>
cd <app-dir>
timeout 5 node server.mjs   # 直接跑看完整錯誤
```

#### ❌ `pm2 restart` 後 .env 改動沒生效

**解法：** 必加 `--update-env`：
```bash
pm2 restart <name> --update-env
```

#### ❌ `npmrc/nvm incompatible` 警告

見 Phase A.2。

### F.2 Build 相關

#### ❌ ARM 上 `npm install` 卡很久

`sqlite3`、`sharp`、`bcrypt` 等 native binding 在 ARM 上要編譯，第一次可能 5-10 分鐘。**正常現象。** 之後復用 backup 的 node_modules 就快了。

#### ❌ `ERR_MODULE_NOT_FOUND`

```bash
ls node_modules/<missing-package>
# 沒有 → 跑 npm install
# 有 → PM2 用錯 Node，看 F.1
```

#### ❌ TypeScript build 失敗

本機修好再 push。**不要在伺服器上改 code。**

### F.3 路由 / 服務相關

#### ❌ POST 某個路由回 404 「Cannot POST /api/xxx」

代表 Express 沒註冊那個路由。可能原因：
1. 部署的 server 不是最新版 → `grep -c "<route>" server.mjs` 確認
2. PM2 跑的是舊 process → `pm2 delete <name> && pm2 start ...`
3. server 在註冊路由前 throw → 用 `node server.mjs` 直接跑看

#### ❌ 502 Bad Gateway

```bash
pm2 logs <name> --lines 50
# 看 backend 有沒有啟動
# 通常是 build 沒成功或 port 沒對到
```

### F.4 前端 / 快取

#### ❌ 改完 code 線上沒變化

**5 個常見原因（按機率）：**
1. `git pull` 沒成功 → 看輸出有沒有 `Updating xxx..yyy`
2. `npm run build` 失敗 → 要看到 `✓ built` 或 `✓ Compiled`
3. `pm2 restart` 沒跑 → `pm2 list` 看 ↺ 有沒有 +1
4. **PWA service worker 卡舊版**（最常忽略）→ Hard refresh `Cmd+Shift+R`
5. Cloudflare CDN 快取（橘雲時）→ Cloudflare 後台 Purge Cache

#### ❌ PWA 一直顯示舊版

```js
// sw.js 內每次 build 改 CACHE_NAME
const CACHE_NAME = 'app-v3';   // ← bump 版本

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});
```

### F.5 權限 / 環境

#### ❌ tar 解壓後檔案 owner 是 macOS UID（如 `501:staff`）

```bash
chown -R root:root /www/wwwroot/<專案>/<app-dir>
```

打包時加 `--no-xattrs` + `COPYFILE_DISABLE=1` 避免：
```bash
COPYFILE_DISABLE=1 tar --no-xattrs -czf out.tar.gz <dir>
```

#### ❌ `.env` 在錯誤位置

不同專案讀 `.env` 的位置不一樣，**讀 server 程式碼確認**：
```bash
grep -n "envPath\|\.env\|dotenv" server.mjs server.js 2>/dev/null
```

常見模式：
- `dotenv.config()` → 讀當前目錄的 `.env`
- `readFileSync(join(__dirname, '..', '.env'))` → 讀**上一層**的 `.env`

#### ❌ `fatal: detected dubious ownership in repository`

```bash
git config --global --add safe.directory /www/wwwroot/<專案>
```

### F.6 SSL / Cloudflare

#### ❌ 灰雲配 Origin Cert / 橘雲配 Let's Encrypt

混用會 SSL handshake 錯誤。改回對應的組合（見 Phase C.2）。

#### ❌ Cloudflare 一直回 521/522

521 = Origin 沒回應，522 = 連線 timeout。
- 確認 PM2 process online
- 確認 Nginx config 對的 port
- 確認 VPS 防火牆允許 80/443

---

## Phase G：回滾策略

### G.1 git pull 模式回滾

```bash
cd /www/wwwroot/<專案>

# 推薦：用 git revert（保留歷史）
git log --oneline -5
git revert <bad-commit>

# 緊急：硬退
git reset --hard HEAD~1   # ⚠️ 會丟掉所有 uncommitted 改動

cd <app-dir>
npm run build
pm2 restart <name> --update-env
```

### G.2 tarball 模式回滾

```bash
cd /www/wwwroot/<專案>
ls <app-dir>.backup-*

pm2 stop <name>
rm -rf <app-dir>
mv <app-dir>.backup-<日期>-<時間> <app-dir>
pm2 start <name>

pm2 logs <name> --lines 20 --nostream
```

### G.3 最壞情況：完全重建

```bash
pm2 delete <name>
cd /www/wwwroot
rm -rf <專案>
# 重跑 Phase D
```

---

## 附錄 A：常見地雷清單

按踩雷機率排序，部署前先檢查。

### A.1 PM2 daemon 用錯 Node

**症狀：** `npm install` 成功，但 PM2 啟動 server 噴 `Cannot find package 'xxx'`
**原因：** PM2 daemon 還用系統 Node，看不到 nvm 的 node_modules
**修法：** `pm2 kill` + `pm2 start --interpreter $(which node)`
**預防：** 永遠用 alias `pm2start='pm2 start --interpreter $(which node)'`

### A.2 npmrc 跟 nvm 衝突

**症狀：** ssh 進去看到警告 `Your user's .npmrc has globalconfig/prefix incompatible with nvm`
**原因：** aaPanel 預設裝的 npm 寫了 prefix
**修法：** Phase A.2

### A.3 PM2 同名 process 重複（搶 port → crash loop）

**症狀：** `pm2 list` 有 myapp 跟 myapp-web 都跑同一支程式
**原因：** 不小心 `pm2 start` 兩次用不同 name
**修法：** `pm2 delete` 重複的那個
**預防：** 每次 deploy 前 `pm2 list` 確認

### A.4 .env 位置錯誤

**症狀：** server 啟動成功但讀不到設定
**原因：** server 讀的是 `../env`（上一層），但你建在當前目錄
**修法：** `grep envPath server.mjs` 確認位置

### A.5 PWA Service Worker 卡舊版

**症狀：** 部署完前端，但用戶看到的還是舊 UI
**原因：** sw.js 還在 serve 舊 cache
**修法：** Hard refresh + bump CACHE_NAME

### A.6 macOS tar 帶 UID 501 / xattr 噪音

**症狀：** 解壓出的目錄 owner 是 `501:staff`
**修法：** `chown -R root:root` + 打包時用 `COPYFILE_DISABLE=1 tar --no-xattrs`

### A.7 tarball 解壓散落到當前目錄

**症狀：** 解壓後檔案散落到 cwd
**原因：** tarball 沒外層 wrapper 目錄
**修法：** 打包時加 wrapper：`tar -czf x.tar.gz <wrapper>/`

### A.8 `npm install --omit=dev` 漏跑

**症狀：** server 找不到任何 production 依賴
**修法：** 加進部署 script 必跑

### A.9 Vite v8 (Rolldown) 破壞 KaTeX 之類含 Unicode escape 的套件

**症狀：** KaTeX `\frac` 變成 `\f rac`
**原因：** Rolldown 把 `\uD800-\uDFFF` 展開成 lone surrogates → UTF-8 替換成 U+FFFD
**修法：** 降版 vite 到 v7（用 Rollup）

---

## 附錄 B：環境變數位置 cheatsheet

| 框架 | 預設讀取位置 | 備註 |
|---|---|---|
| Next.js | `.env.local` 在專案根 | 自動讀 |
| Vite | `.env`、`.env.local` 在專案根 | 只有 `VITE_` 開頭會 expose 到前端 |
| Express + dotenv | `.env` 在 `__dirname`（看程式碼） | 手動 `dotenv.config()` |
| 自訂 readFileSync | 看程式碼，可能讀上層 | 例如 `readFileSync('../.env')` |

**規則：永遠先看 server 程式碼怎麼讀，不要猜。**

---

## 附錄 C：PM2 指令對照

| 用途 | 指令 |
|---|---|
| 啟動 | `pm2 start <script> --name <name> --interpreter $(which node) --cwd $(pwd)` |
| 重啟 | `pm2 restart <name> --update-env` |
| 砍掉 process | `pm2 delete <name>` |
| 砍掉整個 daemon | `pm2 kill` |
| 列表 | `pm2 list` |
| 看詳情 | `pm2 show <name>` |
| 看 log（持續） | `pm2 logs <name>` |
| 看 log（一次） | `pm2 logs <name> --lines 20 --nostream` |
| 看 log（只 error） | `pm2 logs <name> --err` |
| 即時 monitor | `pm2 monit` |
| 存目前設定 | `pm2 save` |
| 從備份還原 | `pm2 resurrect` |
| 開機自啟 | `pm2 startup`（要再跑印出來那行） |
| 清 log | `pm2 flush` |

---

## 附錄 D：通用一鍵部署 script

存成 `~/deploy.sh`，每個專案改前 5 行：

```bash
#!/bin/bash
set -e

# === 設定（每個專案改這裡）===
PROJECT_NAME="myapp"
PROJECT_DIR="/www/wwwroot/${PROJECT_NAME}.example.com"
APP_SUBDIR="02-web"
PM2_NAME="${PROJECT_NAME}-web"
PORT="3000"
# === 設定結束 ===

cd "$PROJECT_DIR"

echo "📥 [1/5] 拉取最新 code..."
git pull

cd "$APP_SUBDIR"

echo "📦 [2/5] 安裝依賴..."
npm install --omit=dev

echo "🔨 [3/5] 建置..."
npm run build

echo "🔄 [4/5] 重啟 PM2..."
pm2 restart "$PM2_NAME" --update-env || \
  pm2 start npm \
    --name "$PM2_NAME" \
    --interpreter "$(which node)" \
    --cwd "$(pwd)" \
    -- start

echo "✅ [5/5] 驗證..."
sleep 2
pm2 list | grep "$PM2_NAME"
echo "---"
pm2 logs "$PM2_NAME" --lines 10 --nostream
echo "---"
curl -I "http://127.0.0.1:${PORT}" 2>&1 | head -3
echo ""
echo "✓ 部署完成。瀏覽器測試前記得 hard refresh（Cmd+Shift+R）。"
```

執行：
```bash
chmod +x ~/deploy.sh
~/deploy.sh
```

---

## 🎯 部署前 checklist

```
□ 本機 git push 已完成
□ 本機 build 過，沒 error
□ 確認 .env 不在 git tracking 內
□ 確認部署目標的 .env 還在
□ 知道這次要重啟哪個 PM2 process name
□ 知道萬一要回滾的指令
□ 部署完要 hard refresh 瀏覽器
□ 部署完要看 pm2 logs 確認沒 error
```

---

**最後提醒：永遠先讀 server 程式碼，不要猜環境變數位置、port、路徑。**
