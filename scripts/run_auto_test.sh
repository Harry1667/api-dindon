#!/bin/bash
# 自動測試 wrapper — 在測試環境 Docker 容器內執行
# 由 cron 呼叫

PROJECT_DIR="/home/linux/Dropbox/84-WebCode/00-gemini/6-linux/5-ajz/linebot-dindon"
LOG_DIR="$PROJECT_DIR/logs/test_reports"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M)
LOG_FILE="$LOG_DIR/${TIMESTAMP}_cron.log"

echo "===== 自動測試開始 $(date) =====" >> "$LOG_FILE"

# 確認測試容器在跑
if ! docker ps --format '{{.Names}}' | grep -q dindon-dev-app; then
    echo "ERROR: dindon-dev-app 容器未啟動" >> "$LOG_FILE"
    exit 1
fi

# 在 app 容器內執行測試腳本
docker exec dindon-dev-app python3 scripts/auto_test.py --all >> "$LOG_FILE" 2>&1

echo "===== 自動測試結束 $(date) =====" >> "$LOG_FILE"
