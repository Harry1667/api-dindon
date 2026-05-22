---
name: env-check
description: |
  快速檢查本地開發環境：Docker 容器狀態、PM2 進程、Node/Python 版本、
  環境變數完整性、常用 port 是否被佔用、磁碟空間。
  Use when: "環境檢查", "env check", "docker 狀態", "服務健康", "port 佔用"
triggers:
  - env check
  - 環境檢查
  - docker 狀態
  - 服務健康
  - 檢查環境
  - port 佔用
allowed-tools:
  - Bash
  - Read
---

# /env-check — 本地開發環境健康檢查

快速掃描開發環境狀態，找出問題點。

## 執行步驟

### 1. 基本環境版本

```bash
echo "=== 開發環境健康檢查 ==="
echo "時間：$(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "--- Runtime 版本 ---"
node -v 2>/dev/null && echo "Node OK" || echo "❌ Node 未安裝"
npm -v 2>/dev/null && echo "npm OK" || echo "❌ npm 未安裝"
python3 --version 2>/dev/null || echo "❌ Python3 未安裝"
docker --version 2>/dev/null || echo "❌ Docker 未安裝"
git --version 2>/dev/null || echo "❌ git 未安裝"
```

### 2. Docker 容器狀態

```bash
echo ""
echo "--- Docker 容器 ---"
if docker info > /dev/null 2>&1; then
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null
  STOPPED=$(docker ps -a --filter "status=exited" --format "{{.Names}}" 2>/dev/null)
  [ -n "$STOPPED" ] && echo "⚠️  已停止的容器：$STOPPED"
else
  echo "❌ Docker daemon 未啟動"
fi
```

### 3. 常用 Port 佔用

```bash
echo ""
echo "--- Port 佔用 ---"
for PORT in 3000 3001 3002 8080 8081 8091 8765 50051 5432 6379 27017; do
  PID=$(lsof -ti tcp:"$PORT" 2>/dev/null)
  if [ -n "$PID" ]; then
    PROC=$(ps -p "$PID" -o comm= 2>/dev/null)
    echo "🔴 Port $PORT → PID $PID ($PROC)"
  fi
done
echo "（只顯示已佔用的 port）"
```

### 4. 磁碟空間

```bash
echo ""
echo "--- 磁碟空間 ---"
df -h / 2>/dev/null | tail -1 | awk '{print "根目錄：已用 "$3" / 總計 "$2" （"$5"）"}'
docker system df 2>/dev/null | grep -v "^TYPE" | awk '{print $1": 已用 "$3}' || true
```

### 5. .env 完整性（當前目錄）

```bash
echo ""
echo "--- .env 檔案檢查 ---"
if [ -f ".env.example" ] && [ -f ".env" ]; then
  MISSING=$(comm -23 \
    <(grep -E "^[A-Z_]+=?" .env.example | cut -d= -f1 | sort) \
    <(grep -E "^[A-Z_]+=?" .env | cut -d= -f1 | sort) 2>/dev/null)
  if [ -n "$MISSING" ]; then
    echo "⚠️  .env 缺少 key：$MISSING"
  else
    echo "✅ .env 與 .env.example 的 key 一致"
  fi
elif [ -f ".env.example" ] && [ ! -f ".env" ]; then
  echo "⚠️  有 .env.example 但沒有 .env → cp .env.example .env"
fi
```

### 6. 輸出格式

```
## 環境檢查報告 [時間]

### ✅ 正常
- Node v22.x, npm 10.x
- Docker：3 個容器運行中

### ⚠️ 需注意
- Port 3000 被 node (PID 12345) 佔用
- .env 缺少 API_KEY

### ❌ 問題
- Docker daemon 未啟動
```

## 注意事項

- 不要自動修改任何設定，只報告狀態
- Linux 改用 `ss -tlnp` 取代 `lsof`
