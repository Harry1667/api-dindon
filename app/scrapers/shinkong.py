"""新光醫院看診進度 Adapter

資料來源：https://www.skh.org.tw/skh_regis/ (Angular SPA)
真實 API：https://www.skh.org.tw/regis_api/AppointmentProgress?DivisionCode={code}
科別列表：https://www.skh.org.tw/regis_api/RegistrationDivision
需要 headers：X-Request-ID, X-Date, Content-Type
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

import httpx

from app.scrapers.base import BaseHospitalAdapter
from app.schemas.clinic import ClinicProgressData

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

API_BASE = "https://www.skh.org.tw/regis_api"


class ShinkongAdapter(BaseHospitalAdapter):
    """新光醫院 Adapter — 使用 Angular SPA 背後的 REST API"""

    hospital_code = "shinkong"
    hospital_name = "新光醫院"
    base_url = API_BASE

    def _make_headers(self) -> dict:
        """產生 API 所需的自訂 headers"""
        now = datetime.now(TW_TZ)
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Request-ID": str(uuid.uuid4()),
            "X-Date": now.isoformat(),
            "Origin": "https://www.skh.org.tw",
            "Referer": "https://www.skh.org.tw/skh_regis/",
        }

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """先取科別列表，再逐一查詢看診進度"""
        now = datetime.now(TW_TZ)
        headers = self._make_headers()

        # Step 1: 取得所有子科別代碼
        division_codes = await self._fetch_division_codes(headers)
        if not division_codes:
            logger.warning(f"[{self.hospital_code}] 無法取得科別列表")
            return []

        # Step 2: 查詢每個科別的看診進度
        all_results = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for code, name in division_codes:
                try:
                    results = await self._fetch_progress(client, code, name, headers, now)
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"[{self.hospital_code}] {name}({code}) 失敗: {e}")

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_division_codes(self, headers: dict) -> list[tuple[str, str]]:
        """取得科別列表（含子科別）"""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{API_BASE}/RegistrationDivision",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 取科別列表失敗: {e}")
            return []

        if not isinstance(data, list):
            return []

        codes = []
        for group in data:
            subs = group.get("SubDivisions", [])
            for sub in subs:
                code = sub.get("DivisionCode", "")
                name = sub.get("DivisionName", "")
                if code and name:
                    codes.append((code, name))

        logger.info(f"[{self.hospital_code}] 找到 {len(codes)} 個子科別")
        return codes

    async def _fetch_progress(
        self,
        client: httpx.AsyncClient,
        division_code: str,
        division_name: str,
        headers: dict,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一科別的看診進度"""
        resp = await client.get(
            f"{API_BASE}/AppointmentProgress",
            params={"DivisionCode": division_code},
            headers=headers,
        )

        # 400 = 該科別今天沒有門診（找不到掛號限額檔）
        if resp.status_code == 400:
            return []

        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            return []

        date_str = now.strftime("%Y/%m/%d")
        results = []

        for record in data:
            try:
                progress = self._parse_record(record, division_name, date_str, now)
                if progress:
                    results.append(progress)
            except Exception as e:
                logger.warning(f"[{self.hospital_code}] 解析失敗: {e}")

        return results

    def _parse_record(
        self, record: dict, division_name: str, date_str: str, now: datetime
    ) -> ClinicProgressData | None:
        """解析單筆看診進度"""
        doctor_name = (record.get("DoctorName") or record.get("doctorName") or "").strip()
        clinic_room = (record.get("ClinicRoom") or record.get("clinicRoom") or "").strip()
        current_str = str(record.get("CurrentNumber") or record.get("currentNumber") or "0")
        current_number = int(current_str) if current_str.isdigit() else 0

        if current_number == 0:
            return None

        # 午別
        session_raw = (record.get("Session") or record.get("session") or "").strip()
        if "上午" in session_raw or "morning" in session_raw.lower():
            session = "上午診"
        elif "下午" in session_raw or "afternoon" in session_raw.lower():
            session = "下午診"
        elif "夜" in session_raw or "evening" in session_raw.lower():
            session = "夜診"
        else:
            session = session_raw or "未知"

        return ClinicProgressData(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            date=date_str,
            session=session,
            department=division_name,
            doctor_name=doctor_name,
            clinic_room=clinic_room or division_name,
            current_number=current_number,
            next_number=current_number + 1,
            is_current_skipped=False,
            is_next_skipped=False,
            fetched_at=now,
        )

    async def get_departments(self) -> list[str]:
        headers = self._make_headers()
        codes = await self._fetch_division_codes(headers)
        return [name for _, name in codes]
