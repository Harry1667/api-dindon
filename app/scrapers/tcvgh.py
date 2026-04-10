"""台中榮總看診進度 Adapter

資料來源：https://www.vghtc.gov.tw/APIPage/OutpatientProcess2
流程：
  1. GET OutpatientProcess 首頁 → 取得所有科別 SECTION_ID / SECTION_NAME
  2. GET OutpatientProcess2?SECTION_ID=XX&SECTION_NAME=YY → 取得該科 HTML table

HTML table 欄位：
  午別 | 診間 | 醫師 | 最末號 | 目前看診號次 | 過號看診號 | 已報到待看診人次 | 備註 | 地點
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

BASE_URL = "https://www.vghtc.gov.tw/APIPage"
WEB_MENU_ID = "7ee59e49-b2b8-4e1a-a3cb-45360caab01c"

# 常用科別（優先抓取，減少請求數）
MAIN_SECTIONS = [
    ("GM", "一般內科"), ("CV", "心臟內科"), ("GI", "胃腸肝膽"),
    ("CM", "胸腔內科"), ("NEUR", "神經內科"), ("NEPH", "腎臟科"),
    ("META", "新陳代謝"), ("IMRH", "免疫風濕"), ("INF", "感染科"),
    ("MO", "腫瘤內科"), ("HEMA", "血液腫瘤"),
    ("GS", "一般外科"), ("BS", "乳房腫瘤外科"), ("CRS", "大腸直腸"),
    ("CVS", "心臟外科"), ("PS", "整形外科"), ("GU", "泌尿醫學部"),
    ("NS", "神經外科"), ("CS", "胸腔外科"), ("ORTH", "骨科部"),
    ("PGEN", "一般兒科"), ("OBGY", "婦女醫學部"),
    ("FM", "家庭醫學"), ("PSY", "精神部"), ("DERM", "皮膚科"),
    ("OPH", "眼科部"), ("ENT", "耳鼻喉頭頸部"), ("REHA", "復健醫學部"),
    ("DENT", "一般牙科"), ("TCM", "傳統醫學部"), ("CGA", "高齡醫學"),
]


class TcvghAdapter(BaseHospitalAdapter):
    """台中榮總 Adapter"""

    hospital_code = "tcvgh"
    hospital_name = "台中榮總"
    base_url = f"{BASE_URL}/OutpatientProcess"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """抓取所有科別看診進度"""
        now = datetime.now(TW_TZ)
        all_results = []

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for sect_id, sect_name in MAIN_SECTIONS:
                try:
                    results = await self._fetch_section(client, sect_id, sect_name, now)
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"[{self.hospital_code}] {sect_name}({sect_id}) 失敗: {e}")

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_section(
        self, client: httpx.AsyncClient, sect_id: str, sect_name: str, now: datetime
    ) -> list[ClinicProgressData]:
        """查詢單一科別"""
        resp = await client.get(
            f"{BASE_URL}/OutpatientProcess2",
            params={
                "SECTION_ID": sect_id,
                "SECTION_NAME": sect_name,
                "WebMenuID": WEB_MENU_ID,
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            },
        )
        resp.raise_for_status()
        return self._parse_html(resp.text, sect_name, now)

    def _parse_html(self, html: str, dept_name: str, now: datetime) -> list[ClinicProgressData]:
        """解析科別看診進度 HTML table

        欄位順序：午別 | 診間 | 醫師 | 最末號 | 目前看診號次 | 過號看診號 | 已報到待看診人次 | 備註 | 地點
        """
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        results = []

        # 找所有 table，跳過 header
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 7:
                    continue

                try:
                    texts = [c.get_text(strip=True) for c in cells]

                    session_text = texts[0]  # 午別：上午/下午/夜間
                    clinic_room = texts[1]   # 診間：2213
                    doctor = texts[2]        # 醫師
                    # texts[3] = 最末號
                    current_str = texts[4]   # 目前看診號次
                    skipped_str = texts[5]   # 過號看診號
                    # texts[6] = 已報到待看診人次

                    # 跳過標題列
                    if '午別' in session_text or '醫師' in doctor:
                        continue

                    # 解析號碼
                    current_number = self._parse_number(current_str)
                    if current_number == 0:
                        continue

                    # 過號數
                    skipped_count = self._parse_number(skipped_str)

                    # 午別轉換
                    session = self._map_session(session_text)

                    results.append(ClinicProgressData(
                        hospital_code=self.hospital_code,
                        hospital_name=self.hospital_name,
                        date=date_str,
                        session=session,
                        department=dept_name,
                        doctor_name=doctor,
                        clinic_room=f"{clinic_room}診",
                        current_number=current_number,
                        next_number=current_number + 1,
                        is_current_skipped=skipped_count > 0,
                        is_next_skipped=False,
                        fetched_at=now,
                    ))
                except Exception as e:
                    logger.warning(f"[{self.hospital_code}] 解析 row 失敗: {e}")

        return results

    @staticmethod
    def _parse_number(text: str) -> int:
        """解析數字，非數字回傳 0"""
        m = re.search(r"(\d+)", text)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _map_session(text: str) -> str:
        if "上" in text:
            return "上午診"
        elif "下" in text:
            return "下午診"
        elif "夜" in text or "晚" in text:
            return "夜診"
        return text

    async def get_departments(self) -> list[str]:
        """取得所有科別"""
        return [name for _, name in MAIN_SECTIONS]
