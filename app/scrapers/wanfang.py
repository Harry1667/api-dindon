"""萬芳醫院看診進度爬蟲 Adapter

資料來源：
  - 科別列表：https://wwww.wanfang.gov.tw/reg/register_visits_cload.aspx
  - 各科進度：https://wwww.wanfang.gov.tw/reg/register_visits_cload2.aspx?pidm=XXX
頁面技術：ASP.NET WebForms，cload2 為 server-side render（可直接 GET）
更新頻率：頁面每 60 秒 meta refresh

流程：
  1. 先從 cload.aspx 抓取所有科別的 pidm 連結
  2. 逐科請求 cload2.aspx?pidm=XXX 取得看診進度 HTML
  3. 解析 .card-panel 或 UpdatePanel 內的資料
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

# 共用 headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


class WanfangAdapter(BaseHospitalAdapter):
    hospital_code = "wanfang"
    hospital_name = "萬芳醫院"
    base_url = "https://wwww.wanfang.gov.tw/reg/register_visits_cload.aspx"
    dept_url = "https://wwww.wanfang.gov.tw/reg/register_visits_cload2.aspx"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """抓取萬芳醫院所有科別的看診進度

        注意：萬芳醫院 robots.txt 設定 Disallow: /（全站禁止爬蟲）
        目前為測試階段暫時啟用，正式上線前需取得授權或改用官方 API。
        """
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                # Step 1: 取得所有科別 pidm
                pidm_list = await self._fetch_department_pidms(client)
                if not pidm_list:
                    logger.warning(f"[{self.hospital_code}] 無法取得科別列表")
                    return []

                logger.info(f"[{self.hospital_code}] 取得 {len(pidm_list)} 個科別，開始逐科抓取")

                # Step 2: 逐科抓取進度
                results = []
                for pidm, dept_name in pidm_list:
                    try:
                        dept_results = await self._fetch_dept_progress(client, pidm, dept_name)
                        results.extend(dept_results)
                    except Exception as e:
                        logger.warning(f"[{self.hospital_code}] {dept_name} 抓取失敗: {e}")
                        continue

                logger.info(f"[{self.hospital_code}] 成功解析 {len(results)} 個診間")
                return results

        except httpx.HTTPError as e:
            logger.error(f"[{self.hospital_code}] 抓取失敗: {e}")
            return []

    async def _fetch_department_pidms(self, client: httpx.AsyncClient) -> list[tuple[str, str]]:
        """從科別列表頁取得所有科別的 (pidm, 科別名稱)"""
        resp = await client.get(self.base_url, headers=HEADERS)
        resp.raise_for_status()

        pidm_list = []
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.select("a[onclick*='cload2']"):
            onclick = a.get("onclick", "")
            match = re.search(r"pidm=([A-F0-9]+)", onclick)
            if match:
                pidm = match.group(1)
                name = a.get_text(strip=True)
                pidm_list.append((pidm, name))

        return pidm_list

    async def _fetch_dept_progress(
        self, client: httpx.AsyncClient, pidm: str, dept_name: str
    ) -> list[ClinicProgressData]:
        """抓取單一科別的看診進度"""
        url = f"{self.dept_url}?pidm={pidm}"
        resp = await client.get(url, headers=HEADERS)
        resp.raise_for_status()

        # 如果回傳「查無資料」就跳過
        if "查無資料" in resp.text:
            return []

        return self._parse_dept_html(resp.text, dept_name)

    def _parse_dept_html(self, html: str, dept_name: str) -> list[ClinicProgressData]:
        """解析科別進度頁面"""
        soup = BeautifulSoup(html, "lxml")
        now = datetime.now(TW_TZ)
        results = []

        # 嘗試 .card-panel 結構
        cards = soup.select(".card-panel")
        for card in cards:
            try:
                progress = self._parse_card(card, now, dept_name)
                if progress:
                    results.append(progress)
            except Exception as e:
                logger.warning(f"[{self.hospital_code}] 解析卡片失敗: {e}")
                continue

        # 如果沒有 card-panel，嘗試從 UpdatePanel 的表格解析
        if not results:
            panel = soup.select_one("#ContentPlaceHolder1_UpdatePanelUpdate")
            if panel:
                results = self._parse_panel_table(panel, now, dept_name)

        return results

    def _parse_card(self, card, now: datetime, fallback_dept: str) -> ClinicProgressData | None:
        """解析單一 .card-panel 卡片

        卡片 innerText 結構：
          2026/03/28  上午診
          精神科
          許元彰
          282診
          45    46
          目前號碼  下一號碼
          (過號)              ← 可選
        """
        text = card.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        if len(lines) < 6:
            return None

        # 第 1 行: 日期 + 診別
        date_session = lines[0]
        date_match = re.search(r"(\d{4}/\d{2}/\d{2})", date_session)
        if not date_match:
            return None
        date_str = date_match.group(1)

        session = "上午診"
        if "上午" in date_session or "早" in date_session:
            session = "上午診"
        elif "下午" in date_session or "午" in date_session:
            session = "下午診"
        elif "夜" in date_session:
            session = "夜診"

        # 第 2 行: 科別
        department = lines[1]

        # 第 3 行: 醫師
        doctor_name = lines[2]

        # 第 4 行: 診間
        clinic_room = lines[3]

        # 第 5 行: 號碼 (tab 分隔)
        numbers_line = lines[4]
        numbers = re.findall(r"\d+", numbers_line)
        if len(numbers) < 2:
            return None
        current_number = int(numbers[0])
        next_number = int(numbers[1])

        # 檢查過號狀態
        is_current_skipped = False
        is_next_skipped = False
        tables = card.select("table")
        for table in tables:
            tds = table.select("td")
            for i, td in enumerate(tds):
                td_text = td.get_text(strip=True)
                if "(過號)" in td_text or "過號" in td_text:
                    if i % 2 == 0:
                        is_current_skipped = True
                    else:
                        is_next_skipped = True

        return ClinicProgressData(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            date=date_str,
            session=session,
            department=department,
            doctor_name=doctor_name,
            clinic_room=clinic_room,
            current_number=current_number,
            next_number=next_number,
            is_current_skipped=is_current_skipped,
            is_next_skipped=is_next_skipped,
            fetched_at=now,
        )

    def _parse_panel_table(self, panel, now: datetime, dept_name: str) -> list[ClinicProgressData]:
        """從 UpdatePanel 中解析表格格式的看診進度"""
        results = []
        today_str = now.strftime("%Y/%m/%d")

        # 找所有 row-like 結構
        rows = panel.select("tr")
        for row in rows:
            tds = row.select("td")
            if len(tds) < 4:
                continue

            try:
                texts = [td.get_text(strip=True) for td in tds]

                # 嘗試從各 td 中取得 醫師、診間、號碼
                doctor_name = texts[0] if texts[0] else ""
                clinic_room = texts[1] if len(texts) > 1 else ""

                # 找數字 (目前號碼, 下一號碼)
                numbers = []
                for t in texts:
                    nums = re.findall(r"\d+", t)
                    numbers.extend(nums)

                if len(numbers) < 2:
                    continue

                current_number = int(numbers[0])
                next_number = int(numbers[1])

                # 判斷時段
                hour = now.hour
                if hour < 12:
                    session = "上午診"
                elif hour < 17:
                    session = "下午診"
                else:
                    session = "夜診"

                results.append(ClinicProgressData(
                    hospital_code=self.hospital_code,
                    hospital_name=self.hospital_name,
                    date=today_str,
                    session=session,
                    department=dept_name,
                    doctor_name=doctor_name,
                    clinic_room=clinic_room,
                    current_number=current_number,
                    next_number=next_number,
                    is_current_skipped=False,
                    is_next_skipped=False,
                    fetched_at=now,
                ))
            except Exception:
                continue

        return results

    async def get_departments(self) -> list[str]:
        """取得萬芳醫院所有科別"""
        async with httpx.AsyncClient(timeout=15.0) as client:
            pidm_list = await self._fetch_department_pidms(client)
            return sorted(set(name for _, name in pidm_list))
