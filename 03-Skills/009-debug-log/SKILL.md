---
name: debug-log
description: |
  讀取 PM2 log 和 Nginx error log，自動判斷錯誤類型並給出解法。
  適用於伺服器 502、PM2 crash、Cannot find module、.env 沒生效等問題。
  Use when: "看 log", "debug", "502", "PM2 crash", "服務掛了", "錯誤排查"
triggers:
  - 看 log
  - debug
  - 502
  - PM2 crash
  - 服務掛了
  - 錯誤排查
  - Cannot find module
  - 網站掛了
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# /debug-log — 伺服器錯誤排查 SOP

先問使用者：**症狀是什麼？**

| 症狀 | 直接跳到 |
|---|---|
| 網頁顯示 502 Bad Gateway | Step A |
| PM2 process 一直重啟（↺ 次數爆增） | Step B |
| 網頁白畫面或 404 | Step C |
| 改了 .env 沒有生效 | Step D |
| 更新後網站沒變化 | Step E |

---

## Step A：502 Bad Gateway

### 1. 確認 PM2 是否在跑

```bash
ssh -i ~/Documents/important\ file/ssh-key-2026-04-08.key ubuntu@137.131.7.230
sudo su
pm2 list
```

看 `status` 欄：
- `online` → PM2 在跑，但 port 可能不對
- `errored` / `stopped` → 直接跳 Step B

### 2. 確認 port 有沒有監聽

```bash
curl -I http://127.0.0.1:<port>
# 如果 connection refused → 服務沒在跑或 port 不對
```

### 3. 確認 Nginx proxy_pass port 跟 PM2 一致

```bash
cat /www/server/panel/vhost/nginx/<域名>.conf | grep proxy_pass
# 看 port 是不是跟 PM2 啟動的 port 一樣
```

---

## Step B：PM2 一直重啟

### 1. 看最近的 log

```bash
pm2 logs <專案名稱>-web --lines 50 --nostream
```

把 log 貼給使用者，找這幾個關鍵字：

| 關鍵字 | 意思 | 解法 |
|---|---|---|
| `Cannot find package` / `Cannot find module` | 依賴沒裝 | 重新 `npm install` |
| `EADDRINUSE` | port 被佔了 | `pm2 kill` 再重啟 |
| `SyntaxError` | 程式碼語法錯誤 | 看行號修 code |
| `MODULE_NOT_FOUND` | import 路徑錯 | 確認 dist/ 有沒有 build |
| `Error: ENOENT` | 檔案不存在 | 確認 .env / 資料庫路徑 |

### 2. Cannot find package 解法

```bash
pm2 kill
cd /www/wwwroot/<專案名稱>.looptw.com/<app-dir>
npm install --omit=dev
pm2 start server.mjs \
  --name <專案名稱>-web \
  --interpreter $(which node) \
  --cwd $(pwd)
pm2 save
```

### 3. port 衝突解法

```bash
pm2 list                    # 找重複 process
pm2 delete <重複的name>
# 或直接清掉所有
pm2 kill
# 再重新啟動
```

### 4. 直接跑看報錯

```bash
pm2 stop <name>
timeout 5 node server.mjs   # 直接看 stderr
```

---

## Step C：白畫面或 404

### 1. 確認 Nginx try_files 設定

```bash
cat /www/server/panel/vhost/nginx/<域名>.conf | grep try_files
# 應該有：try_files $uri $uri/ /index.html;
```

### 2. 確認 index.html 存在

```bash
ls /www/wwwroot/<域名>/
ls /www/wwwroot/<域名>/dist/   # 如果是 build 後的
```

### 3. 確認 build 有跑

```bash
# 本機
npm run build
# 看有沒有 error，dist/ 有沒有 index.html
```

---

## Step D：.env 改了沒生效

```bash
pm2 restart <名稱> --update-env
# 必加 --update-env，不加的話 env 不會重新載入
```

---

## Step E：更新後網站沒變化

逐一確認：

```bash
# 1. git pull 有沒有拿到新的
git pull
# 看有沒有 "Updating xxxxxx"

# 2. build 有沒有跑
npm run build

# 3. PM2 有沒有重啟
pm2 restart <名稱> --update-env

# 4. 確認線上版本
curl -s https://<域名>/api/version   # 如果有版本 endpoint
```

瀏覽器端：
- `Cmd+Shift+R`（Mac）強制刷新，清 Service Worker 快取
- Cloudflare 橘色雲朵 → Caching → Purge Everything

---

## Nginx log 查法

```bash
# 最近 50 行 error log
tail -50 /www/wwwlogs/<域名>.error.log

# 即時追蹤
tail -f /www/wwwlogs/<域名>.error.log

# 找特定錯誤
grep "502\|upstream\|connect() failed" /www/wwwlogs/<域名>.error.log | tail -20
```
