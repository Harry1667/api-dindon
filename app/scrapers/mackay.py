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
        """解析看診進度頁面"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_CODES.get(ap, "未知")
        dept_name = MACKAY_DEPTS.get(dept_code, dept_code)
        results = []

        # 找所有 table rows（看診資料通常在 table 中）
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                # 過濾 header 行
                if any(kw in texts[0] for kw in ["診間", "醫師", "科別"]):
                    continue

                # 嘗試解析：常見格式是 診間/醫師/目前號碼 或 醫師/診間/號碼
                doctor = ""
                clinic_room = ""
                current_number = 0
                is_stopped = False

                for text in texts:
                    if "已停診" in text or "[已停診]" in text:
                        is_stopped = True
                    nums = re.findall(r"\d+", text)
                    if nums and not doctor:
                        # 可能是號碼
                        pass

                # 更通用的解析：找含數字的 cell 作為號碼
                num_cells = []
                text_cells = []
                for text in texts:
                    nums = re.findall(r"\d+", text)
                    if nums and len(text) < 10:
                        num_cells.append((int(nums[0]), "過號" in text))
                    else:
                        text_cells.append(text)

                if not num_cells or is_stopped:
                    continue

                # 文字欄位：第一個像醫師名，第二個像診間
                if len(text_cells) >= 2:
                    doctor = text_cells[0]
                    clinic_room = text_cells[1]
                elif text_cells:
                    doctor = text_cells[0]
                    clinic_room = dept_name

                current_number = num_cells[0][0]
                is_current_skipped = num_cells[0][1]
                next_number = num_cells[1][0] if len(num_cells) > 1 else current_number + 1
                is_next_skipped = num_cells[1][1] if len(num_cells) > 1 else False

                if current_number == 0:
                    continue

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
                    is_next_skipped=is_next_skipped,
                    fetched_at=now,
                ))

        return results

    async def get_departments(self) -> list[str]:
        return sorted(MACKAY_DEPTS.values())


# === 預建院區 ===
mackay_taipei = MackayAdapter("mackay-taipei", "馬偕醫院(台北)", "tp")
mackay_tamsui = MackayAdapter("mackay-tamsui", "馬偕醫院(淡水)", "ts")
