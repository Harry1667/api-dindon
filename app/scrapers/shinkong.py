"""新光醫院看診進度 Adapter

資料來源：https://www.skh.org.tw/skh_regis/
技術：待上班時間驗證 HTML 結構
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

# 新光掛號系統看診進度頁面
SHINKONG_URL = "https://www.skh.org.tw/skh_regis/"


class ShinkongAdapter(BaseHospitalAdapter):
    """新光醫院 Adapter"""

    hospital_code = "shinkong"
    hospital_name = "新光醫院"
    base_url = SHINKONG_URL

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        now = datetime.now(TW_TZ)
        all_results = []

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    self.base_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )
                resp.raise_for_status()
                all_results = self._parse_html(resp.text, now)
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 抓取失敗: {e}")

        logger.info(f"[{self.hospital_code}] 取得 {len(all_results)} 個診間")
        return all_results

    def _parse_html(self, html: str, now: datetime) -> list[ClinicProgressData]:
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        results = []

        # 通用 table 解析
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                texts = [c.get_text(strip=True) for c in cells]

                doctor = ""
                dept = ""
                current_number = 0

                for text in texts:
                    nums = re.findall(r"\d+", text)
                    if nums and len(text) < 8:
                        current_number = int(nums[0])
                    elif len(text) >= 2 and not dept:
                        dept = text
                    elif len(text) >= 2 and not doctor:
                        doctor = text

                if current_number == 0:
                    continue

                results.append(ClinicProgressData(
                    hospital_code=self.hospital_code,
                    hospital_name=self.hospital_name,
                    date=date_str,
                    session="未知",
                    department=dept,
                    doctor_name=doctor,
                    clinic_room=dept,
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
