"""台大醫院看診進度 Adapter

資料來源：https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo
技術：POST AJAX 到 /WebReg/WebReg/DeptLightTable
      需帶 __RequestVerificationToken（從主頁 hidden input 取得）
參數：vHospitalCode, DeptCode, RegionCode, AmpmCode
院區代碼：T0=總院, CH=兒童醫院, C0=癌醫中心, T2=北護分院
時段：1=上午, 2=下午, 3=夜間

回傳 HTML 格式：div.clinic-room-number card layout
  - div.room-number = 診間（如「24 診」）
  - div.clinic-doc-name = 醫師姓名
  - div.clinic-type = 門診類型
  - div.number = 目前看診號碼
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

# 科別代碼 → 中文名稱（合併所有院區）
DEPT_NAMES = {
    # 台大本院 (T0)
    "MED": "內科部", "GERO": "老年醫學部", "FM": "家庭醫學部",
    "NEUR": "神經部", "GENE": "基因醫學部", "PMR": "復健部",
    "ONC": "腫瘤醫學部", "PSYC": "精神部", "EOM": "環境暨職業醫學部",
    "SURG": "外科部", "ORTH": "骨科部", "OBGY": "婦產部",
    "OPH": "眼科部", "ENT": "耳鼻喉部", "DENT": "口腔醫學部",
    "DERM": "皮膚部", "URO": "泌尿部", "PED": "小兒部",
    "PC": "麻醉部", "KBRC": "乳房醫學中心", "NUTR": "營養室",
    "RAD": "影像醫學部", "ACP": "預立醫療照護諮商",
    # 癌醫中心 (C0)
    "ME02": "心臟科", "ME03": "胸腔科", "ME04": "消化科",
    "ME05": "腎臟科", "ME06": "神經科", "ME07": "身心科",
    "ME08": "內分泌科", "ME09": "免疫科", "ME10": "感染科",
    "ME11": "復健科", "ME12": "家醫暨緩和醫療科", "ME15": "一般內科",
    "ONCR": "腫瘤內科部", "HEMA": "血液腫瘤部", "RT": "放射腫瘤部",
    "SR02": "眼科", "SR03": "牙科", "SR04": "整形外科",
    "SR05": "神經外科", "SR06": "婦科", "SR07": "皮膚科",
    "SR08": "心臟血管外科", "ANE": "麻醉部",
    "SU01": "一般外科", "SU02": "耳鼻喉科", "SU04": "胸腔外科",
    "SU05": "上消化道腫瘤外科", "SU06": "肝膽胰腫瘤外科",
    "SU07": "大腸直腸外科", "SU08": "泌尿科", "SU09": "骨科",
    # 兒童醫院 (CH)
    "02": "一般兒科", "10": "新生兒科", "18": "青少年醫學科",
    "20": "健兒門診", "24": "小兒外科", "36": "特殊需求者口腔醫學科",
    # 分院共用
    "CPC": "臨床心理中心", "CHA": "形體美容中心",
    # 新竹生醫 (T7) — 尾碼 V
    "MEDV": "內科部", "PEDV": "小兒部", "FMV": "家庭醫學部",
    "PMRV": "復健部", "PSYV": "精神部", "NEUV": "神經部",
    "ONCV": "腫瘤醫學部", "GERV": "老年醫學部",
    "SURV": "外科部", "ORTV": "骨科部", "OBGV": "婦產部",
    "ENTV": "耳鼻喉部", "UROV": "泌尿部", "OPHV": "眼科部",
    "DENV": "牙科部", "DERV": "皮膚部", "KBRV": "乳房醫學中心",
    # 雲林虎尾 (Y0) — 前綴 H
    "HMED": "內科部", "HSUR": "外科部", "HFM": "家庭醫學部",
    "HNEU": "神經部", "HORT": "骨科部", "HURO": "泌尿部",
    "HOBG": "婦產部", "HPED": "小兒部", "HOPH": "眼科部",
    "HENT": "耳鼻喉部", "HDER": "皮膚部", "HPMR": "復健部",
    "HPSY": "精神部", "HDEN": "牙科部", "HONC": "腫瘤醫學部",
}

NTUH_DEPTS = [
    "MED", "GERO", "FM", "NEUR", "GENE", "PMR", "ONC", "PSYC", "EOM",
    "SURG", "ORTH", "OBGY", "OPH", "ENT", "DENT", "DERM", "URO",
]

# 台大癌醫科別代碼（C0）
NTUCC_DEPTS = [
    "ME03", "ME04", "ME12", "ME10", "ME07", "ME02", "ME08", "ME06",
    "ME09", "ME05", "ME11", "ME15",  # 內科系
    "ONCR", "HEMA", "RT",  # 腫瘤/血液/放射
    "SR03", "SR02", "SR07", "SR04", "SR05", "SR08", "SR06",  # 外科系
    "SU04", "SU06", "SU07", "SU02", "SU08", "SU01", "SU05", "SU09",  # 外科
    "KBRC",  # 乳房醫學中心
]

# 北護分院（T2）
NTUH_BEIHU_DEPTS = [
    "MED", "PED", "FM", "NEUR", "PMR", "PSYC",
    "SURG", "ORTH", "OBGY", "OPH", "DERM", "ENT", "DENT", "URO",
]

# 金山分院（T3）
NTUH_JINSHAN_DEPTS = [
    "MED", "PED", "GERO", "FM", "NEUR", "PMR", "PSYC",
    "SURG", "ORTH", "OBGY", "OPH", "ENT", "DENT", "DERM", "URO",
]

# 新竹臺大分院（T4）
NTUH_HSINCHU_DEPTS = [
    "MED", "PED", "FM", "EOM", "PMR", "PSYC", "NEUR", "ONC", "GERO",
    "SURG", "ORTH", "OBGY", "ENT", "URO", "OPH", "DENT", "DERM",
]

# 新竹臺大生醫醫院（T7）
NTUH_BIOMEDICAL_DEPTS = [
    "MEDV", "PEDV", "FMV", "PMRV", "PSYV", "NEUV", "ONCV", "GERV",
    "SURV", "ORTV", "OBGV", "ENTV", "UROV", "OPHV", "DENV", "DERV",
    "KBRV",
]

# 雲林分院（Y0）
NTUH_YUNLIN_DEPTS = [
    "MED", "SURG", "FM", "NEUR", "ORTH", "URO", "OBGY", "PED",
    "OPH", "ENT", "DERM", "PMR", "PSYC", "DENT", "ONC",
    # 虎尾院區
    "HMED", "HSUR", "HFM", "HNEU", "HORT", "HURO", "HOBG", "HPED",
    "HOPH", "HENT", "HDER", "HPMR", "HPSY", "HDEN", "HONC",
]
TIME_CODES = ["1", "2", "3"]
TIME_NAMES = {"1": "上午診", "2": "下午診", "3": "夜診"}


class NtuhAdapter(BaseHospitalAdapter):
    """台大醫院 Adapter（支援多院區）"""

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
            # 訪問主頁面取得 session cookie + CSRF token
            token = await self._get_csrf_token(client)
            if not token:
                logger.warning(f"[{self.hospital_code}] 無法取得 CSRF token")
                return []

            for time_code in active_times:
                for dept in self.depts:
                    try:
                        results = await self._fetch_dept(
                            client, dept, time_code, now, token
                        )
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(
                            f"[{self.hospital_code}] dept={dept} "
                            f"time={time_code} 失敗: {e}"
                        )

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _get_csrf_token(self, client: httpx.AsyncClient) -> str | None:
        """從主頁面取得 __RequestVerificationToken"""
        try:
            resp = await client.get(
                f"https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo?vHospCode={self.hosp_code}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            )
            match = re.search(
                r'name="__RequestVerificationToken"[^>]*value="([^"]*)"',
                resp.text,
            )
            if match:
                return match.group(1)
        except Exception as e:
            logger.warning(f"[{self.hospital_code}] 取得 CSRF token 失敗: {e}")
        return None

    async def _fetch_dept(
        self,
        client: httpx.AsyncClient,
        dept: str,
        time_code: str,
        now: datetime,
        token: str,
    ) -> list[ClinicProgressData]:
        """查詢單一科別+時段"""
        resp = await client.post(
            self.base_url,
            data={
                "__RequestVerificationToken": token,
                "vHospitalCode": self.hosp_code,
                "DeptCode": dept,
                "RegionCode": "",
                "AmpmCode": time_code,
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo?vHospCode={self.hosp_code}",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        # 500 = 非看診時間或該科別無資料，不視為錯誤
        if resp.status_code == 500:
            return []
        resp.raise_for_status()
        return self._parse_html(resp.text, dept, time_code, now)

    def _parse_html(
        self, html: str, dept_code: str, time_code: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析回傳的 HTML（card layout: div.clinic-room-number）

        每個 card 結構：
          div.room-number     → 「24 診」
          div.clinic-doc-name → 「吳書丞」
          div.clinic-type     → 「普通門診」
          div.number          → 「019」
        """
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_NAMES.get(time_code, "未知")
        dept_name = DEPT_NAMES.get(dept_code, dept_code)
        results = []

        cards = soup.find_all("div", class_="clinic-room-number")
        for card in cards:
            # 診間
            room_el = card.find("div", class_="room-number")
            clinic_room = room_el.get_text(strip=True) if room_el else ""

            # 醫師
            doc_el = card.find("div", class_="clinic-doc-name")
            doctor = doc_el.get_text(strip=True) if doc_el else ""

            # 目前看診號碼
            num_el = card.find("div", class_="number")
            num_text = num_el.get_text(strip=True) if num_el else ""

            current_number = 0
            nums = re.findall(r"\d+", num_text)
            if nums:
                current_number = int(nums[0])

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
                next_number=0,
                is_current_skipped=False,
                is_next_skipped=False,
                fetched_at=now,
            ))

        return results

    async def get_departments(self) -> list[str]:
        """回傳中文科別名稱；對未定義的代碼，略過（不秀英文）"""
        names = []
        seen = set()
        for code in self.depts:
            name = DEPT_NAMES.get(code)
            if name and name not in seen:
                names.append(name)
                seen.add(name)
        return names


# === 預建院區（8 院區）===
ntuh_main = NtuhAdapter("ntuh", "台大醫院", "T0")
ntuh_children = NtuhAdapter("ntuh-children", "台大兒童醫院", "CH")
ntuh_cancer = NtuhAdapter("ntuh-cancer", "台大癌醫", "C0", depts=NTUCC_DEPTS)
ntuh_beihu = NtuhAdapter("ntuh-beihu", "台大北護分院", "T2", depts=NTUH_BEIHU_DEPTS)
ntuh_jinshan = NtuhAdapter("ntuh-jinshan", "台大金山分院", "T3", depts=NTUH_JINSHAN_DEPTS)
ntuh_hsinchu = NtuhAdapter("ntuh-hsinchu", "新竹台大分院", "T4", depts=NTUH_HSINCHU_DEPTS)
ntuh_biomedical = NtuhAdapter("ntuh-biomedical", "新竹台大生醫", "T7", depts=NTUH_BIOMEDICAL_DEPTS)
ntuh_yunlin = NtuhAdapter("ntuh-yunlin", "台大雲林分院", "Y0", depts=NTUH_YUNLIN_DEPTS)
