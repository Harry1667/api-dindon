"""振興醫院看診進度 Adapter

資料來源：https://reg.chgh.org.tw/allroom_cload.aspx (科別總覽)
         https://reg.chgh.org.tw/allroom_cload2.aspx?pidm={code} (各科進度)
技術：ASP.NET Server-Side Rendered HTML
     每個科別有一個 pidm 代碼，查詢該科所有診間看診進度
     頁面內容在 server side 產生，直接解析 HTML 即可

結構：
  allroom_cload.aspx → 列出所有科別連結，含 pidm 代碼
  allroom_cload2.aspx?pidm=XXX → 該科所有診間的看診進度
    - 「目前無開診的診間」= 該科無看診
    - 有看診時顯示：醫師、診間號、目前號碼 等
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

BASE_URL = "https://reg.chgh.org.tw"


class ChghAdapter(BaseHospitalAdapter):
    """振興醫院 Adapter"""

    hospital_code = "chgh"
    hospital_name = "振興醫院"
    base_url = f"{BASE_URL}/allroom_cload.aspx"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """先取科別列表，再逐科查看診進度"""
        now = datetime.now(TW_TZ)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        # Step 1: 取得科別 pidm 列表
        dept_list = await self._fetch_departments_with_pidm(headers)
        if not dept_list:
            logger.warning(f"[{self.hospital_code}] 無法取得科別列表")
            return []

        # Step 2: 逐科查詢
        all_results = []
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for dept_name, pidm in dept_list:
                try:
                    results = await self._fetch_dept_progress(
                        client, dept_name, pidm, headers, now
                    )
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"[{self.hospital_code}] {dept_name} 失敗: {e}")

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_departments_with_pidm(
        self, headers: dict
    ) -> list[tuple[str, str]]:
        """從科別總覽頁取得所有科別 pidm"""
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.base_url, headers=headers)
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 取科別列表失敗: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        depts = []

        for a in soup.find_all("a", onclick=True):
            match = re.search(
                r"allroom_cload2\.aspx\?pidm=([A-F0-9]+)", a.get("onclick", "")
            )
            if match:
                name = a.get_text(strip=True)
                if name:
                    depts.append((name, match.group(1)))

        logger.info(f"[{self.hospital_code}] 找到 {len(depts)} 個科別")
        return depts

    async def _fetch_dept_progress(
        self,
        client: httpx.AsyncClient,
        dept_name: str,
        pidm: str,
        headers: dict,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一科別的看診進度"""
        resp = await client.get(
            f"{BASE_URL}/allroom_cload2.aspx",
            params={"pidm": pidm},
            headers=headers,
        )
        resp.raise_for_status()
        return self._parse_dept_html(resp.text, dept_name, now)

    def _parse_dept_html(
        self, html: str, dept_name: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析科別看診進度頁面"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        results = []

        # 檢查「目前無開診」
        text = soup.get_text()
        if "目前無開診" in text:
            return []

        # 判斷診別（從頁面顏色提示: 藍=上午, 綠=下午, 紅=夜）
        hour = now.hour
        if hour < 12:
            session = "上午診"
        elif hour < 17:
            session = "下午診"
        else:
            session = "夜診"

        # 振興的 card-panel 內有 table，固定 5 欄:
        #   [0] 午別 (上午診/下午診/夜診)
        #   [1] 科別名稱 (含診間號如 "胃腸肝膽科002診")
        #   [2] 診間號 (如 "002")
        #   [3] 醫生姓名
        #   [4] 現在序號
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                # 跳過 header
                if "午別" in texts[0] or "醫生" in texts[3]:
                    continue

                # 從午別欄位取得更精確的 session
                session_text = texts[0]
                if "上午" in session_text:
                    row_session = "上午診"
                elif "下午" in session_text:
                    row_session = "下午診"
                elif "夜" in session_text:
                    row_session = "夜診"
                else:
                    row_session = session

                clinic_room = texts[2].strip()  # 診間號
                doctor = texts[3].strip()       # 醫生姓名

                # 現在序號（可能在 span 裡）
                num_match = re.search(r"(\d+)", texts[4])
                current_number = int(num_match.group(1)) if num_match else 0

                if current_number == 0 or not doctor:
                    continue

                results.append(
                    ClinicProgressData(
                        hospital_code=self.hospital_code,
                        hospital_name=self.hospital_name,
                        date=date_str,
                        session=row_session,
                        department=dept_name,
                        doctor_name=doctor,
                        clinic_room=f"{clinic_room}診" if clinic_room.isdigit() else clinic_room,
                        current_number=current_number,
                        next_number=current_number + 1,
                        is_current_skipped=False,
                        is_next_skipped=False,
                        fetched_at=now,
                    )
                )

        return results

    async def get_departments(self) -> list[str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        depts = await self._fetch_departments_with_pidm(headers)
        return [name for name, _ in depts]
