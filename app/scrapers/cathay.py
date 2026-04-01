"""國泰醫院看診進度 Adapter

資料來源：https://reg.cgh.org.tw/tw/reg/RealTimeTable.jsp
技術：POST form → HTML (每次查一個診室)
流程：
  1. GET 首頁，從 JS 變數 b{hosarea}{sec} 取得所有診室代碼
  2. 逐 room POST 查詢 → 解析 Table-title-04 和目前看診序號
參數：hosarea=1(總院)/3(新竹)/4(汐止), sec=1(上午)/2(下午)/3(夜間), room=診室代號
"""

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup

from app.scrapers.base import BaseHospitalAdapter
from app.schemas.clinic import ClinicProgressData

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

CATHAY_URL = "https://reg.cgh.org.tw/tw/reg/RealTimeTable.jsp"

TIME_NAMES = {"1": "上午診", "2": "下午診", "3": "夜診"}

# 內湖院區用不同的 sec 代碼
NEIHU_SEC_MAP = {"5": "上午診", "7": "下午診", "9": "夜診"}


class CathayAdapter(BaseHospitalAdapter):
    """國泰醫院 Adapter"""

    hospital_code = "cathay"
    hospital_name = "國泰醫院"
    base_url = CATHAY_URL

    def __init__(self, hospital_code: str = "cathay", hospital_name: str = "國泰醫院", hosarea: str = "1"):
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.hosarea = hosarea
        self.base_url = CATHAY_URL

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        now = datetime.now(TW_TZ)
        hour = now.hour
        if hour < 12:
            active_times = ["1"]
        elif hour < 17:
            active_times = ["1", "2"]
        else:
            active_times = ["2", "3"]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": CATHAY_URL,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        all_results = []
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Step 1: 取得 room 列表
            room_map = await self._fetch_room_list(client)
            if not room_map:
                return []

            for sec in active_times:
                key = f"{self.hosarea}{sec}"
                rooms = room_map.get(key, [])
                if not rooms:
                    continue

                # Step 2: 並行查詢所有 room（每 10 個一批避免過載）
                for i in range(0, len(rooms), 10):
                    batch = rooms[i:i + 10]
                    tasks = [
                        self._fetch_room(client, sec, room_code, headers, now)
                        for room_code in batch
                    ]
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    for result in batch_results:
                        if isinstance(result, ClinicProgressData):
                            all_results.append(result)

        logger.info(f"[{self.hospital_code}] 取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_room_list(self, client: httpx.AsyncClient) -> dict[str, list[str]]:
        """從首頁 JS 解析所有診室代碼

        JS 格式: var b{hosarea}{sec} = ["001","001　郭志東","003","003　秦志輝",...]
        room_code 在偶數位 (0, 2, 4...)
        """
        try:
            resp = await client.get(CATHAY_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 取首頁失敗: {e}")
            return {}

        room_map: dict[str, list[str]] = {}
        for match in re.finditer(r'var\s+b(\d)(\d)\s*=\s*\[([^\]]*)\]', resp.text):
            hosarea, sec, raw = match.group(1), match.group(2), match.group(3)
            items = [s.strip().strip('"').strip("'") for s in raw.split(',') if s.strip()]
            # 提取純 room code（偶數位，不含全形空白/醫生名的）
            rooms = []
            for item in items:
                clean = item.strip()
                if clean and re.match(r'^\d+$', clean):
                    rooms.append(clean)
            key = f"{hosarea}{sec}"
            room_map[key] = rooms
            logger.info(f"[{self.hospital_code}] {key}: {len(rooms)} 個診室")

        return room_map

    async def _fetch_room(
        self,
        client: httpx.AsyncClient,
        sec: str,
        room_code: str,
        headers: dict,
        now: datetime,
    ) -> ClinicProgressData | None:
        """查詢單一診室的看診進度

        回傳 HTML 包含:
          <td class="Table-title-04">115年4月1日　上午　心臟內科　郭志東醫師</td>
          目前看診序號：75
        """
        try:
            resp = await client.post(
                CATHAY_URL,
                data={"hosarea": self.hosarea, "sec": sec, "_sec": sec, "room": room_code},
                headers=headers,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[{self.hospital_code}] room={room_code} 請求失敗: {e}")
            return None

        return self._parse_room_html(resp.text, sec, now)

    def _parse_room_html(
        self, html: str, sec: str, now: datetime
    ) -> ClinicProgressData | None:
        """解析單一診室回傳頁面"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_NAMES.get(sec, NEIHU_SEC_MAP.get(sec, "未知"))

        # 解析標題: "115年4月1日　上午　心臟內科　郭志東醫師"
        title_td = soup.find("td", class_="Table-title-04")
        if not title_td:
            return None

        title_text = title_td.get_text(strip=True)
        # 移除日期部分，取科別和醫生
        title_match = re.search(
            r'(?:上午|下午|夜間)\s*(.+?)\s+(.+?)醫師', title_text
        )
        if not title_match:
            return None

        department = title_match.group(1).strip()
        doctor = title_match.group(2).strip()

        # 解析序號: "目前看診序號：75"
        text = soup.get_text()
        seq_match = re.search(r'目前看診序號[：:]\s*(\d+)', text)
        if not seq_match:
            return None

        current_number = int(seq_match.group(1))
        if current_number == 0:
            return None

        # 嘗試取診室名
        clinic_room = ""
        room_match = re.search(r'診\s*室[：:]\s*(\S+)', text)
        if room_match:
            clinic_room = room_match.group(1)

        return ClinicProgressData(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            date=date_str,
            session=session,
            department=department,
            doctor_name=doctor,
            clinic_room=clinic_room or department,
            current_number=current_number,
            next_number=current_number + 1,
            is_current_skipped=False,
            is_next_skipped=False,
            fetched_at=now,
        )

    async def get_departments(self) -> list[str]:
        all_progress = await self.fetch_all_progress()
        return sorted(set(p.department for p in all_progress))


# === 預建院區 ===
# hosarea: 1=總院(台北), 3=新竹國泰, 4=汐止國泰
cathay_xizhi = CathayAdapter("cathay-xizhi", "汐止國泰", "4")
