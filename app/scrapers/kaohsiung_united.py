"""高雄市立聯合醫院看診進度 Adapter（高雄城市資料平台 API）

資料來源：api.kcg.gov.tw 高雄城市資料平台
API 格式：JSON（即時更新）
API 網址：https://api.kcg.gov.tw/api/service/Get/8cd9aba3-bbbc-4801-b267-5e9ee9ff50a6

回傳欄位（在 data.ProcessInfo 陣列中）：
  DeptName (科別), SectionName (診間號), NoonName (午別),
  EmployeeName (醫師), CurNum (目前看診號)
"""

import logging
from datetime import datetime, timezone, timedelta

import httpx

from app.scrapers.base import BaseHospitalAdapter
from app.schemas.clinic import ClinicProgressData

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

KCG_API_URL = (
    "https://api.kcg.gov.tw/api/service/Get/"
    "8cd9aba3-bbbc-4801-b267-5e9ee9ff50a6"
)


class KaohsiungUnitedAdapter(BaseHospitalAdapter):
    """高雄市立聯合醫院 Adapter — 高雄市政府開放資料 API"""

    hospital_code = "kaohsiung-united"
    hospital_name = "高雄聯合醫院"
    base_url = KCG_API_URL

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """從高雄城市資料平台 API 取得看診進度"""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.base_url,
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"[{self.hospital_code}] API 請求失敗: {e}")
            return []
        except Exception as e:
            logger.error(f"[{self.hospital_code}] JSON 解析失敗: {e}")
            return []

        # 檢查回傳結構
        if not payload.get("success"):
            logger.warning(f"[{self.hospital_code}] API 回傳 success=false")
            return []

        data = payload.get("data", {})
        rtn_code = str(data.get("RtnCode", ""))

        # RtnCode != 0 代表 HIS 系統沒回應（例如非看診時間）
        if rtn_code != "0":
            rtn_msg = data.get("RtnMsg", "")
            logger.info(
                f"[{self.hospital_code}] HIS 回傳 code={rtn_code}: {rtn_msg[:100]}"
            )
            return []

        process_info = data.get("ProcessInfo", [])
        if not isinstance(process_info, list):
            logger.warning(f"[{self.hospital_code}] ProcessInfo 非陣列")
            return []

        now = datetime.now(TW_TZ)
        date_str = now.strftime("%Y/%m/%d")
        results = []

        for record in process_info:
            try:
                progress = self._parse_record(record, date_str, now)
                if progress:
                    results.append(progress)
            except Exception as e:
                logger.warning(f"[{self.hospital_code}] 解析紀錄失敗: {e}")
                continue

        logger.info(f"[{self.hospital_code}] API 取得 {len(results)} 個診間")
        return results

    def _parse_record(
        self, record: dict, date_str: str, now: datetime
    ) -> ClinicProgressData | None:
        """解析單筆看診進度紀錄"""
        dept_name = (record.get("DeptName") or "").strip()
        doctor_name = (record.get("EmployeeName") or "").strip()
        if not dept_name or not doctor_name:
            return None

        # 目前看診號
        cur_num_str = str(record.get("CurNum", "0"))
        current_number = int(cur_num_str) if cur_num_str.isdigit() else 0

        if current_number == 0:
            return None

        # 午別
        noon_name = (record.get("NoonName") or "").strip()
        session = noon_name if noon_name else "未知"
        # 統一格式
        if "上午" in session or "早" in session:
            session = "上午診"
        elif "下午" in session:
            session = "下午診"
        elif "夜" in session or "晚" in session:
            session = "夜診"

        # 診間
        section_name = (record.get("SectionName") or "").strip()

        return ClinicProgressData(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            date=date_str,
            session=session,
            department=dept_name,
            doctor_name=doctor_name,
            clinic_room=section_name,
            current_number=current_number,
            next_number=current_number + 1,  # API 沒提供 next，+1 估算
            is_current_skipped=False,
            is_next_skipped=False,
            fetched_at=now,
        )

    async def get_departments(self) -> list[str]:
        """取得所有科別"""
        all_progress = await self.fetch_all_progress()
        return sorted(set(p.department for p in all_progress))
