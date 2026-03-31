#!/bin/bash
# 叮咚到號 — 本地 build + 推 image 到伺服器
# 避免在 lightsail 上 docker build 導致機器掛掉
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_NAME="ajz-dindon:latest"
IMAGE_TAR="/tmp/ajz-dindon.tar"
REMOTE="aapanel"
REMOTE_DIR="/opt/docker/ajz-dingdon"

echo "========================================="
echo "  叮咚到號 — 本地 Build + Deploy"
echo "========================================="

# 1. 本地 build
echo ""
echo "[1/5] 本地 docker build..."
cd "$PROJECT_DIR"
docker build -t "$IMAGE_NAME" .

# 2. 匯出 image
echo ""
echo "[2/5] 匯出 image..."
docker save "$IMAGE_NAME" -o "$IMAGE_TAR"
SIZE=$(du -h "$IMAGE_TAR" | cut -f1)
echo "Image size: $SIZE"

# 3. 上傳到伺服器
echo ""
echo "[3/5] 上傳到伺服器..."
scp "$IMAGE_TAR" "$REMOTE:/tmp/ajz-dindon.tar"

# 4. 伺服器載入 image + 啟動
echo ""
echo "[4/5] 伺服器載入 image 並重啟..."
ssh "$REMOTE" "
  cd $REMOTE_DIR &&
  git pull origin main &&
  docker load -i /tmp/ajz-dindon.tar &&
  docker compose -f docker-compose.prod.yml up -d &&
  rm -f /tmp/ajz-dindon.tar
"

# 5. 等待 + 健康檢查
echo ""
echo "[5/5] 等待啟動..."
sleep 10

HEALTH=$(ssh "$REMOTE" "curl -s http://localhost:8000/health")
echo "Health: $HEALTH"

if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo ""
    echo "========================================="
    echo "  部署成功！"
    echo "========================================="
else
    echo ""
    echo "WARNING: 健康檢查異常"
    echo "  ssh aapanel 'docker compose -f $REMOTE_DIR/docker-compose.yml logs --tail 30 app'"
fi

# 清理本地 tar
rm -f "$IMAGE_TAR"
