"""NHI 醫事機構資料同步服務 — 將 API 資料寫入資料庫"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.nhi_institution import NhiInstitution
from app.services.nhi_api import NhiApiService, NhiRecord

logger = logging.getLogger(__name__)


class NhiSyncService:
    """同步 NHI 開放資料到本地資料庫"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self.api = NhiApiService()

    async def sync_all(self, types: list[str] | None = None):
        """
        同步所有類型的醫事機構

        Args:
            types: 要同步的類型，預設為全部五種
        """
        if types is None:
            types = ["醫學中心", "區域醫院", "地區醫院", "診所", "藥局"]

        total_created = 0
        total_updated = 0

        for hosp_type in types:
            created, updated = await self._sync_type(hosp_type)
            total_created += created
            total_updated += updated

        logger.info(
            f"[NHI Sync] 同步完成: 新增 {total_created} 筆, 更新 {total_updated} 筆"
        )
        await self.api.close()
        return total_created, total_updated

    async def sync_hospitals_only(self):
        """只同步醫院類（醫學中心+區域醫院+地區醫院），不含診所和藥局"""
        return await self.sync_all(["醫學中心", "區域醫院", "地區醫院"])

    async def _sync_type(self, hosp_type: str) -> tuple[int, int]:
        """同步單一類型"""
        logger.info(f"[NHI Sync] 開始同步: {hosp_type}")
        records = await self.api.fetch_all_institutions(hosp_type)

        if not records:
            logger.warning(f"[NHI Sync] {hosp_type} 沒有取得任何資料")
            return 0, 0

        created = 0
        updated = 0

        # 分批寫入，每批 200 筆
        batch_size = 200
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            c, u = await self._upsert_batch(batch)
            created += c
            updated += u

        logger.info(f"[NHI Sync] {hosp_type}: 新增 {created}, 更新 {updated}")
        return created, updated

    async def _upsert_batch(self, records: list[NhiRecord]) -> tuple[int, int]:
        """批次新增或更新"""
        created = 0
        updated = 0

        async with self.session_factory() as session:
            for record in records:
                existing = await session.execute(
                    select(NhiInstitution).where(
                        NhiInstitution.hosp_id == record.hosp_id
                    )
                )
                inst = existing.scalar_one_or_none()

                if inst:
                    # 更新既有紀錄
                    inst.hosp_name = record.hosp_name
                    inst.hosp_type = record.hosp_type
                    inst.tel = record.tel
                    inst.address = record.address
                    inst.branch_type = record.branch_type
                    inst.special_type = record.special_type
                    inst.service = record.service
                    inst.departments = record.departments
                    inst.close_date = record.close_date
                    inst.schedule = record.schedule
                    inst.schedule_remark = record.schedule_remark
                    inst.gov_area_no = record.gov_area_no
                    inst.contract_start = record.contract_start
                    inst.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    # 新增紀錄
                    inst = NhiInstitution(
                        hosp_id=record.hosp_id,
                        hosp_name=record.hosp_name,
                        hosp_type=record.hosp_type,
                        tel=record.tel,
                        address=record.address,
                        branch_type=record.branch_type,
                        special_type=record.special_type,
                        service=record.service,
                        departments=record.departments,
                        close_date=record.close_date,
                        schedule=record.schedule,
                        schedule_remark=record.schedule_remark,
                        gov_area_no=record.gov_area_no,
                        contract_start=record.contract_start,
                    )
                    session.add(inst)
                    created += 1

            await session.commit()

        return created, updated


class NhiQueryService:
    """查詢本地 NHI 醫事機構資料"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None):
        if session_factory is None:
            from app.models.database import async_session
            session_factory = async_session
        self.session_factory = session_factory

    async def search_by_name(self, keyword: str, limit: int = 10) -> list[NhiInstitution]:
        """依名稱模糊搜尋"""
        async with self.session_factory() as session:
            result = await session.execute(
                select(NhiInstitution)
                .where(NhiInstitution.hosp_name.contains(keyword))
                .limit(limit)
            )
            return list(result.scalars().all())

    async def search_by_department(self, department: str, area: str | None = None, limit: int = 10) -> list[NhiInstitution]:
        """依科別搜尋"""
        query = select(NhiInstitution).where(
            NhiInstitution.departments.contains(department)
        )
        if area:
            query = query.where(NhiInstitution.address.contains(area))
        query = query.limit(limit)

        async with self.session_factory() as session:
            result = await session.execute(query)
            return list(result.scalars().all())

    async def search_hospitals(self, keyword: str, limit: int = 10) -> list[NhiInstitution]:
        """只搜醫院（不含診所、藥局）"""
        async with self.session_factory() as session:
            result = await session.execute(
                select(NhiInstitution)
                .where(
                    NhiInstitution.hosp_name.contains(keyword),
                    NhiInstitution.hosp_type.in_(["醫學中心", "區域醫院", "地區醫院"]),
                )
                .limit(limit)
            )
            return list(result.scalars().all())

    async def search_hospitals_by_area(
        self, area: str, hosp_types: list[str] | None = None, limit: int = 50
    ) -> list[NhiInstitution]:
        """依地區搜尋醫院（地址包含關鍵字）"""
        if hosp_types is None:
            hosp_types = ["醫學中心", "區域醫院"]
        async with self.session_factory() as session:
            result = await session.execute(
                select(NhiInstitution)
                .where(
                    NhiInstitution.address.contains(area),
                    NhiInstitution.hosp_type.in_(hosp_types),
                )
                .order_by(NhiInstitution.hosp_type, NhiInstitution.hosp_name)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def search_pharmacies_near(self, address_keyword: str, limit: int = 5) -> list[NhiInstitution]:
        """搜尋附近藥局（依地址關鍵字）"""
        async with self.session_factory() as session:
            result = await session.execute(
                select(NhiInstitution)
                .where(
                    NhiInstitution.hosp_type == "藥局",
                    NhiInstitution.address.contains(address_keyword),
                )
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_institution_info(self, hosp_id: str) -> NhiInstitution | None:
        """依機構代碼取得完整資訊"""
        async with self.session_factory() as session:
            result = await session.execute(
                select(NhiInstitution).where(NhiInstitution.hosp_id == hosp_id)
            )
            return result.scalar_one_or_none()

    async def get_stats(self) -> dict:
        """取得各類型機構數量統計"""
        from sqlalchemy import func
        async with self.session_factory() as session:
            result = await session.execute(
                select(NhiInstitution.hosp_type, func.count())
                .group_by(NhiInstitution.hosp_type)
            )
            return {row[0]: row[1] for row in result.all()}
