"""爬蟲排程任務 — 動態頻率控制"""

import asyncio
import logging
import redis as sync_redis
import os

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


def _get_redis():
    """取得同步 Redis 連線"""
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return sync_redis.from_url(redis_url, decode_responses=True)


def _should_skip(hospital_code: str) -> bool:
    """
    判斷是否跳過本次抓取
    邏輯：連續 SLOWDOWN_THRESHOLD 次沒資料後，改為每 SLOW_INTERVAL 秒才抓一次
    """
    r = _get_redis()
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


def _record_result(hospital_code: str, has_data: bool):
    """記錄抓取結果，控制頻率"""
    r = _get_redis()
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
    """抓取所有啟用醫院的看診進度（動態頻率控制）"""
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
    """非同步抓取所有醫院"""
    cache = CacheService()
    adapters = AdapterRegistry.get_all()

    for code, adapter in adapters.items():
        # 動態頻率控制：沒資料時自動降速
        if _should_skip(code):
            logger.debug(f"[scrape] {adapter.hospital_name} 降速中，跳過本次")
            continue

        try:
            logger.info(f"[scrape] 開始抓取 {adapter.hospital_name}")
            progress_list = await adapter.fetch_all_progress()

            if progress_list:
                await cache.store_progress(progress_list)

                # 同時寫入 MySQL clinic_progress 表
                try:
                    local_engine = create_async_engine(settings.database_url, echo=False)
                    local_session = async_sessionmaker(local_engine, class_=AsyncSession, expire_on_commit=False)
                    async with local_session() as session:
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
                    await local_engine.dispose()
                except Exception as db_err:
                    logger.error(f"[scrape] {adapter.hospital_name} 寫入 MySQL 失敗: {db_err}")

                logger.info(f"[scrape] {adapter.hospital_name} 完成，{len(progress_list)} 個診間")
                _record_result(code, has_data=True)
            else:
                logger.info(f"[scrape] {adapter.hospital_name} 目前沒有看診中的診間")
                _record_result(code, has_data=False)

        except Exception as e:
            logger.error(f"[scrape] {adapter.hospital_name} 抓取失敗: {e}")

    await cache.close()


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
