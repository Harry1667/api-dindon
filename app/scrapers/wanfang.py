"""萬芳醫院看診進度爬蟲 Adapter

資料來源：https://wwww.wanfang.gov.tw/reg/register_visits_cload3.aspx
頁面技術：ASP.NET WebForms，純 GET 即可取得所有資料
更新頻率：頁面每 60 秒 meta refresh
資料結構：每個診間為一個 .card-panel 元素
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


class WanfangAdapter(BaseHospitalAdapter):
    hospital_code = "wanfang"
    hospital_name = "萬芳醫院"
    base_url = "https://wwww.wanfang.gov.tw/reg/register_visits_cload3.aspx"

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """抓取萬芳醫院所有目前看診中的診間進度"""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.base_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"[{self.hospital_code}] 抓取失敗: {e}")
            return []

        return self._parse_html(resp.text)

    def _parse_html(self, html: str) -> list[ClinicProgressData]:
        """解析 HTML，從 .card-panel 元素中提取看診進度"""
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(".card-panel")
        now = datetime.now(TW_TZ)
        results = []

        for card in cards:
            try:
                progress = self._parse_card(card, now)
                if progress:
                    results.append(progress)
            except Exception as e:
                logger.warning(f"[{self.hospital_code}] 解析卡片失敗: {e}")
                continue

        logger.info(f"[{self.hospital_code}] 成功解析 {len(results)} 個診間")
        return results

    def _parse_card(self, card, now: datetime) -> ClinicProgressData | None:
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
        full_text = card.get_text()

        # 找所有 (過號) 的位置來判斷是目前號碼過號還是下一號碼過號
        # 方法: 檢查 table 結構中 (過號) 出現在哪一個欄位
        tables = card.select("table")
        for table in tables:
            tds = table.select("td")
            for i, td in enumerate(tds):
                td_text = td.get_text(strip=True)
                if "(過號)" in td_text or "過號" in td_text:
                    # 偶數 index = 左欄 (目前號碼), 奇數 index = 右欄 (下一號碼)
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

    async def get_departments(self) -> list[str]:
        """取得萬芳醫院所有科別（從即時進度頁面解析）"""
        all_progress = await self.fetch_all_progress()
        departments = sorted(set(p.department for p in all_progress))
        return departments
