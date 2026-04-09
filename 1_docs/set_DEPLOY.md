# 部署指南

## 環境資訊

| 項目 | 值 |
|------|-----|
| 域名 | `dd.dl-app.com` |
| 主機 | AWS Lightsail Tokyo（`ssh aapanel`） |
| 路徑 | `/www/wwwroot/dd.dl-app.com` |
| 對外 Port | 8045（容器內 8000） |
| Redis Port | 6399（容器內 6379） |
| 面板 | aaPanel |

## Docker 安裝（安裝在 /opt/docker）

如果伺服器還沒裝 Docker：

```bash
ssh aapanel

# 安裝 Docker（指定資料目錄 /opt/docker）
curl -fsSL https://get.docker.com | sh

# 修改 Docker 資料目錄
sudo mkdir -p /opt/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "data-root": "/opt/docker"
}
EOF

# 重啟 Docker
sudo systemctl restart docker

# 驗證資料目錄
docker info | grep "Docker Root Dir"
# 應顯示：Docker Root Dir: /opt/docker

# 安裝 Docker Compose plugin（如果沒有）
sudo apt-get install -y docker-compose-plugin 2>/dev/null || true
docker compose version
```

## 首次部署

### 1. 在伺服器上 clone 專案

```bash
ssh aapanel
cd /www/wwwroot
git clone <your-repo-url> dd.dl-app.com
cd dd.dl-app.com
```

### 2. 設定環境變數

```bash
cp .env.example .env
nano .env
```

必填項：
- `LINE_CHANNEL_SECRET` — LINE Bot 設定
- `LINE_CHANNEL_ACCESS_TOKEN` — LINE Bot 設定
- `MYSQL_PASSWORD` — MySQL 密碼
- `JWT_SECRET_KEY` — `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `API_BEARER_TOKEN` — `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `ADMIN_LINE_USER_ID` — 管理員 LINE ID（接收告警）

### 3. 建立 MySQL 資料庫

在 aaPanel → Database → 新增：
- 資料庫名: `medical_queue`
- 用戶名: `medqueue`
- 編碼: `utf8mb4`

### 4. aaPanel 設定域名

aaPanel → Website → Add site → 域名: `dd.dl-app.com`
aaPanel → Website → dd.dl-app.com → SSL → Let's Encrypt（自動續期）
aaPanel → Website → dd.dl-app.com → Configuration → 貼入以下完整 Nginx 設定：

```nginx
server
{
    listen 80;
    listen 443 ssl http2 ;
    listen [::]:443 ssl http2 ;
    listen [::]:80;
    server_name dd.dl-app.com;
    index index.php index.html index.htm default.php default.htm default.html;
    root /www/wwwroot/dd.dl-app.com;
    include /www/server/panel/vhost/nginx/extension/dd.dl-app.com/*.conf;

    #CERT-APPLY-CHECK--START
    include /www/server/panel/vhost/nginx/well-known/dd.dl-app.com.conf;
    #CERT-APPLY-CHECK--END
    #SSL-START
    #error_page 404/404.html;
    #HTTP_TO_HTTPS_START
    if ($server_port !~ 443){
        rewrite ^(/.*)$ https://$host$1 permanent;
    }
    #HTTP_TO_HTTPS_END
    ssl_certificate    /www/server/panel/vhost/cert/dd.dl-app.com/fullchain.pem;
    ssl_certificate_key    /www/server/panel/vhost/cert/dd.dl-app.com/privkey.pem;
    ssl_protocols TLSv1.1 TLSv1.2 TLSv1.3;
    ssl_ciphers EECDH+CHACHA20:EECDH+CHACHA20-draft:EECDH+AES128:RSA+AES128:EECDH+AES256:RSA+AES256:EECDH+3DES:RSA+3DES:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_tickets on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    add_header Strict-Transport-Security "max-age=31536000";
    error_page 497  https://$host$request_uri;
    #SSL-END

    #ERROR-PAGE-START
    error_page 404 /404.html;
    error_page 502 /502.html;
    #ERROR-PAGE-END

    #PHP-INFO-START
    include enable-php-00.conf;
    #PHP-INFO-END

    #REWRITE-START
    include /www/server/panel/vhost/rewrite/dd.dl-app.com.conf;
    #REWRITE-END

    # === LINE Bot Webhook ===
    location /webhook {
        proxy_pass http://127.0.0.1:8045/webhook;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # === Health Check（無認證）===
    location /health {
        proxy_pass http://127.0.0.1:8045/health;
        proxy_set_header Host $host;
    }

    # === Admin 後台（JWT 認證）===
    location /admin {
        proxy_pass http://127.0.0.1:8045/admin;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # === 公開 API（Bearer Token + Rate Limit）===
    location /api/ {
        proxy_pass http://127.0.0.1:8045/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }

    # === FastAPI 自動文件（開發用，正式環境可移除）===
    location /docs {
        proxy_pass http://127.0.0.1:8045/docs;
        proxy_set_header Host $host;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8045/openapi.json;
        proxy_set_header Host $host;
    }

    # Forbidden files or directories
    location ~ ^/(\.user.ini|\.htaccess|\.git|\.env|\.svn|\.project|LICENSE|README.md)
    {
        return 404;
    }

    location ~ \.well-known{
        allow all;
    }

    if ( $uri ~ "^/\.well-known/.*\.(php|jsp|py|js|css|lua|ts|go|zip|tar\.gz|rar|7z|sql|bak)$" ) {
        return 403;
    }

    location ~ .*\.(gif|jpg|jpeg|png|bmp|swf)$
    {
        expires      30d;
        error_log /dev/null;
        access_log /dev/null;
    }

    location ~ .*\.(js|css)?$
    {
        expires      12h;
        error_log /dev/null;
        access_log /dev/null;
    }
    access_log  /www/wwwlogs/dd.dl-app.com.log;
    error_log  /www/wwwlogs/dd.dl-app.com.error.log;
}
```

### 5. 啟動 Docker

```bash
cd /www/wwwroot/dd.dl-app.com
docker compose build
docker compose up -d
```

### 6. 驗證

```bash
# 健康檢查
curl https://dd.dl-app.com/health

# API 測試（帶 token）
curl -H "X-API-Key: <your-token>" https://dd.dl-app.com/api/hospitals

# 查看 log
docker logs -f medqueue-app
docker logs -f medqueue-worker
```

### 7. 設定 LINE Webhook URL

LINE Developers Console → Messaging API → Webhook URL:
```
https://dd.dl-app.com/webhook
```

## 更新部署

```bash
cd /www/wwwroot/dd.dl-app.com
git pull
docker compose build
docker compose up -d
```

## 常用指令

```bash
# 查看容器狀態
docker compose ps

# 查看爬蟲 log
docker logs -f medqueue-worker

# 查看 API log
docker logs -f medqueue-app

# 重啟
docker compose restart

# 在容器內跑測試
docker compose exec app python -m pytest tests/ -v

# 進入容器 shell
docker compose exec app bash
```

## 服務架構

```
dd.dl-app.com (Nginx + SSL)
  │
  ├── /webhook        → medqueue-app:8000  (LINE Bot)
  ├── /api/*          → medqueue-app:8000  (公開 API，需 X-API-Key)
  ├── /admin/*        → medqueue-app:8000  (管理後台，需 JWT)
  ├── /health         → medqueue-app:8000  (健康檢查)
  │
  ├── medqueue-worker (Celery: 爬蟲 + 通知 + 排程)
  └── medqueue-redis  (快取 + 任務佇列，port 6399)
```

## 休診排程

爬蟲自動在以下時段停止（節省伺服器資源）：
- 每天 22:00 ~ 07:00（夜間無看診）
- 週日全天
- 台灣國定假日（元旦、228、清明、兒童節、勞動節、國慶、農曆新年、端午、中秋）

週六照常爬蟲（動態頻率控制會自動降速沒看診的醫院）。
