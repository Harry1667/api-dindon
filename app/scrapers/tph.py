"""衛生福利部臺北醫院看診進度 Adapter

資料來源：https://nreg.tph.mohw.gov.tw/OReg/VisitProgressPage
API：POST /OReg/GetVisitedProcess → JSON array
科別：POST /OReg/GetSectCategoryList → JSON array

JSON 欄位（從 Handlebars template 推斷）：
  sectno, sectname, sectsuname, sectshowname,
  docno, docname, replacenm,
  roomno, roomname,
  visitno (目前號碼), statusname,
  kndkind, apptotal
"""

import logging
from datetime import datetime, timezone, timedelta

import httpx

from app.scrapers.base import BaseHospitalAdapter
from app.schemas.clinic import ClinicProgressData

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

BASE_URL = "https://nreg.tph.mohw.gov.tw/OReg"


class TphAdapter(BaseHospitalAdapter):
    """衛福部臺北醫院 Adapter — JSON API"""

    hospital_code = "tph"
    hospital_name = "衛福部臺北醫院"
    base_url = f"{BASE_URL}/VisitProgressPage"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        now = datetime.now(TW_TZ)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/VisitProgressPage",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
                # 先建立 session
                await client.get(self.base_url, headers={
                    "User-Agent": headers["User-Agent"],
                })

                # 取得看診進度
                resp = await client.post(
                    f"{BASE_URL}/GetVisitedProcess",
                    data={},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error(f"[{self.hospital_code}] API 請求失敗: {e}")
            return []

        if not isinstance(data, list):
            return []

        date_str = now.strftime("%Y/%m/%d")
        results = []

        for record in data:
            try:
                progress = self._parse_record(record, date_str, now)
                if progress:
                    results.append(progress)
            except Exception as e:
                logger.warning(f"[{self.hospital_code}] 解析失敗: {e}")

        logger.info(f"[{self.hospital_code}] 取得 {len(results)} 個診間")
        return results

    def _parse_record(
        self, record: dict, date_str: str, now: datetime
    ) -> ClinicProgressData | None:
        department = (record.get("sectname") or "").strip()
        doctor = (record.get("docname") or "").strip()
        room = (record.get("roomname") or record.get("roomno") or "").strip()
        visit_no = str(record.get("visitno") or "0").strip()
        current_number = int(visit_no) if visit_no.isdigit() else 0

        if current_number == 0:
            return None

        # 判斷時段
        hour = now.hour
        if hour < 12:
            session = "上午診"
        elif hour < 17:
            session = "下午診"
        else:
            session = "夜診"

        # 子科別
        sub_dept = (record.get("sectsuname") or "").strip()
        if sub_dept and sub_dept != department:
            department = f"{sub_dept}-{department}"

        return ClinicProgressData(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            date=date_str,
            session=session,
            department=department or "未知",
            doctor_name=doctor,
            clinic_room=room or department or "未知",
            current_number=current_number,
            next_number=current_number + 1,
            is_current_skipped=False,
            is_next_skipped=False,
            fetched_at=now,
        )

    async def get_departments(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
                await client.get(self.base_url)
                resp = await client.post(
                    f"{BASE_URL}/GetSectCategoryList",
                    data={},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                data = resp.json()
                return [d.get("sectsuname", "") for d in data if d.get("sectsuname")]
        except Exception:
            return []
