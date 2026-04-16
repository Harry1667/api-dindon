# nginx 設定恢復 + Phase 1.5

## 一、恢復 nginx config（貼到 SSH 執行）

```bash
set +H
cat > /www/server/panel/vhost/nginx/dd.dl-app.com.conf << 'NGINX_EOF'
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
    if ($server_port \!~ 443){
        rewrite ^(/.*)$ https://$host$1 permanent;
    }
    #HTTP_TO_HTTPS_END
    ssl_certificate    /www/server/panel/vhost/cert/dd.dl-app.com/fullchain.pem;
    ssl_certificate_key    /www/server/panel/vhost/cert/dd.dl-app.com/privkey.pem;
    ssl_protocols TLSv1.1 TLSv1.2 TLSv1.3;
    ssl_ciphers EECDH+CHACHA20:EECDH+CHACHA20-draft:EECDH+AES128:RSA+AES128:EECDH+AES256:RSA+AES256:EECDH+3DES:RSA+3DES:\!MD5;
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

    # === Health Check ===
    location /health {
        proxy_pass http://127.0.0.1:8045/health;
        proxy_set_header Host $host;
    }

    # === Admin 後台 ===
    location /admin {
        proxy_pass http://127.0.0.1:8045/admin;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # === 公開 API ===
    location /api/ {
        proxy_pass http://127.0.0.1:8045/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }

    # === 對話式查詢頁面 ===
    location /chat {
        proxy_pass http://127.0.0.1:8045/chat;
        proxy_set_header Host $host;
    }

    # === LIFF 頁面 ===
    location /liff {
        proxy_pass http://127.0.0.1:8045/liff;
        proxy_set_header Host $host;
    }

    # === FastAPI 文件 ===
    location /docs {
        proxy_pass http://127.0.0.1:8045/docs;
        proxy_set_header Host $host;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8045/openapi.json;
        proxy_set_header Host $host;
    }

    # Forbidden
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
NGINX_EOF
```

## 二、加 JS/CSS proxy（Phase 1.5）

```bash
mkdir -p /www/server/panel/vhost/nginx/extension/dd.dl-app.com
cat > /www/server/panel/vhost/nginx/extension/dd.dl-app.com/js-css-proxy.conf << 'EOF'
location ~* ^/(js|css)/ {
    proxy_pass http://127.0.0.1:8045;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
EOF
```

## 三、Reload nginx

```bash
/www/server/nginx/sbin/nginx -t && /www/server/nginx/sbin/nginx -s reload && echo OK
```
