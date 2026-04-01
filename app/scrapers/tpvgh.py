"""台北榮總看診進度 Adapter

資料來源：https://m.vghtpe.gov.tw:6443/MobileWeb/roomsta/ (Mobile 版，無 Cloudflare)
桌面版 www6.vghtpe.gov.tw 有 Cloudflare 403 擋，改用 Mobile API

流程：
  1. GET /roomsta/seltime?selTime={0|1|2} → 列出當前時段的科別 section codes
  2. GET /roomsta/selsect?selTime={0|1|2}&selSect={code} → 取得該科看診進度

HTML 結構（li.textbox）：
  <font> 科別名稱
  <i>    子科別/備註
  <b>    醫師名 空格 診間號
  <b>    已叫最大號燈：{number}
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

MOBILE_BASE = "https://m.vghtpe.gov.tw:6443/MobileWeb/roomsta"

TIME_CODES = {"0": "上午診", "1": "下午診", "2": "夜診"}


class TpvghAdapter(BaseHospitalAdapter):
    """台北榮總 Adapter — 使用 Mobile Web（繞過 Cloudflare）"""

    hospital_code = "tpvgh"
    hospital_name = "台北榮總"
    base_url = MOBILE_BASE

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """先取各時段科別列表，再逐一查進度"""
        now = datetime.now(TW_TZ)
        hour = now.hour
        if hour < 12:
            active_times = ["0"]
        elif hour < 17:
            active_times = ["0", "1"]
        else:
            active_times = ["1", "2"]

        all_results = []
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True, verify=False
        ) as client:
            for time_code in active_times:
                # Step 1: 取得該時段的科別
                sections = await self._fetch_sections(client, time_code)
                if not sections:
                    continue

                # Step 2: 逐科查詢
                for sect_code, sect_name in sections:
                    try:
                        results = await self._fetch_section_progress(
                            client, time_code, sect_code, sect_name, now
                        )
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(
                            f"[{self.hospital_code}] {sect_name}({sect_code}) 失敗: {e}"
                        )

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_sections(
        self, client: httpx.AsyncClient, time_code: str
    ) -> list[tuple[str, str]]:
        """取得指定時段的科別列表"""
        try:
            resp = await client.get(
                f"{MOBILE_BASE}/seltime",
                params={"selTime": time_code},
                headers={
                    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
                },
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 取時段 {time_code} 科別失敗: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        sections = []

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            match = re.search(r"selSect=(\w+)", href)
            if match and text:
                sections.append((match.group(1), text))

        logger.info(
            f"[{self.hospital_code}] 時段 {TIME_CODES.get(time_code, '?')}: "
            f"{len(sections)} 個科別"
        )
        return sections

    async def _fetch_section_progress(
        self,
        client: httpx.AsyncClient,
        time_code: str,
        sect_code: str,
        sect_name: str,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一科別的看診進度"""
        resp = await client.get(
            f"{MOBILE_BASE}/selsect",
            params={"selTime": time_code, "selSect": sect_code},
            headers={
                "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
            },
        )
        resp.raise_for_status()
        return self._parse_section_html(resp.text, sect_name, time_code, now)

    def _parse_section_html(
        self, html: str, sect_name: str, time_code: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析科別看診進度頁面

        每個 li.textbox 的結構：
          <font> 科別名稱（如「心臟內科」）
          <i>    子科別/備註
          <b>    醫師名 空格 診間號（如「王大明　　0123診」）
          <b>    已叫最大號燈：{number}
        """
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = TIME_CODES.get(time_code, "未知")
        results = []

        textboxes = soup.find_all("li", class_="textbox")
        for li in textboxes:
            try:
                progress = self._parse_textbox(li, sect_name, date_str, session, now)
                if progress:
                    results.append(progress)
            except Exception as e:
                logger.warning(f"[{self.hospital_code}] 解析 textbox 失敗: {e}")

        return results

    def _parse_textbox(
        self, li, sect_name: str, date_str: str, session: str, now: datetime
    ) -> ClinicProgressData | None:
        """解析單一 li.textbox

        HTML 結構（3 個 <b> 標籤）:
          <font><b>科別-午別</b></font>   ← bolds[0] (在 font 裡)
          <b>醫師名　　XXXX診</b>         ← bolds[1]
          <b>已叫最大號燈：N</b>           ← bolds[2]
        """
        # 科別名稱
        font = li.find("font")
        department = font.get_text(strip=True) if font else sect_name

        # 如果是「門診時間」等非看診資料，跳過
        if "門診時間" in department:
            return None

        # 找所有 <b>，排除 font 內的（科別標題）
        all_bolds = li.find_all("b")
        # 過濾掉在 <font> 裡面的 <b>
        bolds = [b for b in all_bolds if not b.find_parent("font")]
        if len(bolds) < 2:
            return None

        # 第一個非 font 內的 <b>: "醫師名　　XXXX診"
        doctor_room_text = bolds[0].get_text(strip=True)
        # 第二個非 font 內的 <b>: "已叫最大號燈：N"
        number_text = bolds[1].get_text(strip=True)

        # 解析醫師和診間
        # 格式: "王大明　　0123診" 或 "排班醫師　　0099診"
        doctor = ""
        clinic_room = ""
        room_match = re.search(r"(\d+診)", doctor_room_text)
        if room_match:
            clinic_room = room_match.group(1)
            doctor = doctor_room_text[: room_match.start()].strip()
            # 移除全形空白
            doctor = re.sub(r"[\u3000\s]+", "", doctor)
        else:
            doctor = doctor_room_text.strip()

        # 解析號碼: "已叫最大號燈：0" → 0
        num_match = re.search(r"(\d+)", number_text)
        current_number = int(num_match.group(1)) if num_match else 0

        if current_number == 0:
            return None

        # 子科別/備註
        italic = li.find("i")
        sub_dept = italic.get_text(strip=True) if italic else ""
        if sub_dept:
            department = f"{department}-{sub_dept}"

        return ClinicProgressData(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            date=date_str,
            session=session,
            department=department,
            doctor_name=doctor,
            clinic_room=clinic_room,
            current_number=current_number,
            next_number=current_number + 1,
            is_current_skipped=False,
            is_next_skipped=False,
            fetched_at=now,
        )

    async def get_departments(self) -> list[str]:
        """取得所有科別"""
        departments = set()
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True, verify=False
        ) as client:
            for time_code in ["0", "1", "2"]:
                sections = await self._fetch_sections(client, time_code)
                for _, name in sections:
                    departments.add(name)
        return sorted(departments)
