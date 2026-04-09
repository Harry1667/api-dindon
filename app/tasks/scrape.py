"""爬蟲排程任務 — 動態頻率控制 + 休診時段自動停止

休診規則（台灣時間 Asia/Taipei）：
  - 每天 22:00 ~ 隔天 07:00 停止爬蟲（夜間無看診）
  - 週日全天停止（大多數醫院週日休診）
  - 台灣國定假日停止（農曆新年、清明、端午等）
  Celery Beat 仍每 60 秒觸發，但 task 自行判斷是否在看診時段。
"""

import asyncio
import logging
import redis as sync_redis
import os
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.tasks.celery_app import celery_app
from app.scrapers.registry import AdapterRegistry
from app.services.cache import CacheService
from app.config import settings
from app.models.clinic_progress import ClinicProgress

logger = logging.getLogger(__name__)

# Redis key 用來追蹤連續空結果次數
EMPTY_COUNT_KEY = "scrape:empty_count:{code}"
# 連續空結果次數門檻 → 降速
SLOWDOWN_THRESHOLD = 3
# 降速後的間隔（秒）：5 分鐘檢查一次有沒有恢復看診
SLOW_INTERVAL = 300

# === 休診時段設定 ===
SCRAPE_START_HOUR = 7   # 早上 7 點開始爬蟲
SCRAPE_END_HOUR = 22    # 晚上 10 點停止爬蟲
SKIP_SUNDAY = True       # 週日停止

# 台灣國定假日（每年更新，格式 MM-DD 或完整日期 YYYY-MM-DD）
# 固定日期用 MM-DD，農曆假日用完整日期（需每年手動更新）
TW_HOLIDAYS_FIXED = {
    "01-01",  # 元旦
    "02-28",  # 和平紀念日
    "04-04",  # 兒童節
    "04-05",  # 清明節（大部分年份）
    "05-01",  # 勞動節
    "10-10",  # 國慶日
}

# 2026 年農曆假日（每年需更新）
TW_HOLIDAYS_2026 = {
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-21",  # 農曆新年
    "2026-02-22", "2026-02-23",  # 農曆新年（含調整假）
    "2026-05-31",  # 端午節
    "2026-10-06",  # 中秋節
}


def _is_clinic_hours() -> bool:
    """判斷現在是否在看診時段（台灣時間）

    回傳 True = 應該爬蟲，False = 休診時段，跳過
    """
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Taipei"))

    # 夜間停止（22:00 ~ 07:00）
    if now.hour >= SCRAPE_END_HOUR or now.hour < SCRAPE_START_HOUR:
        return False

    # 週日停止
    if SKIP_SUNDAY and now.weekday() == 6:
        return False

    # 台灣國定假日
    today_mmdd = now.strftime("%m-%d")
    today_full = now.strftime("%Y-%m-%d")

    if today_mmdd in TW_HOLIDAYS_FIXED:
        return False
    if today_full in TW_HOLIDAYS_2026:
        return False

    return True


def _get_redis():
    """取得同步 Redis 連線（僅供 scrape_all_hospitals 鎖用，其他場景用共用 client）"""
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return sync_redis.from_url(redis_url, decode_responses=True)


def _should_skip(r, hospital_code: str) -> bool:
    """
    判斷是否跳過本次抓取（接收共用 Redis client）
    邏輯：連續 SLOWDOWN_THRESHOLD 次沒資料後，改為每 SLOW_INTERVAL 秒才抓一次
    """
    empty_count = int(r.get(EMPTY_COUNT_KEY.format(code=hospital_code)) or 0)

    if empty_count < SLOWDOWN_THRESHOLD:
        return False

    # 已進入降速模式，用 Redis SET NX + TTL 當作計時器
    lock_key = f"scrape:slow_lock:{hospital_code}"
    # 如果 lock 存在，代表還沒到下次抓取時間 → 跳過
    if r.exists(lock_key):
        return True

    # 設定 lock，SLOW_INTERVAL 秒後過期 → 下次才會再抓
    r.setex(lock_key, SLOW_INTERVAL, "1")
    return False


def _record_result(r, hospital_code: str, has_data: bool):
    """記錄抓取結果，控制頻率（接收共用 Redis client）"""
    key = EMPTY_COUNT_KEY.format(code=hospital_code)

    if has_data:
        # 有資料 → 重置計數，恢復正常頻率
        r.delete(key)
        r.delete(f"scrape:slow_lock:{hospital_code}")
        logger.info(f"[scrape] {hospital_code} 有看診資料，恢復正常抓取頻率")
    else:
        # 沒資料 → 計數 +1
        count = r.incr(key)
        # 設定 24 小時過期，避免永久殘留
        r.expire(key, 86400)
        if count == SLOWDOWN_THRESHOLD:
            logger.info(
                f"[scrape] {hospital_code} 連續 {count} 次沒資料，"
                f"降速為每 {SLOW_INTERVAL // 60} 分鐘抓一次"
            )


def _run_async(coro):
    """在 Celery worker (sync) 中執行 async 函式"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.scrape.scrape_all_hospitals", bind=True, max_retries=3)
def scrape_all_hospitals(self):
    """抓取所有啟用醫院的看診進度（動態頻率控制 + 休診時段跳過）"""
    # 休診時段直接跳過（夜間、週日、國定假日）
    if not _is_clinic_hours():
        return

    # 用 Redis 鎖防止多個 task 同時跑
    r = _get_redis()
    lock_key = "scrape:running_lock"
    if not r.set(lock_key, "1", nx=True, ex=300):
        logger.info("[scrape] 上一輪還在跑，跳過本次")
        return
    try:
        _run_async(_scrape_all())
    except Exception as exc:
        logger.error(f"爬蟲任務失敗: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=10)
    finally:
        r.delete(lock_key)


async def _scrape_all():
    """非同步抓取所有醫院

    連線管理：一個 scrape cycle 共用一個 DB engine 和一個 sync Redis client，
    避免每家醫院都建新連線（30 家 = 原本 30 個 engine + 60 個 Redis 連線）。
    """
    cache = CacheService()
    adapters = AdapterRegistry.get_all()

    # 共用 DB engine — 整個 cycle 只建一次
    db_engine = create_async_engine(settings.database_url, echo=False)
    db_session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    # 共用 sync Redis client — 頻率控制用
    r = _get_redis()

    try:
        for code, adapter in adapters.items():
            # 動態頻率控制：沒資料時自動降速
            if _should_skip(r, code):
                logger.debug(f"[scrape] {adapter.hospital_name} 降速中，跳過本次")
                continue

            try:
                logger.info(f"[scrape] 開始抓取 {adapter.hospital_name}")
                progress_list = await adapter.fetch_all_progress()

                if progress_list:
                    await cache.store_progress(progress_list)

                    # 同時寫入 MySQL clinic_progress 表
                    try:
                        async with db_session_factory() as session:
                            for p in progress_list:
                                session.add(ClinicProgress(
                                    hospital_code=p.hospital_code,
                                    date=p.date,
                                    session=p.session,
                                    department=p.department,
                                    doctor_name=p.doctor_name,
                                    clinic_room=p.clinic_room,
                                    current_number=p.current_number,
                                    next_number=p.next_number,
                                    is_current_skipped=p.is_current_skipped,
                                    is_next_skipped=p.is_next_skipped,
                                    fetched_at=p.fetched_at,
                                ))
                            await session.commit()
                    except Exception as db_err:
                        logger.error(f"[scrape] {adapter.hospital_name} 寫入 MySQL 失敗: {db_err}")

                    logger.info(f"[scrape] {adapter.hospital_name} 完成，{len(progress_list)} 個診間")
                    _record_result(r, code, has_data=True)
                    # 重置失敗計數
                    try:
                        r.delete(f"scrape:fail_count:{code}")
                    except Exception:
                        pass
                else:
                    logger.info(f"[scrape] {adapter.hospital_name} 目前沒有看診中的診間")
                    _record_result(r, code, has_data=False)

            except Exception as e:
                logger.error(f"[scrape] {adapter.hospital_name} 抓取失敗: {e}")
                # 連續失敗告警
                await _check_and_alert_failure(r, code, adapter.hospital_name, str(e))
    finally:
        await db_engine.dispose()
        await cache.close()
        r.close()


async def _check_and_alert_failure(r, hospital_code: str, hospital_name: str, error: str):
    """連續失敗 3 次後通知管理員（接收共用 Redis client）"""
    try:
        fail_key = f"scrape:fail_count:{hospital_code}"
        count = r.incr(fail_key)
        r.expire(fail_key, 3600)  # 1 小時過期

        if count == 3:  # 剛好第 3 次時告警
            admin_id = settings.admin_line_user_id
            if admin_id:
                from app.services.line_bot import LineBotService
                bot = LineBotService()
                await bot.push_message(admin_id, (
                    f"⚠️ 爬蟲告警\n"
                    f"{hospital_name} ({hospital_code})\n"
                    f"連續失敗 {count} 次\n"
                    f"錯誤: {error[:200]}"
                ))
                logger.warning(f"[scrape] 已通知管理員: {hospital_name} 連續失敗 {count} 次")
    except Exception as e:
        logger.error(f"[scrape] 告警發送失敗: {e}")


@celery_app.task(name="app.tasks.scrape.scrape_hospital")
def scrape_hospital(hospital_code: str):
    """抓取單一醫院的看診進度（手動觸發用，不受頻率控制）"""
    _run_async(_scrape_single(hospital_code))


async def _scrape_single(hospital_code: str):
    adapter = AdapterRegistry.get(hospital_code)
    if not adapter:
        logger.error(f"找不到 Adapter: {hospital_code}")
        return

    cache = CacheService()
    progress_list = await adapter.fetch_all_progress()
    if progress_list:
        await cache.store_progress(progress_list)
    await cache.close()
