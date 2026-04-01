"""亞東紀念醫院看診進度 Adapter

資料來源：https://www.femh.org.tw/visit/visit.aspx?Action=9
技術：ASP.NET WebForms __doPostBack
流程：
  1. GET 頁面取得 ViewState + EventValidation
  2. POST DD2 (時段) 觸發 PostBack → 伺服器回傳填充過的 DD1 (科別)
  3. 選科別 → POST Button1 查詢 → 解析看診進度 table

注意：週日/非看診時段 DD1 會是空的（正常現象）
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

VISIT_URL = "https://www.femh.org.tw/visit/visit.aspx?Action=9"

SESSION_MAP = {"1": "上午診", "2": "下午診", "3": "夜診"}


class FemhAdapter(BaseHospitalAdapter):
    """亞東紀念醫院 Adapter"""

    hospital_code = "femh"
    hospital_name = "亞東醫院"
    base_url = VISIT_URL

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        now = datetime.now(TW_TZ)
        hour = now.hour
        if hour < 12:
            active_sessions = ["1"]
        elif hour < 17:
            active_sessions = ["1", "2"]
        else:
            active_sessions = ["2", "3"]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        all_results = []
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True, verify=False
        ) as client:
            for session_code in active_sessions:
                try:
                    results = await self._fetch_session(
                        client, session_code, headers, now
                    )
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(
                        f"[{self.hospital_code}] session={session_code} 失敗: {e}"
                    )

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    async def _fetch_session(
        self,
        client: httpx.AsyncClient,
        session_code: str,
        headers: dict,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢一個時段的所有科別"""

        # Step 1: GET 頁面取得 form state
        resp = await client.get(VISIT_URL, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        form_state = self._extract_form_state(soup)
        if not form_state:
            return []

        # Step 2: POST 選時段 → 觸發 PostBack 填充科別
        form_data = {
            **form_state,
            "__EVENTTARGET": "ctl00$MainContent$ctl00$DropDownList2",
            "__EVENTARGUMENT": "",
            "ctl00$MainContent$ctl00$DropDownList1": "",
            "ctl00$MainContent$ctl00$DropDownList2": session_code,
            "ctl00$MainContent$ctl00$TextBox1": "",
        }

        resp2 = await client.post(
            VISIT_URL,
            data=form_data,
            headers={
                **headers,
                "Referer": VISIT_URL,
            },
        )
        resp2.raise_for_status()
        soup2 = BeautifulSoup(resp2.text, "html.parser")

        # 取得科別列表
        dd1 = soup2.find(id="MainContent_ctl00_DropDownList1")
        if not dd1:
            return []

        depts = []
        for opt in dd1.find_all("option"):
            val = opt.get("value", "")
            name = opt.get_text(strip=True)
            if val and name and name != "請選擇科別":
                depts.append((val, name))

        if not depts:
            logger.info(
                f"[{self.hospital_code}] session={session_code} 無科別（可能非看診時段）"
            )
            return []

        logger.info(
            f"[{self.hospital_code}] session={session_code} 找到 {len(depts)} 個科別"
        )

        # Step 3: 逐科查詢
        form_state2 = self._extract_form_state(soup2)
        all_results = []

        for dept_code, dept_name in depts:
            try:
                results = await self._fetch_dept(
                    client,
                    dept_code,
                    dept_name,
                    session_code,
                    form_state2,
                    headers,
                    now,
                )
                all_results.extend(results)

                # 更新 form state（ASP.NET 可能每次都變）
                # 但為了速度，只用初始的 form_state2
            except Exception as e:
                logger.warning(
                    f"[{self.hospital_code}] {dept_name} 失敗: {e}"
                )

        return all_results

    async def _fetch_dept(
        self,
        client: httpx.AsyncClient,
        dept_code: str,
        dept_name: str,
        session_code: str,
        form_state: dict,
        headers: dict,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一科別的看診進度"""
        form_data = {
            **form_state,
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "ctl00$MainContent$ctl00$DropDownList1": dept_code,
            "ctl00$MainContent$ctl00$DropDownList2": session_code,
            "ctl00$MainContent$ctl00$TextBox1": "",
            "ctl00$MainContent$ctl00$Button1": "查詢",
        }

        resp = await client.post(
            VISIT_URL,
            data=form_data,
            headers={**headers, "Referer": VISIT_URL},
        )
        resp.raise_for_status()
        return self._parse_html(resp.text, dept_name, session_code, now)

    def _extract_form_state(self, soup: BeautifulSoup) -> dict | None:
        """提取 ASP.NET 表單隱藏欄位"""
        vs = soup.find("input", {"name": "__VIEWSTATE"})
        ev = soup.find("input", {"name": "__EVENTVALIDATION"})
        if not vs or not ev:
            return None
        vsg = soup.find("input", {"name": "__VIEWSTATEGENERATOR"})
        return {
            "__VIEWSTATE": vs["value"],
            "__EVENTVALIDATION": ev["value"],
            "__VIEWSTATEGENERATOR": vsg["value"] if vsg else "",
            "__SCROLLPOSITIONX": "0",
            "__SCROLLPOSITIONY": "0",
        }

    def _parse_html(
        self, html: str, dept_name: str, session_code: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析看診進度

        亞東 HTML table 固定 8 欄:
          [0] 看診日期   (如 "115/04/01(星期三)")
          [1] 時段      (如 "早上")
          [2] 看診科別   (如 "一般外科")
          [3] 診間      (如 "F211")
          [4] 看診醫師   (如 "趙余俊")
          [5] 掛號人數   (如 "28")
          [6] 下一號    (如 "4")
          [7] 目前看診號  (如 "35號...")
        """
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = SESSION_MAP.get(session_code, "未知")
        results = []

        tab1 = soup.find(id="order-tab1")
        search_area = tab1 if tab1 else soup

        for table in search_area.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            for row in rows[1:]:
                # 跳過展開用的 collapse 行
                row_class = row.get("class", [])
                if "collapse" in row_class or "row-collapse" in row_class:
                    continue

                cells = row.find_all("td")
                if len(cells) < 8:
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                clinic_room = texts[3]   # 診間
                doctor = texts[4]        # 看診醫師

                # 目前看診號（可能帶 "號" 字尾或 "..."）
                current_match = re.search(r"(\d+)", texts[7])
                current_number = int(current_match.group(1)) if current_match else 0

                if current_number == 0 or not doctor:
                    continue

                # 掛號人數 → next_number
                registered_match = re.search(r"(\d+)", texts[5])
                registered = int(registered_match.group(1)) if registered_match else 0
                next_number = registered if registered > current_number else current_number + 1

                results.append(
                    ClinicProgressData(
                        hospital_code=self.hospital_code,
                        hospital_name=self.hospital_name,
                        date=date_str,
                        session=session,
                        department=dept_name,
                        doctor_name=doctor,
                        clinic_room=clinic_room or dept_name,
                        current_number=current_number,
                        next_number=next_number,
                        is_current_skipped=False,
                        is_next_skipped=False,
                        fetched_at=now,
                    )
                )

        return results

    async def get_departments(self) -> list[str]:
        """取得所有科別（需要選時段才能取得）"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        all_depts = set()
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True, verify=False
        ) as client:
            for session_code in ["1", "2", "3"]:
                try:
                    resp = await client.get(VISIT_URL, headers=headers)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    form_state = self._extract_form_state(soup)
                    if not form_state:
                        continue

                    form_data = {
                        **form_state,
                        "__EVENTTARGET": "ctl00$MainContent$ctl00$DropDownList2",
                        "__EVENTARGUMENT": "",
                        "ctl00$MainContent$ctl00$DropDownList1": "",
                        "ctl00$MainContent$ctl00$DropDownList2": session_code,
                        "ctl00$MainContent$ctl00$TextBox1": "",
                    }
                    resp2 = await client.post(
                        VISIT_URL, data=form_data, headers=headers
                    )
                    soup2 = BeautifulSoup(resp2.text, "html.parser")
                    dd1 = soup2.find(id="MainContent_ctl00_DropDownList1")
                    if dd1:
                        for opt in dd1.find_all("option"):
                            name = opt.get_text(strip=True)
                            if name and name != "請選擇科別":
                                all_depts.add(name)
                except Exception:
                    pass
        return sorted(all_depts)
