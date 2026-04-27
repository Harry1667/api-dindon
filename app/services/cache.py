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

    @staticmethod
    def _session_matches_now(session: str) -> bool:
        """判斷該 session 標籤是否屬於當前時段（避免寫入已結束時段的舊資料）

        時段寬鬆定義（允許延診 2-3 小時）：
          - 上午診：06:00 ~ 14:00
          - 下午診：12:00 ~ 22:30（允許延診到晚診結束）
          - 夜診  ：16:00 ~ 24:00 + 00:00 ~ 01:00
        其他無法辨識的 session 標籤一律允許（保守）。
        """
        from datetime import datetime, timezone, timedelta
        TW_TZ = timezone(timedelta(hours=8))
        now = datetime.now(TW_TZ)
        minutes = now.hour * 60 + now.minute

        s = (session or '').strip()
        if not s:
            return True

        def in_window(lo_h, lo_m, hi_h, hi_m):
            lo = lo_h * 60 + lo_m
            hi = hi_h * 60 + hi_m
            return lo <= minutes < hi

        if '上午' in s or 'morning' in s.lower():
            return in_window(6, 0, 14, 0)
        if '下午' in s or 'afternoon' in s.lower():
            return in_window(12, 0, 22, 30)
        if '夜' in s or '晚' in s or 'evening' in s.lower() or 'night' in s.lower():
            # 夜診跨午夜也允許（00:00-01:00）
            return in_window(16, 0, 24, 0) or in_window(0, 0, 1, 0)
        return True  # 未知標籤 → 放行

    async def store_progress(self, progress_list: list[ClinicProgressData]):
        """將爬蟲結果存入 Redis 快取（依當前時段過濾 + 索引集同步修剪）"""
        # 先過濾：只留「當前時段」的進度
        if progress_list:
            progress_list = [p for p in progress_list if self._session_matches_now(p.session)]

        # 取得 hospital_code：優先用 progress_list[0]，若為空則從 caller 推不出來 → 由另一個入口 store_progress_for 處理
        if not progress_list:
            return

        hospital_code = progress_list[0].hospital_code
        await self._replace_progress(hospital_code, progress_list)

    async def _replace_progress(self, hospital_code: str, progress_list: list[ClinicProgressData]):
        """完整替換某醫院的進度資料：寫入新 keys，並從 index 移除不在本次結果的舊成員"""
        try:
            PROGRESS_TTL = 600  # 10 分鐘（個別資料 TTL）
            index_key = f"index:{hospital_code}"
            new_keys = set(p.to_cache_key() for p in progress_list)

            # 先讀現有 index 成員，計算要移除的 stale keys
            old_members = await self.redis.smembers(index_key)
            stale = [m for m in old_members if m not in new_keys]

            pipe = self.redis.pipeline()

            # 寫入新資料
            for p in progress_list:
                key = p.to_cache_key()
                pipe.set(key, json.dumps(p.to_dict(), ensure_ascii=False), ex=PROGRESS_TTL)

            # 同步修剪 index：移除不在本輪結果的舊 key，加入新 key
            if stale:
                pipe.srem(index_key, *stale)
                # 順手刪掉對應資料 key（即使 TTL 還沒到）
                pipe.delete(*stale)
            if new_keys:
                pipe.sadd(index_key, *new_keys)
                pipe.expire(index_key, PROGRESS_TTL)

            await pipe.execute()
            logger.info(
                f"[cache] 已更新 {hospital_code} 共 {len(progress_list)} 筆"
                + (f"（移除 {len(stale)} 筆舊資料）" if stale else "")
            )
        except RedisError as e:
            logger.error(f"[cache] Redis 寫入失敗 {hospital_code}: {e}")
        except Exception as e:
            logger.error(f"[cache] 儲存失敗 {hospital_code}: {e}")

    async def clear_hospital(self, hospital_code: str):
        """完全清除一家醫院的 Redis 快取（當 scraper 回傳空列表時呼叫）"""
        try:
            index_key = f"index:{hospital_code}"
            members = await self.redis.smembers(index_key)
            pipe = self.redis.pipeline()
            if members:
                pipe.delete(*members)
            pipe.delete(index_key)
            await pipe.execute()
            if members:
                logger.info(f"[cache] 已清空 {hospital_code}（{len(members)} 筆）")
        except Exception as e:
            logger.error(f"[cache] 清空失敗 {hospital_code}: {e}")

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
