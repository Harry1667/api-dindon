"""Celery 應用設定"""

import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "medical_queue",
    broker=redis_url,
    # backend 不設定：沒有任何地方呼叫 .get()，省 Redis 寫入開銷
)

celery_app.conf.update(
    # 時區
    timezone="Asia/Taipei",

    # Celery 6.0+ 相容設定
    broker_connection_retry_on_startup=True,
    enable_utc=True,

    # 任務序列化
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # 任務超時（預設值，個別任務可覆蓋）
    # 29 家醫院序列抓取 + 部分醫院回應慢，需要較長時間
    task_soft_time_limit=600,
    task_time_limit=660,

    # 自動發現任務
    include=["app.tasks.scrape", "app.tasks.notify", "app.tasks.nhi_sync", "app.tasks.sync_master_data", "app.tasks.test_scheduler", "app.tasks.maintenance", "app.tasks.metrics"],

    # 路由：notify 用獨立 queue，不被爬蟲擋住
    task_routes={
        "app.tasks.notify.check_and_notify": {"queue": "notify"},
    },

    # 定時排程 (Celery Beat)
    beat_schedule={
        # 每 60 秒抓取看診進度
        "scrape-all-hospitals": {
            "task": "app.tasks.scrape.scrape_all_hospitals",
            "schedule": int(os.getenv("SCRAPE_INTERVAL_SECONDS", "60")),
        },
        # 每 60 秒檢查通知（走 notify queue）
        "check-and-notify": {
            "task": "app.tasks.notify.check_and_notify",
            "schedule": int(os.getenv("SCRAPE_INTERVAL_SECONDS", "60")),
            "options": {"queue": "notify"},
        },
        # 每天凌晨 3 點同步 NHI 醫事機構資料
        "sync-nhi-daily": {
            "task": "app.tasks.nhi_sync.sync_nhi_institutions",
            "schedule": crontab(hour=3, minute=0),
        },
        # 每天凌晨 4 點同步診科/醫生主檔（從各醫院爬蟲提取）
        "sync-master-data-daily": {
            "task": "app.tasks.sync_master_data.sync_master_data",
            "schedule": crontab(hour=4, minute=0),
        },
        # 每分鐘檢查排程測試
        "check-test-schedule": {
            "task": "app.tasks.test_scheduler.check_scheduled_test",
            "schedule": 60,
        },
        # 每天凌晨 1 點統計診間開關診時間（累積足夠資料後可取代即時爬蟲判斷）
        "build-clinic-schedule-daily": {
            "task": "app.tasks.maintenance.build_clinic_schedule",
            "schedule": crontab(hour=1, minute=0),
        },
        # 每天凌晨 2 點清理超過 7 天的 clinic_progress 舊資料
        "cleanup-old-progress-daily": {
            "task": "app.tasks.maintenance.cleanup_old_progress",
            "schedule": crontab(hour=2, minute=0),
        },
        # 每分鐘收集系統指標（壓力負載圖）
        "collect-metrics-every-minute": {
            "task": "app.tasks.metrics.collect_metrics",
            "schedule": 60,
        },
    },
)
