# SSH 安全連線設定 — aaPanel (57.182.129.192)

> **目的**：讓 Claude Code 透過 SSH 操作伺服器項目，同時防止誤刪系統或重要檔案。
> **原則**：最小權限 — 能裝套件、能操作 Docker、能管理項目，但不能刪系統。

---

## 目錄

1. [建立受限帳號](#1-建立受限帳號)
2. [設定 sudo 白名單](#2-設定-sudo-白名單)
3. [SSH Key 認證（免密碼）](#3-ssh-key-認證)
4. [保護系統關鍵目錄](#4-保護系統關鍵目錄)
5. [限制刪除範圍](#5-限制刪除範圍)
6. [SSH 連線測試](#6-ssh-連線測試)
7. [權限速查表](#7-權限速查表)
8. [緊急處理](#8-緊急處理)

---

## 1. 建立受限帳號

用 root 登入伺服器執行：

```bash
# 建立帳號
useradd -m -s /bin/bash claude

# 設定密碼（記下來，後面 Claude Code 要用）
passwd claude

# 加入 www 群組（aaPanel 網站檔案群組）
usermod -aG www claude

# 加入 docker 群組（讓 claude 可以執行 docker 指令，不需 sudo）
usermod -aG docker claude

# 給項目目錄權限
chown -R claude:www /opt/docker/arkmesa-aiaeoscan
chmod -R 775 /opt/docker/arkmesa-aiaeoscan

# 建立上傳暫存區（給 scp 用）
mkdir -p /home/claude/upload
chown claude:claude /home/claude/upload
```

---

## 2. 設定 sudo 白名單

只允許特定指令，**明確禁止 rm、chmod、chown 系統目錄**。

```bash
visudo
```

在最後加入：

```sudoers
# ===== Claude 帳號權限 =====

# 允許：套件安裝
claude ALL=(ALL) NOPASSWD: /usr/bin/apt update
claude ALL=(ALL) NOPASSWD: /usr/bin/apt install *
claude ALL=(ALL) NOPASSWD: /usr/bin/apt-get update
claude ALL=(ALL) NOPASSWD: /usr/bin/apt-get install *
claude ALL=(ALL) NOPASSWD: /usr/bin/apt list *
claude ALL=(ALL) NOPASSWD: /usr/bin/dpkg -l *

# 允許：服務管理（只能 restart / reload / status，不能 stop）
claude ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx
claude ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx
claude ALL=(ALL) NOPASSWD: /usr/bin/systemctl status nginx
claude ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart docker
claude ALL=(ALL) NOPASSWD: /usr/bin/systemctl status docker

# 允許：查看日誌
claude ALL=(ALL) NOPASSWD: /usr/bin/journalctl *
claude ALL=(ALL) NOPASSWD: /usr/bin/tail -f /www/wwwlogs/*
claude ALL=(ALL) NOPASSWD: /usr/bin/cat /www/wwwlogs/*

# 允許：certbot SSL 管理
claude ALL=(ALL) NOPASSWD: /usr/bin/certbot *

# 允許：nginx 檢測
claude ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t
claude ALL=(ALL) NOPASSWD: /usr/sbin/nginx -s reload

# 允許：pip（全域安裝，如需要）
claude ALL=(ALL) NOPASSWD: /usr/bin/pip3 install *
claude ALL=(ALL) NOPASSWD: /usr/local/bin/pip3 install *

# 允許：查看系統狀態
claude ALL=(ALL) NOPASSWD: /usr/bin/df *
claude ALL=(ALL) NOPASSWD: /usr/bin/free *
claude ALL=(ALL) NOPASSWD: /usr/bin/netstat *
claude ALL=(ALL) NOPASSWD: /usr/bin/ss *

# 禁止：所有其他 sudo 指令（這是預設行為，不需額外設定）
```

> **注意**：`claude` 帳號已加入 `docker` 群組，可以直接跑 `docker` 和 `docker compose`，不需要 sudo。

---

## 3. SSH Key 認證

### 3.1 本地產生 Key（如果還沒有）

```bash
# 在本地 Linux 執行
ssh-keygen -t ed25519 -C "claude-code" -f ~/.ssh/id_claude_aapanel
```

### 3.2 上傳公鑰到伺服器

```bash
ssh-copy-id -i ~/.ssh/id_claude_aapanel.pub claude@57.182.129.192
```

如果 SSH port 不是 22：
```bash
ssh-copy-id -i ~/.ssh/id_claude_aapanel.pub -p 你的PORT claude@57.182.129.192
```

### 3.3 設定本地 SSH config（方便連線）

編輯 `~/.ssh/config`，加入：

```
Host aapanel
    HostName 57.182.129.192
    User claude
    Port 22
    IdentityFile ~/.ssh/id_claude_aapanel
    # 安全性設定
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

之後 Claude Code 只需：
```bash
ssh aapanel "command"
```

### 3.4 （選配）禁用密碼登入，只允許 Key

在伺服器 `/etc/ssh/sshd_config` 中：
```
PasswordAuthentication no
PubkeyAuthentication yes
```

```bash
systemctl restart sshd
```

> **警告**：確認 Key 登入成功後才關密碼，否則會鎖死自己。

---

## 4. 保護系統關鍵目錄

用 root 執行，防止任何帳號（包括 root 手誤）刪除關鍵檔案：

```bash
# 鎖定系統關鍵設定
chattr +i /etc/passwd
chattr +i /etc/shadow
chattr +i /etc/sudoers
chattr +i /etc/ssh/sshd_config

# 鎖定 aaPanel 本體（防誤刪面板）
chattr +i /www/server/panel/BT-Panel
```

> 日後如需修改這些檔案，先 `chattr -i /etc/passwd` 解鎖，改完再鎖回去。

---

## 5. 限制刪除範圍

### 5.1 用 safe-rm 替代 rm

```bash
# 安裝 safe-rm
apt install safe-rm

# 設定保護清單
cat >> /etc/safe-rm.conf << 'EOF'
/
/*
/etc
/etc/*
/usr
/usr/*
/var
/var/*
/www/server
/www/server/*
/boot
/boot/*
/home
/root
EOF
```

安裝後，`rm /etc/passwd` 會直接拒絕，但 `rm /opt/docker/arkmesa-aiaeoscan/somefile` 正常運作。

### 5.2 設定 claude 帳號的 bash 保護

```bash
# 編輯 claude 的 bashrc
cat >> /home/claude/.bashrc << 'EOF'

# === 安全防護 ===
# rm 強制加 -i（互動確認），除非用 \rm 跳過
alias rm='rm -i --preserve-root'
# 禁止 chmod 777
alias chmod='chmod --preserve-root'
alias chown='chown --preserve-root'
EOF
```

---

## 6. SSH 連線測試

### 6.1 在本地測試連線

```bash
# 測試 SSH 連線
ssh aapanel "whoami && pwd"
# 預期：claude  /home/claude

# 測試 docker 權限
ssh aapanel "docker ps"
# 預期：列出容器

# 測試 docker compose
ssh aapanel "cd /opt/docker/arkmesa-aiaeoscan && docker compose -f docker-compose.prod.yml ps"
# 預期：列出 aiaeoscan 容器

# 測試 sudo apt（應該成功）
ssh aapanel "sudo apt update"
# 預期：正常更新套件列表

# 測試 sudo rm（應該失敗）
ssh aapanel "sudo rm -rf /tmp/testfile"
# 預期：Sorry, user claude is not allowed to execute '/usr/bin/rm ...'
```

### 6.2 驗證安全限制

```bash
# 這些都應該失敗 ✗
ssh aapanel "sudo rm -rf /"
ssh aapanel "sudo systemctl stop nginx"
ssh aapanel "sudo chmod 777 /"
ssh aapanel "sudo cat /etc/shadow"

# 這些都應該成功 ✓
ssh aapanel "sudo apt install -y curl"
ssh aapanel "sudo systemctl restart nginx"
ssh aapanel "docker compose -f /opt/docker/arkmesa-aiaeoscan/docker-compose.prod.yml logs --tail 10"
ssh aapanel "ls -la /opt/docker/arkmesa-aiaeoscan/"
```

---

## 7. 權限速查表

| 操作 | 是否允許 | 方式 |
|------|---------|------|
| 查看/編輯項目檔案 | ✅ | 直接操作 `/opt/docker/arkmesa-aiaeoscan/` |
| docker / docker compose | ✅ | 直接（已在 docker 群組） |
| apt install 安裝套件 | ✅ | `sudo apt install xxx` |
| 重啟 nginx | ✅ | `sudo systemctl restart nginx` |
| 重啟 docker | ✅ | `sudo systemctl restart docker` |
| 查看系統日誌 | ✅ | `sudo journalctl` |
| 查看網站日誌 | ✅ | `sudo tail -f /www/wwwlogs/*` |
| SSL 憑證操作 | ✅ | `sudo certbot` |
| scp 上傳檔案 | ✅ | 傳到 `/home/claude/upload/` 再搬 |
| rm -rf / | ❌ | sudo 白名單不含 rm |
| 停止 nginx | ❌ | 只允許 restart/reload |
| 修改系統設定 | ❌ | /etc 下檔案被 chattr 鎖定 |
| 操作其他網站目錄 | ❌ | 無權限 |
| 修改 aaPanel 面板 | ❌ | 被 chattr 鎖定 |

---

## 8. 緊急處理

### 如果 claude 帳號被入侵

```bash
# 用 root 立即鎖定
passwd -l claude

# 踢掉所有 claude 的 session
pkill -u claude

# 查看 claude 做了什麼
grep "claude" /var/log/auth.log | tail -50
```

### 如果需要暫時提升權限

不要修改 sudoers，直接用 root 操作。操作完成後確認沒有留下寬鬆權限。

### 回溯操作紀錄

claude 帳號的所有指令紀錄在：
```bash
cat /home/claude/.bash_history
```

---

## Claude Code 連線資訊

設定完成後，在 Claude Code 中使用：

```bash
# 單指令
ssh aapanel "docker compose -f /opt/docker/arkmesa-aiaeoscan/docker-compose.prod.yml ps"

# 多指令
ssh aapanel "cd /opt/docker/arkmesa-aiaeoscan && docker compose -f docker-compose.prod.yml logs --tail 50 backend"

# 上傳檔案
scp -r deploy/project/* aapanel:/opt/docker/arkmesa-aiaeoscan/
```
