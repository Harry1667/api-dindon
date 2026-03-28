"""健保特約醫事機構開放資料 API 服務"""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# NHI 開放資料 API 基礎設定
NHI_API_BASE = "https://info.nhi.gov.tw/api/iode0010/v1/rest/datastore"

# 各類醫事機構的 Resource ID
NHI_RESOURCE_IDS = {
    "醫學中心": "A21030000I-D21001-003",
    "區域醫院": "A21030000I-D21002-005",
    "地區醫院": "A21030000I-D21003-003",
    "診所": "A21030000I-D21004-009",
    "藥局": "A21030000I-D21005-001",
}


@dataclass
class NhiRecord:
    """NHI API 回傳的單筆醫事機構資料"""
    hosp_id: str
    hosp_name: str
    hosp_type: str  # 醫學中心/區域醫院/地區醫院/診所/藥局
    tel: str | None = None
    address: str | None = None
    branch_type: str | None = None
    special_type: str | None = None
    service: str | None = None
    departments: str | None = None
    close_date: str | None = None
    schedule: str | None = None
    schedule_remark: str | None = None
    gov_area_no: str | None = None
    contract_start: str | None = None


class NhiApiService:
    """NHI 開放資料 API 存取服務"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def fetch_institutions(
        self,
        hosp_type: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[NhiRecord]:
        """
        拉取指定類型的醫事機構資料

        Args:
            hosp_type: 醫學中心/區域醫院/地區醫院/診所/藥局
            limit: 每次拉取筆數（最大 1000）
            offset: 起始位置
        """
        resource_id = NHI_RESOURCE_IDS.get(hosp_type)
        if not resource_id:
            raise ValueError(f"不支援的機構類型: {hosp_type}")

        url = f"{NHI_API_BASE}/{resource_id}"
        params = {"limit": limit, "offset": offset}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                logger.error(f"[NHI API] 回應失敗: {data}")
                return []

            records = data.get("result", {}).get("records", [])
            return [self._parse_record(r, hosp_type) for r in records]

        except httpx.HTTPError as e:
            logger.error(f"[NHI API] HTTP 錯誤 ({hosp_type}): {e}")
            return []

    async def fetch_all_institutions(self, hosp_type: str) -> list[NhiRecord]:
        """拉取指定類型的所有醫事機構（自動分頁）"""
        all_records = []
        offset = 0
        batch_size = 1000

        while True:
            logger.info(f"[NHI API] 拉取 {hosp_type} offset={offset}")
            records = await self.fetch_institutions(hosp_type, limit=batch_size, offset=offset)

            if not records:
                break

            all_records.extend(records)
            offset += batch_size

            # 如果回傳筆數少於 batch_size，代表已經到最後一頁
            if len(records) < batch_size:
                break

        logger.info(f"[NHI API] {hosp_type} 共 {len(all_records)} 筆")
        return all_records

    async def fetch_all_types(self, types: list[str] | None = None) -> list[NhiRecord]:
        """
        拉取多種類型的醫事機構

        Args:
            types: 要拉取的類型列表，預設為醫院類（醫學中心+區域醫院+地區醫院）
        """
        if types is None:
            types = ["醫學中心", "區域醫院", "地區醫院"]

        all_records = []
        for hosp_type in types:
            records = await self.fetch_all_institutions(hosp_type)
            all_records.extend(records)

        return all_records

    def _parse_record(self, raw: dict, hosp_type: str) -> NhiRecord:
        """解析 API 回傳的原始 JSON 為 NhiRecord"""
        return NhiRecord(
            hosp_id=raw.get("HOSP_ID", ""),
            hosp_name=raw.get("HOSP_NAME", ""),
            hosp_type=hosp_type,
            tel=raw.get("TEL"),
            address=raw.get("ADDRESS"),
            branch_type=raw.get("BRANCH_TYPE_CNAME"),
            special_type=raw.get("SPECIAL_TYPE"),
            service=raw.get("SERVICE_CNAME"),
            departments=raw.get("FUNCTYPE_CNAME"),
            close_date=raw.get("CLOSESHOP"),
            schedule=raw.get("HOLIDAYDUTY_CNAME"),
            schedule_remark=raw.get("HOLIDAY_REMARK_CNAME"),
            gov_area_no=raw.get("GOVAREANO"),
            contract_start=raw.get("CONT_S_DATE"),
        )

    async def close(self):
        await self.client.aclose()
