"""台大醫院看診進度 Adapter

資料來源：https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo
技術：POST AJAX 到 /WebReg/WebReg/DeptLightTable
院區代碼：T0=總院, CH=兒童醫院, C0=癌醫中心, T2=北護分院
科別代碼：MED=內科部, SURG=外科部, ORTH=骨科部, OBGY=婦產部, OPH=眼科部, etc.
時段：1=上午, 2=下午, 3=夜間
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

NTUH_DEPTS = [
    "MED", "GERO", "FM", "NEUR", "GENE", "PMR", "ONC", "PSYC", "EOM",
    "SURG", "ORTH", "OBGY", "OPH", "ENT", "DENT", "DERM", "URO",
]

# 台大癌醫科別代碼
NTUCC_DEPTS = [
    "ME03", "ME04", "ME12", "ME10", "ME07", "ME02", "ME08", "ME06",
    "ME09", "ME05", "ME11", "ME15",  # 內科系
    "ONCR", "HEMA", "RT",  # 腫瘤/血液/放射
    "SR03", "SR02", "SR07", "SR04", "SR05", "SR08", "SR06",  # 外科系
    "SU04", "SU06", "SU07", "SU02", "SU08", "SU01", "SU05", "SU09",  # 外科
    "KBRC",  # 乳房醫學中心
]
TIME_CODES = ["1", "2", "3"]
TIME_NAMES = {"1": "上午診", "2": "下午診", "3": "夜診"}


class NtuhAdapter(BaseHospitalAdapter):
    """台大醫院 Adapter"""

    def __init__(self, hospital_code: str, hospital_name: str, hosp_code: str, depts: list[str] | None = None):
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.hosp_code = hosp_code
        self.depts = depts or NTUH_DEPTS
        self.base_url = "https://reg.ntuh.gov.tw/WebReg/WebReg/DeptLightTable"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """遍歷科別+時段取得看診進度"""
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
            # 先訪問主頁面取得 session cookie
            try:
                await client.get(
                    f"https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo?vHospCode={self.hosp_code}",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )
            except Exception:
                pass

            for time_code in active_times:
                for dept in self.depts:
                    try:
                        results = await self._fetch_dept(
                            client, dept, time_code, now
                        )
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(
                            f"[{self.hospital_code}] dept={dept} "
                            f"time={time_code} 失敗: {e}"
                        )

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_dept(
        self,
        client: httpx.AsyncClient,
        dept: str,
        time_code: str,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一科別+時段（先訪問主頁取得 session）"""
        resp = await client.post(
            self.base_url,
            data={
                "vHospCode": self.hosp_code,
                "DropDownDept": dept,
                "DropDownAMPM": time_code,
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo?vHospCode={self.hosp_code}",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        # 500 = 非看診時間或該科別無資料，不視為錯誤
        if resp.status_code == 500:
            return []
        resp.raise_for_status()
        return self._parse_html(resp.text, time_code, now)

    def _parse_html(
        self, html: str, time_code: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析回傳的 HTML（可能是 table 或 div 列表）"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_NAMES.get(time_code, "未知")
        results = []

        # 嘗試 table 格式
        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            texts = [c.get_text(strip=True) for c in cells]
            # 常見欄位：科別/診間, 醫師, 燈號(目前看診號), 下一號
            # 具體格式需上班時間驗證
            dept = texts[0] if texts[0] else ""
            doctor = texts[1] if len(texts) > 1 else ""
            current_text = texts[2] if len(texts) > 2 else ""
            next_text = texts[3] if len(texts) > 3 else ""

            if not dept or not current_text:
                continue

            current_number = 0
            next_number = 0
            is_current_skipped = False
            is_next_skipped = False

            cur_nums = re.findall(r"\d+", current_text)
            if cur_nums:
                current_number = int(cur_nums[0])
            nxt_nums = re.findall(r"\d+", next_text)
            if nxt_nums:
                next_number = int(nxt_nums[0])

            if "過號" in current_text:
                is_current_skipped = True
            if "過號" in next_text:
                is_next_skipped = True

            if current_number == 0 and next_number == 0:
                continue

            results.append(ClinicProgressData(
                hospital_code=self.hospital_code,
                hospital_name=self.hospital_name,
                date=date_str,
                session=session,
                department=dept,
                doctor_name=doctor,
                clinic_room=dept,  # 台大用科別作為診間標示
                current_number=current_number,
                next_number=next_number,
                is_current_skipped=is_current_skipped,
                is_next_skipped=is_next_skipped,
                fetched_at=now,
            ))

        # 如果 table 沒資料，嘗試其他格式（div/span）
        if not results:
            # 找所有包含數字的燈號元素
            light_elements = soup.find_all(class_=re.compile(r"light|num|clinic", re.I))
            for el in light_elements:
                text = el.get_text(strip=True)
                nums = re.findall(r"\d+", text)
                if nums:
                    logger.debug(f"[{self.hospital_code}] 燈號元素: {text}")

        return results

    async def get_departments(self) -> list[str]:
        return [d for d in self.depts]


# === 預建院區 ===
ntuh_main = NtuhAdapter("ntuh", "台大醫院", "T0")
ntuh_children = NtuhAdapter("ntuh-children", "台大兒童醫院", "CH")
ntuh_cancer = NtuhAdapter("ntuh-cancer", "台大癌醫", "C0", depts=NTUCC_DEPTS)
