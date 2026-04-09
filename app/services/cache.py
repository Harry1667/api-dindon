"""Redis 快取服務 — 管理即時看診進度快取

錯誤處理策略：
  - 所有 Redis 操作都有 try/except
  - Redis 斷線時回傳空結果，不讓系統掛掉
  - 連線超時 5 秒，避免永遠卡住
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.config import settings
from app.schemas.clinic import ClinicProgressData

logger = logging.getLogger(__name__)


class CacheService:
    """Redis 快取管理，含錯誤處理和超時保護"""

    def __init__(self):
        self.redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )

    async def store_progress(self, progress_list: list[ClinicProgressData]):
        """將爬蟲結果存入 Redis 快取"""
        if not progress_list:
            return

        hospital_code = progress_list[0].hospital_code
        try:
            pipe = self.redis.pipeline()

            # 不清除舊資料，只更新有抓到的診間（MERGE 邏輯）
            # 這樣即使某次爬蟲漏抓某些科別，之前的資料不會消失
            # 每筆資料有 10 分鐘 TTL，超時自然過期
            PROGRESS_TTL = 600  # 10 分鐘（2 次爬蟲週期的緩衝）

            # 寫入新資料（覆蓋或新增）
            for p in progress_list:
                key = p.to_cache_key()
                pipe.set(key, json.dumps(p.to_dict(), ensure_ascii=False), ex=PROGRESS_TTL)

            # 更新醫院索引：加入新的 key，不刪除舊的（靠 TTL 自然淘汰）
            index_key = f"index:{hospital_code}"
            room_keys = [p.to_cache_key() for p in progress_list]
            if room_keys:
                pipe.sadd(index_key, *room_keys)
                pipe.expire(index_key, PROGRESS_TTL)

            await pipe.execute()
            logger.info(f"[cache] 已更新 {hospital_code} 共 {len(progress_list)} 筆")
        except RedisError as e:
            logger.error(f"[cache] Redis 寫入失敗 {hospital_code}: {e}")
        except Exception as e:
            logger.error(f"[cache] 儲存失敗 {hospital_code}: {e}")

    async def get_all_progress(self, hospital_code: str) -> list[ClinicProgressData]:
        """取得某醫院所有診間的即時進度（用 mget 批量取，2 次 round trip）"""
        try:
            index_key = f"index:{hospital_code}"
            room_keys = await self.redis.smembers(index_key)

            if not room_keys:
                return []

            # 用 mget 一次取完，避免逐一 GET 的 N+1 round trip
            values = await self.redis.mget(*room_keys)

            results = []
            for data in values:
                if not data:  # key 已過期（TTL 不同步），跳過
                    continue
                d = json.loads(data)
                results.append(ClinicProgressData(
                    hospital_code=d["hospital_code"],
                    hospital_name=d["hospital_name"],
                    date=d["date"],
                    session=d["session"],
                    department=d["department"],
                    doctor_name=d["doctor_name"],
                    clinic_room=d["clinic_room"],
                    current_number=d["current_number"],
                    next_number=d["next_number"],
                    is_current_skipped=d["is_current_skipped"],
                    is_next_skipped=d["is_next_skipped"],
                    fetched_at=__import__("datetime").datetime.fromisoformat(d["fetched_at"]),
                ))

            return results
        except RedisError as e:
            logger.error(f"[cache] Redis 讀取失敗 {hospital_code}: {e}")
            return []
        except Exception as e:
            logger.error(f"[cache] 讀取失敗 {hospital_code}: {e}")
            return []

    async def search_progress(
        self,
        hospital_code: str,
        department: str | None = None,
        doctor_name: str | None = None,
        clinic_room: str | None = None,
    ) -> list[ClinicProgressData]:
        """搜尋符合條件的診間進度"""
        all_progress = await self.get_all_progress(hospital_code)

        results = []
        for p in all_progress:
            if department and department not in p.department:
                continue
            if doctor_name and doctor_name not in p.doctor_name:
                continue
            if clinic_room and clinic_room not in p.clinic_room:
                continue
            results.append(p)

        return results

    async def is_healthy(self) -> bool:
        """檢查 Redis 連線是否正常"""
        try:
            await self.redis.ping()
            return True
        except (RedisError, Exception):
            return False

    async def close(self):
        try:
            await self.redis.close()
        except Exception:
            pass
