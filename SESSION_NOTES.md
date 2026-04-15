# Session Notes

## 2026-04-14

### 完成的事

**伺服器效能優化（aaPanel / Docker）**
- Swap 949MB → 5MB（清空）
- 磁碟 80% → 76%（清 Docker 廢棄 image 釋出 3GB）
- 移除孤兒 Celery 進程（3個→1個）
- journald 上限設 50M、/var/log 清理
- vm.swappiness 臨時設為 10（尚未永久化 → task #12）

**medqueue 本項目優化**
- `clinic_progress.clinic_room`：VARCHAR(100) → VARCHAR(255)（ALTER TABLE 已執行）
- `doctors.clinic_room`：VARCHAR(20) → TEXT（ALTER TABLE 已執行）
- 爬蟲並行化：sequential for 迴圈 → `asyncio.gather()` + Semaphore(10)，29 家醫院從 ~50s 降到 ~3-5s
- 移除 Celery result backend（沒有 .get() 用途，省 Redis 寫入）
- Redis AOF/RDB 關閉（任務佇列不需持久化）
- Celery -B beat 拆出獨立容器 `medqueue-beat`
- 加入 Flower 監控容器 `medqueue-flower`（127.0.0.1:5559）
- Worker healthcheck 加入
- docker-compose.yml 移除 `version: "3.8"` 廢棄屬性
- 修 Celery broker_connection_retry_on_startup 棄用警告

**目前運行容器（medqueue）**
| 容器 | RAM | 說明 |
|------|-----|------|
| medqueue-app | 256M 限 | FastAPI |
| medqueue-worker | 384M 限 | Celery worker（並行爬蟲）|
| medqueue-beat | 96M 限 | Celery beat（獨立排程器）|
| medqueue-flower | 96M 限 | Flower 監控（127.0.0.1:5559）|
| medqueue-redis | 96M 限 | Redis（AOF 關閉）|

### 未完成（下次從這裡繼續）

**本項目**
- [ ] task #17：設定 Flower 域名反代（aaPanel 設站點 + SSL）
  - .env 加 FLOWER_USER / FLOWER_PASSWORD
  - aaPanel 新增站點反代 → 127.0.0.1:5559

**伺服器層級（需 root 或其他專案）**
- [ ] task #10：Docker daemon.json log rotation（需 root + restart docker）
- [ ] task #12：sysctl 永久化（/etc/sysctl.d/99-tuning.conf，需 root）
- [ ] task #11：ibgateway JVM GC 執行緒數調低（ParallelGCThreads=20 → 2）
- [ ] task #7：MySQL innodb_buffer_pool_size 調優
- [ ] task #1：ajz-cleanhome-web 記憶體限制（需 root 改檔案權限）

### 重要資訊
- MySQL 連線：`mysql -h 127.0.0.1 -P 3306 -u ajz-dindon -p ajz-dindon`（socket 不存在）
- Flower SSH tunnel：`ssh -L 5559:127.0.0.1:5559 aapanel -N`，然後開 http://localhost:5559
- 伺服器：aapanel（57.182.129.192），claude 用戶無 sudo
