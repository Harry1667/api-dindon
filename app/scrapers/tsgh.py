"""三軍總醫院看診進度 Adapter

資料來源：https://www2.ndmutsgh.edu.tw/NumberStatus/data/cache.json
技術：靜態 JSON 檔案（每 30 秒更新）
注意：域名從 www2.ndmctsgh.edu.tw 已遷移至 www2.ndmutsgh.edu.tw

JSON 結構：
{
    "lastUpdated": "2026-03-29 12:29:03",
    "visit": [                          ← 看診進度（主院區：內湖/汀州）
        {
            "Key": "內湖-內科",
            "Division": "內科",
            "Doctor": "王大明",
            "Room": "101診",
            "Session": "上午",
            "Current": "25",
            "Next": "26",
            "Status": "看診中"
        }
    ],
    "visitTCB": { "data": [...] },      ← 台北門診中心（不同欄位格式）
    "pharmacy": [...],                   ← 領藥進度
    "registration": [...],              ← 批價掛號
    "surgery": [...]                    ← 手術進度
}

visit 的 Key 格式："院區-科別"，以「內湖-」或「汀州-」開頭
visitTCB 的欄位：branch_id, department_name, doctor_name, room_name, curr_number, next_number
"""

import logging
from datetime import datetime, timezone, timedelta

import httpx

from app.scrapers.base import BaseHospitalAdapter
from app.schemas.clinic import ClinicProgressData

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

CACHE_URL = "https://www2.ndmutsgh.edu.tw/NumberStatus/data/cache.json"

SESSION_MAP = {
    "上午": "上午診",
    "下午": "下午診",
    "夜間": "夜診",
    "夜": "夜診",
}


class TsghAdapter(BaseHospitalAdapter):
    """三軍總醫院 Adapter — 讀取靜態 JSON 快取檔"""

    hospital_code = "tsgh"
    hospital_name = "三軍總醫院"
    base_url = CACHE_URL

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        now = datetime.now(TW_TZ)

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    CACHE_URL,
                    headers={"User-Agent": "Mozilla/5.0"},
                    # 加時間戳避免快取
                    params={"t": str(int(now.timestamp()))},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"[{self.hospital_code}] JSON 請求失敗: {e}")
            return []
        except Exception as e:
            logger.error(f"[{self.hospital_code}] JSON 解析失敗: {e}")
            return []

        all_results = []
        date_str = now.strftime("%Y/%m/%d")

        # 1. 處理 visit（內湖/汀州）
        visit = data.get("visit")
        if visit and isinstance(visit, list):
            for item in visit:
                try:
                    progress = self._parse_visit(item, date_str, now)
                    if progress:
                        all_results.append(progress)
                except Exception as e:
                    logger.warning(f"[{self.hospital_code}] 解析 visit 失敗: {e}")

        # 2. 處理 visitTCB（台北門診中心）
        visit_tcb = data.get("visitTCB", {})
        tcb_data = visit_tcb.get("data", []) if isinstance(visit_tcb, dict) else []
        if tcb_data and isinstance(tcb_data, list):
            for item in tcb_data:
                try:
                    progress = self._parse_visit_tcb(item, date_str, now)
                    if progress:
                        all_results.append(progress)
                except Exception as e:
                    logger.warning(f"[{self.hospital_code}] 解析 visitTCB 失敗: {e}")

        logger.info(f"[{self.hospital_code}] 取得 {len(all_results)} 個診間")
        return all_results

    def _parse_visit(
        self, item: dict, date_str: str, now: datetime
    ) -> ClinicProgressData | None:
        """解析主院區看診進度（內湖/汀州）"""
        division = (item.get("Division") or "").strip()
        doctor = (item.get("Doctor") or "").strip()
        room = (item.get("Room") or "").strip()
        current_str = str(item.get("Current") or "0")
        next_str = str(item.get("Next") or "0")

        current_number = int(current_str) if current_str.isdigit() else 0
        next_number = int(next_str) if next_str.isdigit() else 0

        if current_number == 0 and next_number == 0:
            return None

        # 午別
        session_raw = (item.get("Session") or "").strip()
        session = SESSION_MAP.get(session_raw, session_raw or "未知")

        # 院區
        key = (item.get("Key") or "").strip()
        branch = ""
        if key.startswith("內湖-"):
            branch = "內湖"
        elif key.startswith("汀州-"):
            branch = "汀州"

        dept_name = f"{branch}{division}" if branch else division

        return ClinicProgressData(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            date=date_str,
            session=session,
            department=dept_name or "未知",
            doctor_name=doctor,
            clinic_room=room or dept_name or "未知",
            current_number=current_number,
            next_number=next_number,
            is_current_skipped=False,
            is_next_skipped=False,
            fetched_at=now,
        )

    def _parse_visit_tcb(
        self, item: dict, date_str: str, now: datetime
    ) -> ClinicProgressData | None:
        """解析台北門診中心看診進度"""
        department = (item.get("department_name") or "").strip()
        doctor = (item.get("doctor_name") or "").strip()
        room = (item.get("room_name") or "").strip()
        current_str = str(item.get("curr_number") or "0")
        next_str = str(item.get("next_number") or "0")

        current_number = int(current_str) if current_str.isdigit() else 0
        next_number = int(next_str) if next_str.isdigit() else 0

        if current_number == 0 and next_number == 0:
            return None

        # 午別
        hours_id = str(item.get("hours_id") or "")
        if hours_id == "1":
            session = "上午診"
        elif hours_id == "2":
            session = "下午診"
        elif hours_id == "3":
            session = "夜診"
        else:
            session = "未知"

        return ClinicProgressData(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            date=date_str,
            session=session,
            department=f"台北門診{department}" if department else "台北門診中心",
            doctor_name=doctor,
            clinic_room=room or department or "未知",
            current_number=current_number,
            next_number=next_number,
            is_current_skipped=False,
            is_next_skipped=False,
            fetched_at=now,
        )

    async def get_departments(self) -> list[str]:
        all_progress = await self.fetch_all_progress()
        return sorted(set(p.department for p in all_progress))
