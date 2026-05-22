---
name: deploy-sop
description: |
  兩件事：建立 GitHub repo 並推上去、把專案部署到 looptw.com 伺服器。
  可以分開做也可以一起做。
  Use when: "部署", "deploy", "上線", "建 repo", "git push", "PM2", "Nginx",
  "aaPanel", "502", "Cannot find package", "tarball 部署", "新增網站", "推 github"
triggers:
  - 部署
  - deploy
  - 上線
  - 建 repo
  - git push
  - PM2 啟動
  - Nginx 反向代理
  - git pull 更新
  - 502 bad gateway
  - Cannot find package
  - 新增網站
  - 推 github
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - AskUserQuestion
---

# /deploy-sop — GitHub 建 repo + looptw.com 部署 SOP

這個 skill 做兩件事，可以分開也可以一起：
- **Part 1**：在 GitHub 建立 repo，設定 remote，`git push` 推上去
- **Part 2**：SSH 進 looptw.com 伺服器，部署網站

先問使用者要做哪個，或兩個都要。

> ⚠️ **搭配 `/git-safety` 使用**
> 不管是推 GitHub 還是上傳伺服器，都要先過濾敏感檔案。
> 每次執行 Part 1 或 Part 2 之前，必須先跑下方的安全檢查。

---

## 🔒 安全檢查（推 GitHub / 部署前都要跑）

```bash
# 1. 確認 .gitignore 有擋住敏感目錄
cat .gitignore | grep -E '\.env|\.key|\.pem|secret|private'

# 2. 掃描 staged 或所有已追蹤的檔案，找出洩漏風險
git diff --cached | grep -iE "(password|密碼|secret|token|api[_-]?key|ghp_|ghs_|sk-|AKIA|BEGIN [A-Z ]+PRIVATE KEY)"
git ls-files | grep -E '\.env$|key$|pem$|sqlite$|\.db$'
# 兩個指令都應該沒有輸出，有就停下來處理

# 3. 常見需要過濾的東西
#    .env / .env.local          → 環境變數（含 API key、密碼）
#    *.key / *.pem / id_rsa     → SSH / SSL 私鑰
#    *.sqlite / *.db            → production 資料庫
#    01-dev/0-run.md 之類       → 含真實帳密的個人筆記
#    node_modules / dist        → build 產物（沒必要上去）
#    .DS_Store / ._*            → macOS 垃圾檔
```

有問題先用 `/git-safety` 處理再回來。

---

## Part 1：GitHub 建 repo + 推上去

### Step 1-1：確認 gh CLI 已登入

```bash
gh auth status
# 如果沒登入：gh auth login
```

### Step 1-2：確認 .gitignore 存在且正確

```bash
# 如果還沒有 .gitignore，從 git-safety 的範本建一個
# 最少要有這幾行：
cat >> .gitignore << 'EOF'
.env
.env.*
!.env.example
*.key
*.pem
node_modules/
dist/
build/
.DS_Store
._*
*.sqlite
*.db
EOF

# 如果還沒 git init
git init
```

### Step 1-3：建立 GitHub repo

```bash
# 建立 private repo（預設推薦）
gh repo create <repo-name> --private --source=. --remote=origin --push

# 或建立 public repo
gh repo create <repo-name> --public --source=. --remote=origin --push
```

如果 repo 已存在，只需要設定 remote：

```bash
git remote add origin https://github.com/<帳號>/<repo-name>.git
git branch -M main
git push -u origin main
```

### Step 1-4：之後每次推上去

```bash
git add .
git commit -m "你的 commit message"
git push
```

---

## Part 2：部署到 looptw.com 伺服器

## Step 0：開始前確認

**先問使用者：**

> 網域和 DNS 設定好了嗎？（Cloudflare 加了 A 記錄、指向 `137.131.7.230`，灰色雲朵）
> 大多數情況下已經設定好，確認一下就好。

如果還沒設定，給這個流程：
1. 登入 Cloudflare → 點 `looptw.com` → DNS → 新增記錄
2. 類型：`A`，名稱：`<專案名稱>`，IPv4：`137.131.7.230`，Proxy：**灰色雲朵（DNS Only）**
3. `ping <專案名稱>.looptw.com` 確認 IP 正確後再繼續

---

## Step 1：SSH 進伺服器，確認現有專案

```bash
ssh -i ~/Documents/important\ file/ssh-key-2026-04-08.key ubuntu@137.131.7.230
sudo su
```

進去後先看 wwwroot 有哪些專案：

```bash
ls /www/wwwroot/
```

把結果告訴使用者，確認新專案名稱不衝突，並確認部署目標路徑：

```
/www/wwwroot/<專案名稱>.looptw.com
```

### ⚠️ 每次部署前必掃：現有 Port 路由表

> 下方「現有專案 Port 路由表」只是快照，會過時。**每次部署前都要在伺服器跑這段掃描**，
> 用實際結果挑下一個可用 port，不要憑記憶猜。

```bash
# 已在 sudo su 狀態下，一次掃出 nginx 路由 + 實際監聽 + 已佔用 port
bash -c '
echo "=== 現有 Node port 路由（nginx → 實際監聽）==="
printf "%-28s %-8s %-22s %s\n" 域名 nginxPort 監聽程序 狀態
for f in /www/server/panel/vhost/nginx/*.looptw.com.conf; do
  [ -e "$f" ] || continue
  d=$(basename "$f" .conf)
  p=$(grep -rhoE "proxy_pass http://127.0.0.1:[0-9]+" "$f" /www/server/panel/vhost/nginx/proxy/${d}/*.conf 2>/dev/null | grep -oE "[0-9]+$" | head -1)
  [ -z "$p" ] && continue
  proc=$(ss -tlnp 2>/dev/null | grep -E "[*:.]$p " | grep -oE "users:\(\(\"[^\"]+" | head -1 | grep -oE "[^\"]+$")
  st=$([ -n "$proc" ] && echo OK || echo "⚠️無監聽")
  printf "%-28s %-8s %-22s %s\n" "$d" "$p" "${proc:--}" "$st"
done
echo
echo "=== 已被佔用的 30xx port（含 docker / 內部服務）==="
ss -tlnp 2>/dev/null | grep -oE "[*:.]30[0-9][0-9] " | grep -oE "30[0-9]+" | sort -u
'
```

挑「已被佔用」清單以外的最小 port 給新專案。

> 📌 **用掉一個 port 後，記得回來更新本檔（`001-deploy-docs/SKILL.md`）下方的「現有專案 Port 路由表」**，
> 把新域名、port、PM2 名稱補進去，下次才不會撞 port。

---

## Step 2：判斷專案類型

| 類型 | 特徵 | 部署方式 |
|---|---|---|
| **A. 純 Next.js** | 前後端一體，無本地檔案儲存 | git pull |
| **B. SPA + Node backend** | Vite + Express，可能含 SQLite | git pull 或 tarball |
| **C. 純前端 SPA** | build 出靜態檔，打外部 API | nginx serve dist/ |
| **D. 含 Python 副服務** | 主應用 + uvicorn / Worker | git pull + 多 PM2 |

```bash
# 在本機專案目錄判斷類型
ls package.json next.config.* vite.config.* server.mjs server.js 2>/dev/null
grep -l "sqlite\|leveldb" package.json 2>/dev/null
```

---

## Step 3：第一次部署

### 共通：clone 專案

```bash
# 已在 sudo su 狀態下
git config --global --add safe.directory /www/wwwroot/<專案名稱>.looptw.com
cd /www/wwwroot/

# 公開 repo：直接 clone
git clone https://github.com/<帳號>/<repo>.git <專案名稱>.looptw.com

# 私有 repo：伺服器若已裝 gh 且登入，用 gh clone 最省事
#   gh repo clone <帳號>/<repo> <專案名稱>.looptw.com
# 否則用 token（用完即清，別寫進 remote）：
#   git clone https://<帳號>:<PERSONAL_ACCESS_TOKEN>@github.com/<帳號>/<repo>.git <專案名稱>.looptw.com

cd <專案名稱>.looptw.com
```

---

### 路徑 A：純 Next.js

```bash
cd <app-dir>         # 通常是 02-web/
npm install
nano .env.local      # 貼上環境變數
chmod 600 .env.local
npm run build
pm2 start npm \
  --name <專案名稱>-web \
  --interpreter $(which node) \
  --cwd $(pwd) \
  -- start
pm2 save
# 驗證
curl -I http://127.0.0.1:3000
```

---

### 路徑 B：SPA + Node backend

```bash
cd <app-dir>
npm install --omit=dev
# 先確認 .env 要放哪裡
grep -n "envPath\|\.env\|dotenv" server.mjs
nano .env            # 或 ../.env，看上一步的結果
chmod 600 .env
npm run build
pm2 start server.mjs \
  --name <專案名稱>-web \
  --interpreter $(which node) \
  --cwd $(pwd)
pm2 save
curl -I http://127.0.0.1:3001
```

---

### 路徑 C：純前端 SPA（不需 PM2）

```bash
cd <app-dir>
npm install && npm run build
# aaPanel 直接 serve dist/，不用 PM2
```

---

### 路徑 D：含 Python 副服務

```bash
# 1. 先按 A 或 B 部署主應用
# 2. 再啟動副服務
cd <python-subdir>
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pm2 start ./venv/bin/python \
  --name <專案名稱>-bridge \
  --cwd $(pwd) \
  --interpreter none \
  -- -m uvicorn server:app --host 127.0.0.1 --port 8765
pm2 save
```

---

## Step 4：aaPanel 建站 + Nginx 設定 + SSL

### 4-1：aaPanel 添加站點

請使用者自行登入 aaPanel 後台，操作如下：

**網站 → 添加站點**

| 欄位 | 填入 |
|---|---|
| 域名 | `<專案名稱>.looptw.com` |
| 根目錄 | `/www/wwwroot/<專案名稱>.looptw.com` |
| PHP 版本 | 純 Node.js 專案選「純靜態」；有 PHP 選 `8.3` |
| 資料庫 | 不需要（除非有 MySQL）|

建立後 SSH 確認目錄存在：

```bash
ls -la /www/wwwroot/<專案名稱>.looptw.com
# 如果目錄不存在或是空的，代表 clone 步驟有問題
```

---

### 4-2：Nginx 配置

在 aaPanel → 網站 → 點站點名稱 → **配置文件**，根據專案類型貼入對應設定。

**⚠️ 注意：`include enable-php-83.conf;` 本身是一個 location block，不能放在另一個 `location { }` 裡面，否則 Nginx 會報錯。**

---

#### 類型 A / B / D：Node.js（有 PM2，需反向代理）

把 `location /` 區塊替換成：

```nginx
location / {
    proxy_pass http://127.0.0.1:3000;   # 改成實際 port
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_buffering off;
    proxy_cache off;
    client_max_body_size 50M;
}
location ~ /\. {
    deny all;
    return 404;
}
```

---

#### 類型 C：純前端 SPA + PHP API（React/Vue + api.php）

完整配置範本（複製後把 `[DOMAIN]` 全部換掉）：

```nginx
server {
    listen 80;
    server_name [DOMAIN];
    index index.php index.html index.htm;
    root /www/wwwroot/[DOMAIN];

    include /www/server/panel/vhost/nginx/well-known/[DOMAIN].conf;
    include enable-php-83.conf;
    include /www/server/panel/vhost/rewrite/[DOMAIN].conf;

    # SPA fallback（React/Vue Router）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 禁止存取敏感檔案
    location ~ ^/(\.user.ini|\.htaccess|\.git|\.env|\.svn) {
        return 404;
    }

    # 禁止存取資料庫目錄（如有 SQLite）
    location /database {
        deny all;
        return 404;
    }

    # Service Worker 不快取
    location = /sw.js {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        expires off;
    }

    # WASM MIME type（如果專案有用 .wasm）
    location ~ \.wasm$ {
        types { application/wasm wasm; }
        expires 30d;
    }

    # 靜態資源快取
    location ~ .*\.(gif|jpg|jpeg|png|bmp|swf|svg)$ { expires 30d; }
    location ~ .*\.(js|css)?$ { expires 12h; }

    access_log /www/wwwlogs/[DOMAIN].log;
    error_log /www/wwwlogs/[DOMAIN].error.log;
}
```

---

#### 額外選項（視需求加進 Node.js 設定）

有 SQLite 資料庫目錄：
```nginx
location /database {
    deny all;
    return 404;
}
```

有 WASM 檔案：
```nginx
location ~ \.wasm$ {
    types { application/wasm wasm; }
    expires 30d;
}
```

有 Service Worker：
```nginx
location = /sw.js {
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    expires off;
}
```

---

### 4-3：儲存 Nginx 設定

儲存後若出現紅色報錯，最常見原因：
- `include enable-php-83.conf;` 被嵌套在 `location { }` 裡 → 移出來放 server 層級
- port 填錯（proxy_pass 的 port 跟 PM2 啟動的 port 不一致）

---

### 4-4：申請 SSL

**SSL → Let's Encrypt → 申請 → 開啟強制 HTTPS**

申請前確認：
```bash
ping <專案名稱>.looptw.com
# 確認回傳 IP 是 137.131.7.230，不是才需要等 DNS 生效
```

> ⚠️ Let's Encrypt 連續失敗 5 次後要等 1 小時才能重試
> ⚠️ Cloudflare 必須是灰色雲朵（DNS Only），橘色會跟 Let's Encrypt 衝突

---

### 4-5：設定檔案權限（PHP / SQLite 專案）

```bash
# SSH 伺服器內
chown -R www:www /www/wwwroot/<專案名稱>.looptw.com
```

---

## Step 5：驗證

```bash
# 伺服器端
pm2 list
pm2 logs <專案名稱>-web --lines 20 --nostream

# 本機
curl -I https://<專案名稱>.looptw.com
# 應該回 200 / 301，不該是 502 / SSL error
```

---

## 後續更新

### git pull 模式（A/D，無 SQLite）

```bash
ssh -i ~/Documents/important\ file/ssh-key-2026-04-08.key ubuntu@137.131.7.230
sudo su
cd /www/wwwroot/<專案名稱>.looptw.com
git pull
cd <app-dir>
npm install --omit=dev   # 有新依賴才需要
npm run build
pm2 restart <專案名稱>-web --update-env
pm2 logs <專案名稱>-web --lines 20 --nostream
```

### tarball 模式（B，含 SQLite）

```bash
# 本機打包
npm run build
COPYFILE_DISABLE=1 tar --no-xattrs -czf <project>-$(date +%Y%m%d).tar.gz dist-deploy/
scp -i ~/Documents/important\ file/ssh-key-2026-04-08.key \
  <project>-*.tar.gz ubuntu@137.131.7.230:/tmp/

# 伺服器
ssh -i ~/Documents/important\ file/ssh-key-2026-04-08.key ubuntu@137.131.7.230
sudo su
cd /www/wwwroot/<專案名稱>.looptw.com
mv <app-dir> <app-dir>.backup-$(date +%Y%m%d-%H%M)
tar -xzf /tmp/<project>-*.tar.gz -C .deploy-tmp
mv .deploy-tmp/dist-deploy <app-dir>
cp -R <app-dir>.backup-*/node_modules <app-dir>/node_modules 2>/dev/null
cp <app-dir>.backup-*/src/database/*.sqlite <app-dir>/src/database/ 2>/dev/null
pm2 restart <專案名稱>-web --update-env
```

---

## 常見錯誤排除

### ❌ `Cannot find package 'express'`

```bash
pm2 kill
pm2 start <script> --name <name> --interpreter $(which node) --cwd $(pwd)
```

### ❌ PM2 ↺ 重啟次數爆增

```bash
pm2 list                          # 找重複 process
pm2 delete <重複的 name>
# 或直接跑看錯誤：
pm2 stop <name> && timeout 5 node server.mjs
```

### ❌ .env 改了沒生效

```bash
pm2 restart <name> --update-env   # 必加 --update-env
```

### ❌ 502 Bad Gateway

```bash
pm2 logs <name> --lines 50
curl -I http://127.0.0.1:<port>
```

### ❌ 改完 code 線上沒變化

1. `git pull` 有沒有 `Updating`
2. `npm run build` 有沒有成功
3. `pm2 restart` 有沒有跑
4. PWA Service Worker → 瀏覽器 Cmd+Shift+R
5. Cloudflare 橘雲 → Purge Cache

### ❌ SSL 申請失敗

- `ping <專案名稱>.looptw.com` 確認 IP 是 `137.131.7.230`
- Cloudflare 確認是灰色雲朵
- Let's Encrypt 失敗 5 次後要等 1 小時

---

## 回滾

```bash
# git pull 模式
git revert <bad-commit>
npm run build && pm2 restart <name> --update-env

# tarball 模式
pm2 stop <name>
rm -rf <app-dir>
mv <app-dir>.backup-<日期>-<時間> <app-dir>
pm2 start <name>
```

---

## 伺服器基礎設施參考

### 規格

| 項目 | 值 |
|---|---|
| 伺服器 | Oracle Cloud（鳳凰城）ARM64 |
| OS | Ubuntu 24.04.4 LTS (aarch64) |
| 面板 | aaPanel 8.0.1 |
| Nginx | 1.24.0（含 HTTP/2, Lua） |
| PHP | 8.3（socket: `/tmp/php-cgi-83.sock`） |
| 磁碟 | 193GB 總容量，181GB 可用 |
| 檔案擁有者 | 所有 web 檔案必須是 `www:www` |

### 現有專案 Port 路由表（快照，以實際掃描為準）

> ⚠️ 這張表是 **2026-05-21** 的快照，僅供參考。真正的依據是 Step 1 的掃描指令。

| 域名 | 類型 | Port | PM2 名稱 | 狀態 |
|---|---|---|---|---|
| `mentora.looptw.com` | Next.js | **3000** | `mentora-web`（+`mentora-bridge`） | ✅ |
| `reportassist.looptw.com` | Bun | **3001** | `reportassist-api` | ✅ |
| `chatcal.looptw.com` | Node | **3002** | `chatcal-web`（+`chatcal-bot`） | ✅ |
| `imageanalysis.looptw.com` | Next.js | **3005** | `imageanalysis-web` | ✅ |
| `socialbot.looptw.com` | Next.js | **3006** | （Next） | ✅ |
| `documentchatbot.looptw.com` | Next.js | **3007** | `documentchatbot-web` | ✅ |
| `mathbox.looptw.com` | Node ESM (Express) | **3008** | `mathbox` | ✅ |
| `survivalwallet` / `homeworksolver` / `keystorage` / `linkchannel` / `nearsafe` / `worklog` / `zhijian` | 靜態 / PHP | N/A | — | 純前端或 PHP |

- `3003` 被 docker-proxy 佔用，`3004`、`3010` 已被內部服務佔用。
- **下一個新專案 Port：3009**（仍以掃描結果為準）。
- ⚠️ 注意：程式若用 `process.env.PORT || 3001` 這種 fallback，務必在 PM2 設好 `PORT` env 並 `pm2 save`，否則撞 port crash loop（mathbox 曾因此 restart 46 萬次）。

### 已知環境限制

- macOS 打包前清掉隱藏檔：`find . -name "._*" -delete`
- ARM64 部分 C++ Addons 需確認有 ARM 版本
- Node.js 由 aaPanel 安裝，SSH 直接打 `node` 可能找不到，用 PM2 的 `$(which node)` 指定
- `include enable-php-83.conf;` 是 location block，不能嵌套在另一個 `location {}` 裡

---

## PM2 指令速查

| 用途 | 指令 |
|---|---|
| 啟動 | `pm2 start <script> --name <name> --interpreter $(which node) --cwd $(pwd)` |
| 重啟 | `pm2 restart <name> --update-env` |
| 砍 process | `pm2 delete <name>` |
| 砍 daemon | `pm2 kill` |
| 列表 | `pm2 list` |
| 看 log | `pm2 logs <name> --lines 20 --nostream` |
| 即時 monitor | `pm2 monit` |
| 儲存設定 | `pm2 save` |

---

## 部署前 checklist

```
□ 網域 DNS 已設定（或已確認不需要）
□ 本機 git push 完成
□ 本機 build 過，沒 error
□ .env 不在 git tracking 內
□ 伺服器的 .env 確認還在
□ 知道要重啟哪個 PM2 process name
□ 部署完 hard refresh 瀏覽器
□ 部署完看 pm2 logs 確認沒 error
```
