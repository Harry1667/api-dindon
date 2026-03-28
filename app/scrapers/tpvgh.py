"""台北榮總看診進度 Adapter

資料來源：https://www6.vghtpe.gov.tw/reg/realTime.do
技術：GET 帶參數 → HTML table
科別頁面：type=realtime（顯示所有科別連結）
科別進度：type=dept&deptCode={code}&ampm={1|2|3}
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

BASE_URL = "https://www6.vghtpe.gov.tw/reg/realTime.do"

TIME_NAMES = {"1": "上午診", "2": "下午診", "3": "夜診"}


class TpvghAdapter(BaseHospitalAdapter):
    """台北榮總 Adapter"""

    hospital_code = "tpvgh"
    hospital_name = "台北榮總"
    base_url = BASE_URL

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """先取科別列表，再逐一查進度"""
        now = datetime.now(TW_TZ)
        hour = now.hour
        if hour < 12:
            active_times = ["1"]
        elif hour < 17:
            active_times = ["1", "2"]
        else:
            active_times = ["2", "3"]

        # Step 1: 取得所有科別代碼
        dept_codes = await self._fetch_departments()
        if not dept_codes:
            logger.warning(f"[{self.hospital_code}] 無法取得科別列表")
            return []

        # Step 2: 遍歷有效時段+科別
        all_results = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for ampm in active_times:
                for dept_code, dept_name in dept_codes:
                    try:
                        results = await self._fetch_dept(
                            client, dept_code, dept_name, ampm, now
                        )
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(
                            f"[{self.hospital_code}] {dept_name} 失敗: {e}"
                        )

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_departments(self) -> list[tuple[str, str]]:
        """從科別總覽頁面解析所有科別連結"""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.base_url,
                    params={"type": "realtime"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"[{self.hospital_code}] 取科別列表失敗: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        dept_codes = []

        # 找所有科別連結：通常是 <a> 標籤帶 href 包含 deptCode
        links = soup.find_all("a", href=True)
        for link in links:
            href = link.get("href", "")
            name = link.get_text(strip=True)
            # 找包含 deptCode 的連結
            match = re.search(r"deptCode=([^&]+)", href)
            if match and name:
                code = match.group(1)
                dept_codes.append((code, name))

            # 也找 JavaScript onclick 中的科別代碼
            onclick = link.get("onclick", "")
            match2 = re.search(r"deptCode['\"]?\s*[:=]\s*['\"]([^'\"]+)", onclick)
            if match2 and name:
                dept_codes.append((match2.group(1), name))

        # 去重
        seen = set()
        unique = []
        for code, name in dept_codes:
            if code not in seen:
                seen.add(code)
                unique.append((code, name))

        logger.info(f"[{self.hospital_code}] 找到 {len(unique)} 個科別")
        return unique

    async def _fetch_dept(
        self,
        client: httpx.AsyncClient,
        dept_code: str,
        dept_name: str,
        ampm: str,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一科別進度"""
        resp = await client.get(
            self.base_url,
            params={"type": "dept", "deptCode": dept_code, "ampm": ampm},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        return self._parse_dept_html(resp.text, dept_name, ampm, now)

    def _parse_dept_html(
        self, html: str, dept_name: str, ampm: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析科別進度頁面"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_NAMES.get(ampm, "未知")
        results = []

        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                # 跳過 header
                if any(kw in " ".join(texts) for kw in ["診別", "燈號", "醫師姓名"]):
                    continue

                # 提取號碼
                doctor = ""
                clinic_room = ""
                current_number = 0

                for i, text in enumerate(texts):
                    nums = re.findall(r"\d+", text)
                    if nums and len(text) < 8 and not doctor:
                        current_number = int(nums[0])
                    elif len(text) > 1 and len(text) < 20:
                        if not doctor:
                            doctor = text
                        elif not clinic_room:
                            clinic_room = text

                if current_number == 0:
                    continue

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
        dept_codes = await self._fetch_departments()
        return [name for _, name in dept_codes]
