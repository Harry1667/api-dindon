"""輔仁大學附設醫院看診進度 Adapter

資料來源：https://www.hospital.fju.edu.tw/Process
科別 API：POST /Team/QueryList → JSON [{OPDSECTION, SECTIONNMC, SECTIONGROUPNAME}]
查詢方式：POST /Process → HTML（帶 SectionID + strOPDTIMEFLAG）
"""

import logging
import re
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup

from app.scrapers.base import BaseHospitalAdapter
from app.schemas.clinic import ClinicProgressData

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

BASE_URL = "https://www.hospital.fju.edu.tw"

SESSION_MAP = {"A": "上午診", "P": "下午診", "N": "夜診"}


class FjuhAdapter(BaseHospitalAdapter):
    """輔仁大學附設醫院 Adapter"""

    hospital_code = "fjuh"
    hospital_name = "輔大醫院"
    base_url = f"{BASE_URL}/Process"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        now = datetime.now(TW_TZ)
        hour = now.hour
        if hour < 12:
            active_sessions = ["A"]
        elif hour < 17:
            active_sessions = ["A", "P"]
        else:
            active_sessions = ["P", "N"]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        all_results = []
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
            # 建立 session
            await client.get(self.base_url, headers=headers)

            # 取得科別
            sections = await self._fetch_sections(client, headers)
            if not sections:
                return []

            for session_code in active_sessions:
                for sect_code, sect_name in sections:
                    try:
                        results = await self._fetch_progress(
                            client, sect_code, sect_name, session_code, headers, now
                        )
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(f"[{self.hospital_code}] {sect_name} {session_code}: {e}")

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_sections(self, client, headers) -> list[tuple[str, str]]:
        try:
            # IIS 對 application/x-www-form-urlencoded + 無 body 會回 411。
            # 顯式帶 content=b"" + Content-Length: 0 避開。
            resp = await client.post(
                f"{BASE_URL}/Team/QueryList",
                content=b"",
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Content-Length": "0",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            sections = []
            for d in data:
                code = (d.get("OPDSECTION") or "").strip()
                name = (d.get("SECTIONNMC") or "").strip()
                if code and name and name not in ("內科部", "外科部"):
                    sections.append((code, name))
            logger.info(f"[{self.hospital_code}] {len(sections)} 科別")
            return sections
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 取科別失敗: {e}")
            return []

    async def _fetch_progress(self, client, sect_code, sect_name, session_code, headers, now):
        resp = await client.post(
            self.base_url,
            data={"GroupID": "", "SectionID": sect_code, "strOPDTIMEFLAG": session_code},
            headers={
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": self.base_url,
            },
        )
        resp.raise_for_status()
        return self._parse_html(resp.text, sect_name, session_code, now)

    def _parse_html(self, html, dept_name, session_code, now):
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = SESSION_MAP.get(session_code, "未知")
        results = []

        if "查無資料" in soup.get_text():
            return []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                texts = [c.get_text(strip=True) for c in cells]

                doctor = ""
                clinic_room = ""
                current_number = 0

                for text in texts:
                    if not text:
                        continue
                    if re.match(r"^\d+$", text) and current_number == 0:
                        current_number = int(text)
                    elif re.match(r"^\d+診?$", text) and not clinic_room:
                        clinic_room = text
                    elif len(text) >= 2 and len(text) <= 10 and not doctor:
                        doctor = text

                if current_number > 0:
                    results.append(ClinicProgressData(
                        hospital_code=self.hospital_code,
                        hospital_name=self.hospital_name,
                        date=date_str,
                        session=session,
                        department=dept_name,
                        doctor_name=doctor,
                        clinic_room=clinic_room or dept_name,
                        current_number=current_number,
                        next_number=current_number + 1,
                        is_current_skipped=False,
                        is_next_skipped=False,
                        fetched_at=now,
                    ))

        return results

    async def get_departments(self) -> list[str]:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
            await client.get(self.base_url, headers=headers)
            sections = await self._fetch_sections(client, headers)
            return [name for _, name in sections]
