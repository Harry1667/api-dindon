"""長庚醫院看診進度 Adapter

資料來源：https://register.cgmh.org.tw/Progress/{院區代碼}
技術：POST form → HTML table
院區代碼：1=台北長庚, 3=林口長庚, 5=桃園長庚, 6=基隆長庚, 8=高雄長庚, 9=嘉義長庚, A=鳳山長庚, C=雲林長庚, D=土城長庚
科別代碼：00=COVID, 02=內科, 03=外科, 04=牙科, 05=婦產科, 06=兒童, 07=其他, 08=中醫, 09=聯合, 13=自費
時段：1=上午, 2=下午, 3=晚間
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

# 要查詢的主要科別
DEPT_CODES = ["02", "03", "04", "05", "06", "07", "08", "09", "13"]
TIME_CODES = ["1", "2", "3"]
TIME_NAMES = {"1": "上午診", "2": "下午診", "3": "夜診"}


class ChangGungAdapter(BaseHospitalAdapter):
    """長庚醫院 Adapter — 支援多院區"""

    def __init__(self, hospital_code: str, hospital_name: str, branch_id: str):
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.branch_id = branch_id
        self.base_url = f"https://register.cgmh.org.tw/Progress/{branch_id}"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """遍歷所有科別+時段，取得看診進度"""
        now = datetime.now(TW_TZ)
        # 根據當前時間只查詢相關時段
        hour = now.hour
        if hour < 12:
            active_times = ["1"]
        elif hour < 17:
            active_times = ["1", "2"]
        else:
            active_times = ["2", "3"]

        all_results = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for time_code in active_times:
                for dept_code in DEPT_CODES:
                    try:
                        results = await self._fetch_dept(
                            client, dept_code, time_code, now
                        )
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(
                            f"[{self.hospital_code}] dept={dept_code} "
                            f"time={time_code} 失敗: {e}"
                        )

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_dept(
        self,
        client: httpx.AsyncClient,
        dept_code: str,
        time_code: str,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一科別+時段"""
        resp = await client.post(
            self.base_url,
            data={"dept": dept_code, "time": time_code},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": self.base_url,
            },
        )
        resp.raise_for_status()
        return self._parse_html(resp.text, time_code, now)

    def _parse_html(
        self, html: str, time_code: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析 HTML table"""
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            return []

        rows = table.find_all("tr")
        if len(rows) < 2:
            return []

        date_str = now.strftime("%Y/%m/%d")
        session = TIME_NAMES.get(time_code, "未知")
        results = []

        for row in rows[1:]:  # 跳過 header
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            dept = cells[0].get_text(strip=True)
            location = cells[1].get_text(strip=True)
            doctor = cells[2].get_text(strip=True)
            current_text = cells[3].get_text(strip=True)
            next_text = cells[4].get_text(strip=True)

            if not dept or not doctor:
                continue

            # 解析號碼（可能包含「過號」）
            current_number = 0
            is_current_skipped = False
            next_number = 0
            is_next_skipped = False

            cur_nums = re.findall(r"\d+", current_text)
            if cur_nums:
                current_number = int(cur_nums[0])
            if "過號" in current_text:
                is_current_skipped = True

            next_nums = re.findall(r"\d+", next_text)
            if next_nums:
                next_number = int(next_nums[0])
            if "過號" in next_text:
                is_next_skipped = True

            # 跳過沒有任何號碼的
            if current_number == 0 and next_number == 0:
                continue

            # 診間：從看診位置取「／」前的樓層資訊（去掉地址）
            if "／" in location:
                clinic_room = location.split("／")[0].strip()
            elif "/" in location:
                clinic_room = location.split("/")[0].strip()
            else:
                clinic_room = location

            results.append(ClinicProgressData(
                hospital_code=self.hospital_code,
                hospital_name=self.hospital_name,
                date=date_str,
                session=session,
                department=dept,
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
        all_progress = await self.fetch_all_progress()
        return sorted(set(p.department for p in all_progress))


# === 預建院區 Adapter ===
# 代碼對照：1=台北, 2=基隆, 3=林口, 5=桃園, 6=嘉義, 8=高雄,
#          B=長庚診所, E=情人湖(基隆), M=雲林, T=鳳山, V=土城
keelung_changgung = ChangGungAdapter("changgung-keelung", "基隆長庚", "2")
taipei_changgung = ChangGungAdapter("changgung-taipei", "台北長庚", "1")
linkou_changgung = ChangGungAdapter("changgung-linkou", "林口長庚", "3")
taoyuan_changgung = ChangGungAdapter("changgung-taoyuan", "桃園長庚", "5")
yunlin_changgung = ChangGungAdapter("changgung-yunlin", "雲林長庚", "M")
chiayi_changgung = ChangGungAdapter("changgung-chiayi", "嘉義長庚", "6")
kaohsiung_changgung = ChangGungAdapter("changgung-kaohsiung", "高雄長庚", "8")
fengshan_changgung = ChangGungAdapter("changgung-fengshan", "鳳山長庚", "T")
tucheng_changgung = ChangGungAdapter("changgung-tucheng", "土城長庚", "V")
