"""系統指標收集任務 — 每分鐘記錄一次，儲存到 Redis（最近 60 筆）+ MySQL（長期）

指標：
  redis_queue        - celery queue 積壓數
  db_writes          - 過去 1 分鐘新寫入 clinic_progress 筆數
  active_hospitals   - 過去 1 分鐘有回傳資料的醫院數
  scraper_errors     - 爬蟲失敗累計數（所有醫院 fail_count 加總）
  line_notifications - 過去 1 分鐘 LINE 通知發送數（從 Redis counter 讀取後重置）
  slowdown_hospitals - 目前降速中的醫院數（有 scrape:slow_lock:* key）
  active_tasks       - DB 中 status=active 的追蹤任務數
  scrape_duration    - 上一輪爬蟲耗時（秒，從 Redis 讀取）
  worker_mem_mb      - Worker 進程記憶體使用量（MB）
"""

import json
import logging
import os
import resource
from datetime import datetime, timezone, timedelta

import redis as sync_redis
from sqlalchemy import create_engine, text

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

METRICS_KEY = "monitor:metrics_history"   # Redis List，最多保留 60 筆
MAX_HISTORY = 60

# LINE 通知計數器 key（由 notifier 每次發送後 INCR）
LINE_NOTIFY_COUNTER_KEY = "monitor:line_notify_count"
# 爬蟲耗時 key（由 scrape_all_hospitals 記錄）
SCRAPE_DURATION_KEY = "monitor:scrape_duration"

TW_TZ = timezone(timedelta(hours=8))


def _get_redis():
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return sync_redis.from_url(redis_url, decode_responses=True)


def _get_sync_engine():
    from app.config import settings
    sync_url = (settings.database_url
                .replace("+aiomysql", "+pymysql")
                .replace("+asyncpg", "+psycopg2"))
    return create_engine(sync_url, pool_pre_ping=True,
                         connect_args={"init_command": "SET time_zone='+08:00'"})


@celery_app.task(name="app.tasks.metrics.collect_metrics")
def collect_metrics():
    """每分鐘收集一次系統指標，存入 Redis + MySQL"""
    r = _get_redis()
    now = datetime.now(TW_TZ)

    metrics = {
        "ts": now.strftime("%H:%M"),
        "ts_epoch": int(now.timestamp()),
        "redis_queue": 0,
        "db_writes": 0,
        "active_hospitals": 0,
        "scraper_errors": 0,
        "line_notifications": 0,
        "slowdown_hospitals": 0,
        "active_tasks": 0,
        "scrape_duration": 0,
        "worker_mem_mb": 0,
    }

    # 1. Redis queue 積壓數
    try:
        metrics["redis_queue"] = r.llen("celery") + r.llen("notify")
    except Exception:
        pass

    # 2. LINE 通知數（讀取後重置計數器）
    try:
        count = r.getdel(LINE_NOTIFY_COUNTER_KEY)
        metrics["line_notifications"] = int(count or 0)
    except Exception:
        pass

    # 3. 降速中的醫院數
    try:
        slow_keys = list(r.scan_iter("scrape:slow_lock:*"))
        metrics["slowdown_hospitals"] = len(slow_keys)
    except Exception:
        pass

    # 4. 爬蟲耗時
    try:
        dur = r.get(SCRAPE_DURATION_KEY)
        metrics["scrape_duration"] = int(float(dur or 0))
    except Exception:
        pass

    # 5. 爬蟲錯誤累計
    try:
        fail_keys = list(r.scan_iter("scrape:fail_count:*"))
        metrics["scraper_errors"] = sum(int(r.get(k) or 0) for k in fail_keys)
    except Exception:
        pass

    # 6. Worker 記憶體（自身進程）
    try:
        mem_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux: KB, macOS: bytes
        metrics["worker_mem_mb"] = mem_bytes // 1024 if mem_bytes > 1_000_000 else mem_bytes // 1
    except Exception:
        pass

    # 7. DB 查詢（寫入數、活躍醫院、active 任務數）
    try:
        engine = _get_sync_engine()
        with engine.connect() as conn:
            r1 = conn.execute(text(
                "SELECT COUNT(*), COUNT(DISTINCT hospital_code) FROM clinic_progress "
                "WHERE fetched_at >= NOW() - INTERVAL 1 MINUTE"
            )).fetchone()
            metrics["db_writes"] = r1[0] or 0
            metrics["active_hospitals"] = r1[1] or 0

            r2 = conn.execute(text(
                "SELECT COUNT(*) FROM tracking_task WHERE status = 'active'"
            )).fetchone()
            metrics["active_tasks"] = r2[0] or 0
        engine.dispose()
    except Exception as e:
        logger.debug(f"[metrics] DB 查詢失敗: {e}")

    # 存入 Redis（最新 60 筆）
    try:
        r.lpush(METRICS_KEY, json.dumps(metrics))
        r.ltrim(METRICS_KEY, 0, MAX_HISTORY - 1)
        r.expire(METRICS_KEY, 7200)
    except Exception as e:
        logger.error(f"[metrics] 寫入 Redis 失敗: {e}")

    # 存入 MySQL（長期保留）— 補洞：若前幾分鐘有 gap 也補 0 值進去
    try:
        engine = _get_sync_engine()
        with engine.connect() as conn:
            # 查最後一筆記錄時間，補齊中間缺失的分鐘（最多補 60 分鐘）
            last_row = conn.execute(text(
                "SELECT MAX(recorded_at) FROM system_metrics"
            )).scalar()

            rows_to_insert = []
            if last_row:
                gap_minutes = int((now.replace(tzinfo=None) - last_row).total_seconds() // 60)
                # 若 gap > 1 分鐘且 <= 60 分鐘，補 0 值填洞
                for i in range(min(gap_minutes - 1, 60), 0, -1):
                    fill_ts = now.replace(tzinfo=None) - timedelta(minutes=i)
                    rows_to_insert.append({
                        "ts": fill_ts,
                        "q": 0, "w": 0, "h": 0, "e": 0,
                        "ln": 0, "sh": 0, "at": 0, "sd": 0, "wm": 0,
                    })

            # 加上本分鐘的實際資料
            rows_to_insert.append({
                "ts": now.replace(tzinfo=None),
                "q": metrics["redis_queue"],
                "w": metrics["db_writes"],
                "h": metrics["active_hospitals"],
                "e": metrics["scraper_errors"],
                "ln": metrics["line_notifications"],
                "sh": metrics["slowdown_hospitals"],
                "at": metrics["active_tasks"],
                "sd": metrics["scrape_duration"],
                "wm": metrics["worker_mem_mb"],
            })

            insert_sql = text(
                "INSERT INTO system_metrics "
                "(recorded_at, redis_queue, db_writes, active_hospitals, scraper_errors, "
                " line_notifications, slowdown_hospitals, active_tasks, scrape_duration, worker_mem_mb) "
                "VALUES (:ts, :q, :w, :h, :e, :ln, :sh, :at, :sd, :wm)"
            )
            for row in rows_to_insert:
                conn.execute(insert_sql, row)
            conn.commit()

            if len(rows_to_insert) > 1:
                logger.info(f"[metrics] 補寫 {len(rows_to_insert)-1} 筆空白紀錄")
        engine.dispose()
    except Exception as e:
        logger.error(f"[metrics] 寫入 DB 失敗: {e}")
    finally:
        r.close()

    logger.debug(f"[metrics] {now.strftime('%H:%M')} {metrics}")
