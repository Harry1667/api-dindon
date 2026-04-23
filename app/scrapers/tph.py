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
from app.config import settings

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

BASE_URL = "https://nreg.tph.mohw.gov.tw/OReg"


class MohwOregAdapter(BaseHospitalAdapter):
    """衛福部醫院通用 Adapter — OReg 系統 JSON API

    適用於使用 OReg 掛號系統的衛福部醫院：
    - 臺北醫院: nreg.tph.mohw.gov.tw
    - 豐原醫院: nreg.fyh.mohw.gov.tw
    - 未來可擴展更多
    """

    def __init__(self, hospital_code: str, hospital_name: str, domain: str):
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.domain = domain
        self.base_url = f"https://{domain}/OReg/VisitProgressPage"
        self._api_base = f"https://{domain}/OReg"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        now = datetime.now(TW_TZ)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self._api_base}/VisitProgressPage",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False, proxy=settings.socks5_proxy or None) as client:
                # 先建立 session
                await client.get(self.base_url, headers={
                    "User-Agent": headers["User-Agent"],
                })

                # 取得看診進度
                resp = await client.post(
                    f"{self._api_base}/GetVisitedProcess",
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
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False, proxy=settings.socks5_proxy or None) as client:
                await client.get(self.base_url)
                resp = await client.post(
                    f"{self._api_base}/GetSectCategoryList",
                    data={},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                data = resp.json()
                return [d.get("sectsuname", "") for d in data if d.get("sectsuname")]
        except Exception:
            return []


# 向後相容
TphAdapter = MohwOregAdapter

# === 預建醫院實例 ===
tph_adapter = MohwOregAdapter("tph", "衛福部臺北醫院", "nreg.tph.mohw.gov.tw")
fyh_adapter = MohwOregAdapter("fyh-mohw", "衛福部豐原醫院", "nreg.fyh.mohw.gov.tw")
