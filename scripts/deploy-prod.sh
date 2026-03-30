#!/bin/bash
# 叮咚到號 — 正式環境部署腳本
# 在 aaPanel 伺服器上執行
set -e

echo "========================================="
echo "  叮咚到號 — 正式環境部署"
echo "========================================="

# 1. 進入專案目錄
cd /home/linux/Dropbox/84-WebCode/00-gemini/6-linux/5-ajz/linebot-dindon || {
    echo "ERROR: 找不到專案目錄，請修改路徑"
    exit 1
}

# 2. 拉最新程式碼
echo ""
echo "[1/5] 拉取最新程式碼..."
git pull

# 3. 確認 .env 存在
if [ ! -f .env ]; then
    echo "ERROR: .env 檔案不存在，請先設定"
    exit 1
fi
echo "[OK] .env 已就緒"

# 4. 停止舊容器（包括可能殘留的 line_bot.py 容器）
echo ""
echo "[2/5] 停止舊容器..."
docker stop ajz-dindon 2>/dev/null || true
docker rm ajz-dindon 2>/dev/null || true
docker compose down 2>/dev/null || true

# 5. 建置並啟動新版
echo ""
echo "[3/5] 建置並啟動..."
docker compose up -d --build

# 6. 等待啟動
echo ""
echo "[4/5] 等待啟動..."
sleep 10

# 7. 健康檢查
echo ""
echo "[5/5] 健康檢查..."
HEALTH=$(curl -s http://localhost:8000/health)
echo "Health: $HEALTH"

if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo ""
    echo "========================================="
    echo "  部署成功！"
    echo "========================================="
    echo ""
    echo "容器狀態："
    docker compose ps
    echo ""
    echo "⚠️  還需要手動更新 Nginx："
    echo "   1. 登入 aaPanel"
    echo "   2. Website → dindon.cleanhome.tw → Configuration"
    echo "   3. 把所有 proxy_pass 的 port 從 5000 改成 8000"
    echo "   4. 或直接貼入 nginx.conf 的內容"
    echo "   5. 重啟 Nginx"
    echo ""
    echo "更新後驗證："
    echo "   curl https://dindon.cleanhome.tw/health"
else
    echo ""
    echo "WARNING: 健康檢查異常，請檢查日誌："
    echo "   docker logs medqueue-app --tail 50"
fi
