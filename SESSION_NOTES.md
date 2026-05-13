# Session Notes

## 2026-04-27 ~ 05-01(/simple 老人版 + 監控)

### 完成的事

**🚨 Critical bug 修復(已部署)**
- `public/simple/tracking.html` 第 590 行重複 `const my` 宣告 → SyntaxError → 整個 inline script 不執行
- 修法:刪重複的 `const cur`/`const my`,用上面已存在的 `newCur` / `my`
- commit 8eb4e63
- 影響:tracking 頁面從沒運作過,所有用戶看到「—」(過號自動結束、音效、停止追蹤按鈕都失效)

**後端修復(commit 4ddbf60)**
- `app/services/cache.py:_session_matches_now()`:上午(06-14)/下午(12-22:30)/夜診(16-24+00-01) 過濾,避免存已結束時段的舊資料
- `_replace_progress()`:比對新舊 keys,srem stale + delete,解決 SCARD 因殘留謊報 open
- `clear_hospital()`:scraper 抓回空時呼叫,完整清空
- 新增 `GET /api/hospitals/status`(前端用來判斷醫院/科別是否休診中)

**前端 /simple 老人友善版(commit d694570)**
- `simple.js` 共用 lib:多筆追蹤(免費 1 / Pro 3,hard limit)、自訂 dialog、WebAudio 音效、點擊次數排序、HOSPITAL_SPLITS(三軍拆 3 院區)
- `index.html`:追蹤卡片 left/right flex 顯示即時號碼差,30 秒輪詢 + 60 秒刷醫院狀態,警戒區音效
- `dept.html`:用 progress 抓 active depts,休診的灰掉
- `enter.html`:1 頁無捲動鍵盤,追蹤上限 hard limit
- `simple.css`:layout-fixed / two-col / info-hero / lt-card / dd-modal

**監控系統(.gstack/qa-reports/)**
- `system-check.sh`:從用戶視角 review(不只 count),抽 10 家深度檢查
  - 偵測:前後端矛盾、session 跟現在時段不符、資料 8 分鐘沒更新、cur 全 0、號碼倒退/卡死、來源停更
  - 過號 = LOW(正常現象);大規模 + 大落差倒退 = MED;全院 0 開診(非夜間/假日) = CRIT
  - 含 TW 假日 / 週日 / 22:00-07:00 夜間休爬 自動降級
- 5 分鐘 cron 累積 jsonl 趨勢,Snapshot 比對偵測倒退/卡死
- 過 5/1 勞動節成功識別為假日模式

### 驗證範圍

跨 5 天(4/27 ~ 5/1)5 分鐘 cron 連續監控:
- ✅ 上午/下午/夜診 session 切換乾淨
- ✅ 22:00 後 cache TTL 10 min 內全院歸 0
- ✅ 過號(順號→過號→順號)是 TW 醫院真實現象,不是 bug
- ✅ 29 個註冊爬蟲 = 前端 31 卡(tsgh 拆 3 院區),0 重複
- ⚠️ tcvgh 來源偶爾 503 → scraper 抓 0 → 自動清快取 → 用戶看到休診(系統行為正確,但用戶該時段查不到台中榮總)
- ⚠️ femh 醫師名字偶爾亂碼字元 `朱韻�`(big5↔utf-8 編碼問題)
- ⚠️ ntuh-cancer 過號率全院最高,常觸發 MED

### 未完成(下次從這裡繼續)

**可優化(不是 bug,但用戶體驗會更好)**
- [ ] 時段切換主動清 cache:14:00/17:00 切換時不等下一輪 scrape,直接清舊時段 keys(目前用戶會看到 ~5 分鐘的「上午診」舊資料)
- [ ] tracking.html 用 `max(cur_history)` 平滑過號跳動的 UI 閃爍(過號叫到時 31→5 會讓「已過號 / 看診中」狀態反覆切)
- [ ] femh scraper 編碼處理(big5),過濾 `--已下診` 之類的尾綴標籤
- [ ] femh scraper 加合理性檢查(cur=501 這種異常值)
- [ ] tcvgh 來源 503 重試機制(目前單次失敗就清快取)

### 重要資訊

- 監控腳本:`.gstack/qa-reports/system-check.sh`(已 gitignore)
- 累積記錄:`.gstack/qa-reports/system-checks.jsonl`(jsonl 趨勢)
- Snapshot:`.gstack/qa-reports/last-snapshot.json`(跨輪比較倒退用)
- 監控啟動法:`CronCreate cron='3,8,13,18,23,28,33,38,43,48,53,58 * * * *'`(每 5 分,避開 :00/:30)
- 24/7 真正部署請改用 NAS / aapanel 自己的 crontab(目前 cron 只活在 Claude session 中,7 天過期)

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
