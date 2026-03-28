"""新北市立聯合醫院看診進度 Adapter（政府開放資料 API）

資料來源：data.ntpc.gov.tw 開放資料平台
API 格式：JSON（每 5 分鐘更新）
板橋院區 Dataset ID：00f8fa51-cedc-4c1d-88b0-58c55f740b79
三重院區 Dataset ID：0abdf2d0-3246-4614-b715-d4ed6631eb16

欄位：
  deptid, deptname, opdtimeid, roomid, roomname, roomlocation,
  doctorname, subdoctorname,
  callednumber_seqno (目前看診號), calledmaxnumber_seqno (最大看診號),
  waitcount_person (等待人數), regcount_person (已掛號人數),
  memo_remark
"""

import logging
from datetime import datetime, timezone, timedelta

import httpx

from app.scrapers.base import BaseHospitalAdapter
from app.schemas.clinic import ClinicProgressData

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

# 新北市開放資料 API base URL
NTPC_API_BASE = "https://data.ntpc.gov.tw/api/datasets/{dataset_id}/json"

# 午別代碼對照
OPDTIME_MAP = {
    "1": "上午診",
    "2": "下午診",
    "3": "夜診",
}


class NewTaipeiUnitedAdapter(BaseHospitalAdapter):
    """新北市立聯合醫院 Adapter — 支援多院區，透過 dataset_id 切換"""

    def __init__(self, hospital_code: str, hospital_name: str, dataset_id: str):
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.dataset_id = dataset_id
        self.base_url = NTPC_API_BASE.format(dataset_id=dataset_id)

    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """從新北市開放資料 API 取得看診進度"""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    self.base_url,
                    params={"size": 200},  # 足夠涵蓋所有診間
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"[{self.hospital_code}] API 請求失敗: {e}")
            return []
        except Exception as e:
            logger.error(f"[{self.hospital_code}] JSON 解析失敗: {e}")
            return []

        if not isinstance(data, list):
            logger.warning(f"[{self.hospital_code}] API 回傳非陣列: {type(data)}")
            return []

        now = datetime.now(TW_TZ)
        date_str = now.strftime("%Y/%m/%d")
        results = []

        for record in data:
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
        """解析單筆 API 回傳紀錄"""
        # 科別名稱（移除院區前綴，如 "板橋_骨科 " → "骨科"）
        dept_name = (record.get("deptname") or "").strip()
        if "_" in dept_name:
            dept_name = dept_name.split("_", 1)[1].strip()

        doctor_name = (record.get("doctorname") or "").strip()
        if not dept_name or not doctor_name:
            return None

        # 目前看診號
        current_num_str = record.get("callednumber_seqno", "0")
        current_number = int(current_num_str) if current_num_str.isdigit() else 0

        # 最大看診號（作為 next_number 的參考）
        max_num_str = record.get("calledmaxnumber_seqno", "0")
        max_number = int(max_num_str) if max_num_str.isdigit() else 0

        # 等待人數與掛號人數（額外資訊）
        wait_count_str = record.get("waitcount_person", "0")
        wait_count = int(wait_count_str) if wait_count_str.isdigit() else 0

        # 如果目前看診號為 0 且沒有等待人數，可能是已結束的診間
        if current_number == 0 and wait_count == 0:
            return None

        # 午別
        opdtime_id = record.get("opdtimeid", "")
        session = OPDTIME_MAP.get(opdtime_id, "未知")

        # 診間名稱
        room_name = (record.get("roomname") or record.get("roomid") or "").strip()

        # next_number: 看診號+1（API 沒有直接提供下一號）
        next_number = current_number + 1 if current_number > 0 else 0

        return ClinicProgressData(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            date=date_str,
            session=session,
            department=dept_name,
            doctor_name=doctor_name,
            clinic_room=room_name,
            current_number=current_number,
            next_number=next_number,
            is_current_skipped=False,  # API 無過號資訊
            is_next_skipped=False,
            fetched_at=now,
        )

    async def get_departments(self) -> list[str]:
        """取得所有科別"""
        all_progress = await self.fetch_all_progress()
        return sorted(set(p.department for p in all_progress))


# === 預建兩個院區的 Adapter 實例 ===

banqiao_adapter = NewTaipeiUnitedAdapter(
    hospital_code="newtaipei-banqiao",
    hospital_name="新北聯合醫院(板橋)",
    dataset_id="00f8fa51-cedc-4c1d-88b0-58c55f740b79",
)

sanchong_adapter = NewTaipeiUnitedAdapter(
    hospital_code="newtaipei-sanchong",
    hospital_name="新北聯合醫院(三重)",
    dataset_id="0abdf2d0-3246-4614-b715-d4ed6631eb16",
)
