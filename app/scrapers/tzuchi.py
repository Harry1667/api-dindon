"""慈濟醫院看診進度 Adapter

資料來源：https://reg-prod.tzuchi-healthcare.org.tw/tchw/HIS5OpdReg/OpdProgress
技術：ASP.NET WebForms POST（需 ViewState）
參數：Loc=TC(台北)/XD(新店), DeptCode=科別代碼, Session=時段(1/2/3)

流程：
  1. GET 頁面取得 ViewState + EventValidation + 科別列表
  2. POST 查詢各科別+時段的看診進度
"""

import logging
import re
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup

from app.scrapers.base import BaseHospitalAdapter
from app.schemas.clinic import ClinicProgressData
from app.config import settings

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

BASE_URL = "https://reg-prod.tzuchi-healthcare.org.tw/tchw/HIS5OpdReg/OpdProgress"

SESSION_MAP = {"1": "上午診", "2": "下午診", "3": "夜診"}


class TzuchiAdapter(BaseHospitalAdapter):
    """慈濟醫院 Adapter — 支援多院區"""

    def __init__(
        self,
        hospital_code: str,
        hospital_name: str,
        loc: str,
    ):
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.loc = loc  # TC=台北, XD=新店
        self.base_url = f"{BASE_URL}?Loc={loc}"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """取得所有科別的看診進度"""
        now = datetime.now(TW_TZ)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        # 根據時間決定時段
        hour = now.hour
        if hour < 12:
            active_sessions = ["1"]
        elif hour < 17:
            active_sessions = ["1", "2"]
        else:
            active_sessions = ["2", "3"]

        proxy = settings.socks5_proxy or None
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
            follow_redirects=True,
            proxy=proxy,
        ) as client:
            # Step 1: GET 頁面取得 form state + 科別
            try:
                resp = await client.get(self.base_url, headers=headers)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[{self.hospital_code}] 取頁面失敗: {e}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")

            # 取得 ASP.NET 表單狀態
            viewstate = self._get_hidden(soup, "__VIEWSTATE")
            eventval = self._get_hidden(soup, "__EVENTVALIDATION")
            viewstate_gen = self._get_hidden(soup, "__VIEWSTATEGENERATOR")

            if not viewstate or not eventval:
                logger.error(f"[{self.hospital_code}] 無法取得 ViewState")
                return []

            # 取得科別列表
            dept_select = soup.find("select", {"id": "MainContent_DeptCode"})
            if not dept_select:
                logger.error(f"[{self.hospital_code}] 無法取得科別下拉選單")
                return []

            depts = []
            for opt in dept_select.find_all("option"):
                code = opt.get("value", "")
                name = opt.get_text(strip=True)
                if code and name:
                    depts.append((code, name))

            logger.info(f"[{self.hospital_code}] 找到 {len(depts)} 個科別")

            # Step 2: 逐科+時段查詢
            all_results = []
            for session_code in active_sessions:
                for dept_code, dept_name in depts:
                    try:
                        results = await self._fetch_dept(
                            client,
                            dept_code,
                            dept_name,
                            session_code,
                            viewstate,
                            eventval,
                            viewstate_gen,
                            headers,
                            now,
                        )
                        all_results.extend(results)

                        # 更新 viewstate from response (ASP.NET 需要)
                        # 注意: 有些 ASP.NET 頁面每次 POST 後 viewstate 會變
                    except Exception as e:
                        logger.warning(
                            f"[{self.hospital_code}] {dept_name} session={session_code} 失敗: {e}"
                        )

        logger.info(f"[{self.hospital_code}] 共取得 {len(all_results)} 個診間")
        return all_results

    def _get_hidden(self, soup: BeautifulSoup, name: str) -> str:
        """取得 hidden field 的值"""
        field = soup.find("input", {"name": name})
        return field["value"] if field else ""

    async def _fetch_dept(
        self,
        client: httpx.AsyncClient,
        dept_code: str,
        dept_name: str,
        session_code: str,
        viewstate: str,
        eventval: str,
        viewstate_gen: str,
        headers: dict,
        now: datetime,
    ) -> list[ClinicProgressData]:
        """查詢單一科別+時段"""
        form_data = {
            "__VIEWSTATE": viewstate,
            "__EVENTVALIDATION": eventval,
            "__VIEWSTATEGENERATOR": viewstate_gen,
            "ctl00$MainContent$DeptCode": dept_code,
            "ctl00$MainContent$Session": session_code,
            "ctl00$MainContent$btnQuery": "查詢",
        }

        resp = await client.post(
            self.base_url,
            data=form_data,
            headers={
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": self.base_url,
            },
        )
        resp.raise_for_status()
        return self._parse_html(resp.text, dept_name, session_code, now)

    def _parse_html(
        self, html: str, dept_name: str, session_code: str, now: datetime
    ) -> list[ClinicProgressData]:
        """解析看診進度表格"""
        soup = BeautifulSoup(html, "html.parser")
        date_str = now.strftime("%Y/%m/%d")
        session = SESSION_MAP.get(session_code, "未知")
        results = []

        # 查無資料
        if "查無資料" in soup.get_text():
            return []

        # 找資料 table（通常在 GridView 或 repeater）
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            # 檢查是否為資料表（header 含「醫師」「診間」「號碼」等）
            header_text = rows[0].get_text() if rows else ""
            if not any(
                kw in header_text
                for kw in ["醫師", "診間", "號碼", "看診", "燈號", "目前"]
            ):
                continue

            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                texts = [c.get_text(strip=True) for c in cells]

                doctor = ""
                clinic_room = ""
                current_number = 0

                for text in texts:
                    if not text:
                        continue
                    if re.match(r"^\d+$", text) and current_number == 0:
                        current_number = int(text)
                    elif re.match(r"^\d+診?$", text) and not clinic_room:
                        clinic_room = text
                    elif "科" not in text and len(text) >= 2 and len(text) <= 10 and not doctor:
                        doctor = text

                if current_number > 0:
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
                            next_number=current_number + 1,
                            is_current_skipped=False,
                            is_next_skipped=False,
                            fetched_at=now,
                        )
                    )

        return results

    async def get_departments(self) -> list[str]:
        """取得科別列表"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, proxy=settings.socks5_proxy or None) as client:
                resp = await client.get(self.base_url, headers=headers)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                dept_select = soup.find("select", {"id": "MainContent_DeptCode"})
                if dept_select:
                    return [
                        opt.get_text(strip=True)
                        for opt in dept_select.find_all("option")
                        if opt.get("value")
                    ]
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 取科別失敗: {e}")
        return []


# === 預建院區 ===
tzuchi_taipei = TzuchiAdapter("tzuchi-taipei", "台北慈濟醫院", "TC")
tzuchi_xindian = TzuchiAdapter("tzuchi-xindian", "台北慈濟醫院(新店)", "XD")
