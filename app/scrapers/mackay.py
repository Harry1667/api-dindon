"""馬偕醫院看診進度 Adapter

資料來源：https://www.mmh.org.tw/progressstatus.php
技術：GET 帶參數 → HTML（每 30 秒自動更新）
參數：area=tp|ts (台北/淡水), dept=科別代碼, ap=1|2|3 (上午/下午/夜間)
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

BASE_URL = "https://www.mmh.org.tw/progressstatus.php"

# 主要科別代碼
MACKAY_DEPTS = {
    "12": "內分泌暨新陳代謝科", "13": "消化科系", "14": "心臟血管內科系",
    "15": "胸腔內科", "16": "腎臟內科", "18": "血液暨腫瘤科",
    "19": "過敏免疫風濕科", "26": "一般內科及感染科",
    "50": "一般外科", "53": "神經外科", "55": "整形外科",
    "56": "大腸直腸外科", "57": "乳房外科",
    "30": "小兒科", "40": "婦科", "41": "產科",
    "20": "神經科", "21": "精神科", "22": "皮膚科",
    "23": "復健科", "24": "家庭醫學科",
    "60": "骨科", "70": "泌尿科",
    "80": "耳鼻喉科", "90": "眼科",
    "C7": "中醫內兒科", "C6": "中醫婦科", "C2": "中醫針灸科",
    "B0": "牙科",
}

TIME_CODES = {"1": "上午診", "2": "下午診", "3": "夜診"}


class MackayAdapter(BaseHospitalAdapter):
    """馬偕醫院 Adapter"""

    def __init__(self, hospital_code: str, hospital_name: str, area: str):
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.area = area  # tp=台北, ts=淡水
        self.base_url = BASE_URL

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """遍歷所有科別+時段"""
        now = datetime.now(TW_TZ)
        hour = now.hour
        if hour < 12:
            active_times = ["1"]
        elif hour < 17:
            active_times = ["1", "2"]
        else:
            active_times = ["2", "3"]

        all_results = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for ap in active_times:
                for dept_code in MACKAY_DEPTS:
                    try:
                        results = await self._fetch_dept(
                            client, dept_code, ap, now
                        )
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(
                            f"[{self.hospital_code}] dept={dept_code} "
                            f"ap={ap} 失敗: {e}"
                        )

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_dept(
        self,
        client: httpx.AsyncClient,
        dept_code: str,
        ap: str,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一科別+時段"""
        resp = await client.get(
            self.base_url,
            params={"area": self.area, "dept": dept_code, "ap": ap},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )
        resp.raise_for_status()
        return self._parse_html(resp.text, dept_code, ap, now)

    def _parse_html(
        self, html: str, dept_code: str, ap: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析看診進度頁面

        馬偕 HTML table 固定 5 欄:
          [0] 位置      (如 "馬偕樓 02樓 213室")
          [1] 診別      (如 "內分03診")
          [2] 醫師      (如 "簡銘男")
          [3] 目前看診號 (如 "71號" 或 "過號71號")
          [4] 未看診人數 (如 "37人")
        """
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_CODES.get(ap, "未知")
        dept_name = MACKAY_DEPTS.get(dept_code, dept_code)
        results = []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                # 跳過 header 行
                if any(kw in texts[0] for kw in ["位置", "診間", "醫師", "科別"]):
                    continue

                # 跳過已停診
                if any("已停診" in t for t in texts):
                    continue

                clinic_room = texts[1]   # 診別 (如 "內分03診")
                doctor = texts[2]        # 醫師
                current_text = texts[3]  # "71號" 或 "過號71號"
                waiting_text = texts[4]  # "37人"

                # 解析目前看診號
                is_current_skipped = "過號" in current_text
                num_match = re.search(r"(\d+)", current_text)
                current_number = int(num_match.group(1)) if num_match else 0

                if current_number == 0:
                    continue

                # 解析未看診人數 → 推算 next_number
                wait_match = re.search(r"(\d+)", waiting_text)
                waiting = int(wait_match.group(1)) if wait_match else 0
                next_number = current_number + waiting

                results.append(ClinicProgressData(
                    hospital_code=self.hospital_code,
                    hospital_name=self.hospital_name,
                    date=date_str,
                    session=session,
                    department=dept_name,
                    doctor_name=doctor,
                    clinic_room=clinic_room,
                    current_number=current_number,
                    next_number=next_number,
                    is_current_skipped=is_current_skipped,
                    is_next_skipped=False,
                    fetched_at=now,
                ))

        return results

    async def get_departments(self) -> list[str]:
        return sorted(MACKAY_DEPTS.values())


# === 預建院區 ===
mackay_taipei = MackayAdapter("mackay-taipei", "馬偕醫院(台北)", "tp")
mackay_tamsui = MackayAdapter("mackay-tamsui", "馬偕醫院(淡水)", "ts")
