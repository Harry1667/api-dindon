"""三軍總醫院看診進度 Adapter

資料來源：https://www2.ndmctsgh.edu.tw/PatientNum/
技術：SPA 頁面，透過 AJAX 呼叫 /api/tsghapi2023/{1|2} 取得 HTML fragment
     1=上午診, 2=下午診
需要先訪問主頁面取得 session cookie
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

MAIN_URL = "https://www2.ndmctsgh.edu.tw/PatientNum/"
API_URL = "https://www2.ndmctsgh.edu.tw/api/tsghapi2023/{time_code}"

TIME_NAMES = {"1": "上午診", "2": "下午診"}


class TsghAdapter(BaseHospitalAdapter):
    """三軍總醫院 Adapter"""

    hospital_code = "tsgh"
    hospital_name = "三軍總醫院"
    base_url = MAIN_URL

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        now = datetime.now(TW_TZ)
        hour = now.hour
        if hour < 12:
            active_times = ["1"]
        elif hour < 17:
            active_times = ["1", "2"]
        else:
            active_times = ["2"]

        all_results = []

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                # 先訪問主頁面取得 session cookie
                await client.get(
                    MAIN_URL,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )

                for time_code in active_times:
                    try:
                        resp = await client.get(
                            API_URL.format(time_code=time_code),
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                "X-Requested-With": "XMLHttpRequest",
                                "Referer": MAIN_URL,
                            },
                        )
                        resp.raise_for_status()

                        # 如果回傳完整 HTML 頁面（非 fragment），代表 API 需要不同的請求方式
                        if "<!DOCTYPE html>" in resp.text[:100]:
                            logger.warning(f"[{self.hospital_code}] API 回傳完整頁面而非 fragment")
                            # 嘗試從完整頁面中找到看診資料
                            results = self._parse_full_page(resp.text, time_code, now)
                        else:
                            results = self._parse_fragment(resp.text, time_code, now)

                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(f"[{self.hospital_code}] time={time_code} 失敗: {e}")

        except Exception as e:
            logger.error(f"[{self.hospital_code}] 抓取失敗: {e}")

        logger.info(f"[{self.hospital_code}] 取得 {len(all_results)} 個診間")
        return all_results

    def _parse_fragment(
        self, html: str, time_code: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析 AJAX 回傳的 HTML fragment"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_NAMES.get(time_code, "未知")
        results = []

        # 找 table rows
        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            texts = [c.get_text(strip=True) for c in cells]

            # 跳過 header
            if any(kw in " ".join(texts) for kw in ["科別", "醫師", "診室", "燈號"]):
                continue

            department = ""
            doctor = ""
            clinic_room = ""
            current_number = 0

            for text in texts:
                if not text:
                    continue
                nums = re.findall(r"^\d+$", text)
                if nums and current_number == 0:
                    current_number = int(nums[0])
                elif re.match(r"^\d+診$", text) or re.match(r"^第?\d+診$", text):
                    clinic_room = text
                elif "科" in text or "部" in text or "中心" in text:
                    department = text
                elif len(text) >= 2 and len(text) <= 10 and not doctor:
                    doctor = text

            if current_number == 0:
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

    def _parse_full_page(
        self, html: str, time_code: str, now: datetime
    ) -> list[ClinicProgressData]:
        """從完整頁面中嘗試提取看診資料（fallback）"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_NAMES.get(time_code, "未知")
        results = []

        # 找 id=text01 或 id=text02 的 div（AJAX 載入目標）
        for div_id in ["text01", "text02"]:
            div = soup.find(id=div_id)
            if div:
                rows = div.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue
                    texts = [c.get_text(strip=True) for c in cells]

                    department = ""
                    doctor = ""
                    clinic_room = ""
                    current_number = 0

                    for text in texts:
                        if not text:
                            continue
                        nums = re.findall(r"^\d+$", text)
                        if nums and current_number == 0:
                            current_number = int(nums[0])
                        elif "科" in text or "部" in text:
                            department = text
                        elif len(text) >= 2 and len(text) <= 10 and not doctor:
                            doctor = text

                    if current_number > 0:
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
