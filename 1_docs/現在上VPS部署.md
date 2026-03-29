# 上 VPS 部署 — 照著做就好

> 域名：`dindon.cleanhome.tw`
> 所有設定都已填好，只要跑指令。

---

## 1. DNS 指向（如果還沒做）

到你的域名管理後台，新增一筆 A 記錄：

```
主機名: dindon
類型:   A
值:     你的VPS IP
```

---

## 2. aaPanel 新增網站

1. aaPanel → **Website** → **Add site**
2. 域名填：`dindon.cleanhome.tw`
3. 不需要選 PHP、不需要資料庫
4. 建立後 → **SSL** → **Let's Encrypt** → 申請 → 開啟強制 HTTPS

---

## 3. MySQL 開放 Docker 連線權限

SSH 登入 VPS，執行：

```bash
mysql -u root -p
```

輸入 MySQL root 密碼後執行：

```sql
-- MySQL 8.0+ 要分開寫，不能在 GRANT 裡加 IDENTIFIED BY
CREATE USER 'ajz-dindon'@'172.%' IDENTIFIED BY 'zJaMMfP6NnhyNK5H';
GRANT ALL PRIVILEGES ON `ajz-dindon`.* TO 'ajz-dindon'@'172.%';
FLUSH PRIVILEGES;
EXIT;
```

> 如果出現 `ERROR 1396 用戶已存在`，把第一行改成：
> `ALTER USER 'ajz-dindon'@'172.%' IDENTIFIED BY 'zJaMMfP6NnhyNK5H';`

---

## 4. 上傳程式碼

把 `medical-queue-notify/` 整個目錄上傳到 VPS。可以用 aaPanel 的檔案管理或 scp：

```bash
# 在你的電腦上執行（把 YOUR_VPS_IP 換成你的 IP）
scp -r medical-queue-notify/ root@YOUR_VPS_IP:/www/wwwroot/
```

或在 VPS 上 git clone（如果你有放到 GitHub 的話）。

---

## 5. 啟動 Docker

SSH 登入 VPS：

```bash
cd /www/wwwroot/medical-queue-notify/

# 確認 .env 檔案存在且內容正確
cat .env

# 建置 + 啟動
docker compose build
docker compose up -d

# 確認 4 個容器都跑起來
docker compose ps
```

應該看到：

```
medqueue-app     ... Up
medqueue-worker  ... Up
medqueue-beat    ... Up
medqueue-redis   ... Up
```

健康檢查：

```bash
curl http://localhost:8000/health
# 應回傳 {"status":"ok","version":"0.1.0"}
```

---

## 6. 設定 Nginx 反向代理

aaPanel → Website → `dindon.cleanhome.tw` → **Config**（設定檔）

找到 `location / {` 的上方，加入：

```nginx
location /webhook {
    proxy_pass http://127.0.0.1:8000/webhook;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
}

location /health {
    proxy_pass http://127.0.0.1:8000/health;
    proxy_set_header Host $host;
}
```

儲存後，從外網測試：

```bash
curl https://dindon.cleanhome.tw/health
# 應回傳 {"status":"ok","version":"0.1.0"}
```

---

## 7. LINE Developers 設定 Webhook

1. 打開 https://developers.line.biz/console/
2. 進入你的 Channel → **Messaging API** tab
3. Webhook URL 填：

```
https://dindon.cleanhome.tw/webhook
```

4. 開啟 **Use webhook**
5. 點 **Verify** → 應該顯示 **Success**
6. 確認 **Auto-reply messages** 已關閉

---

## 8. 測試！

1. 用手機 LINE 掃描 QR code 加入「叮咚到號」
2. Bot 應該自動回覆使用說明
3. 輸入 `萬芳 精神科` 測試查詢
4. 輸入 `追蹤 萬芳 精神科 許元彰 我是60號` 測試追蹤

---

## 如果遇到問題

```bash
# 看應用日誌
docker compose logs -f app

# 看爬蟲日誌
docker compose logs -f worker

# 看所有日誌
docker compose logs -f

# 重啟
docker compose restart

# 重新建置
docker compose down && docker compose build && docker compose up -d
```
