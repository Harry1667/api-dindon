"""國泰醫院看診進度 Adapter

資料來源：https://reg.cgh.org.tw/tw/reg/RealTimeTable.jsp
技術：POST form → HTML table
參數：hosarea=1(總院)/3(新竹)/4(汐止)/5(內湖), sec=1(上午)/2(下午)/3(夜間), room=診室代號(可選)
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

CATHAY_URL = "https://reg.cgh.org.tw/tw/reg/RealTimeTable.jsp"

TIME_NAMES = {"1": "上午診", "2": "下午診", "3": "夜診"}


class CathayAdapter(BaseHospitalAdapter):
    """國泰醫院 Adapter — 總院"""

    hospital_code = "cathay"
    hospital_name = "國泰醫院"
    base_url = CATHAY_URL

    def __init__(self, hospital_code: str = "cathay", hospital_name: str = "國泰醫院", hosarea: str = "1"):
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.hosarea = hosarea
        self.base_url = CATHAY_URL

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """遍歷所有時段查詢看診進度"""
        now = datetime.now(TW_TZ)
        hour = now.hour
        if hour < 12:
            active_times = ["1"]
        elif hour < 17:
            active_times = ["1", "2"]
        else:
            active_times = ["2", "3"]

        all_results = []
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for sec in active_times:
                try:
                    results = await self._fetch_session(client, sec, now)
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"[{self.hospital_code}] sec={sec} 失敗: {e}")

        logger.info(f"[{self.hospital_code}] 取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_session(
        self,
        client: httpx.AsyncClient,
        sec: str,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一時段"""
        resp = await client.post(
            self.base_url,
            data={"hosarea": self.hosarea, "sec": sec, "room": ""},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": self.base_url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        return self._parse_html(resp.text, sec, now)

    def _parse_html(
        self, html: str, sec: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析看診進度 HTML"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_NAMES.get(sec, "未知")
        results = []

        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            # 檢查是否為看診資料 table（header 含「診室」「醫師」等）
            header = rows[0]
            header_text = header.get_text()
            if "診室" not in header_text and "醫師" not in header_text and "燈號" not in header_text:
                continue

            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                # 解析各欄位
                clinic_room = ""
                department = ""
                doctor = ""
                current_number = 0
                is_stopped = False

                for text in texts:
                    if "停診" in text:
                        is_stopped = True
                    elif not text:
                        continue
                    elif re.match(r"^\d+$", text):
                        if not current_number:
                            current_number = int(text)
                    elif re.match(r"^\d+診$", text) or re.match(r"^[A-Z]?\d+$", text):
                        clinic_room = text
                    elif "科" in text or "部" in text or "中心" in text:
                        department = text
                    elif len(text) >= 2 and len(text) <= 10 and not doctor:
                        doctor = text

                if is_stopped or current_number == 0:
                    continue

                results.append(ClinicProgressData(
                    hospital_code=self.hospital_code,
                    hospital_name=self.hospital_name,
                    date=date_str,
                    session=session,
                    department=department or "未知",
                    doctor_name=doctor,
                    clinic_room=clinic_room or department or "未知",
                    current_number=current_number,
                    next_number=current_number + 1,
                    is_current_skipped=False,
                    is_next_skipped=False,
                    fetched_at=now,
                ))

        return results

    async def get_departments(self) -> list[str]:
        all_progress = await self.fetch_all_progress()
        return sorted(set(p.department for p in all_progress))
