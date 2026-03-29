"""FastAPI 主程式入口"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from app.config import settings
from app.api.webhook import router as webhook_router
from app.models.database import engine, Base

# 確保所有 Model 都被 import，create_all 才能建立資料表
import app.models.hospital  # noqa: F401
import app.models.user  # noqa: F401
import app.models.tracking_task  # noqa: F401
import app.models.clinic_progress  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.nhi_institution  # noqa: F401
import app.models.hospital_alias  # noqa: F401
import app.models.user_query_history  # noqa: F401
import app.models.department  # noqa: F401
import app.models.doctor  # noqa: F401

# 設定 logging
logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    logger.info("🚀 醫院掛號排隊通知系統啟動中...")

    # 建立資料表（開發用，正式環境用 Alembic migration）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ 資料庫初始化完成")

    # 插入預設醫院資料
    await _seed_hospitals()
    await _seed_hospital_aliases()

    # 載入別名解析器到記憶體
    from app.services.hospital_resolver import hospital_resolver
    await hospital_resolver.load()

    yield

    # 關閉連線
    await engine.dispose()
    logger.info("👋 系統已關閉")


async def _seed_hospitals():
    """初始化醫院資料"""
    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.hospital import Hospital

    seeds = [
        # === 台北市 醫學中心 ===
        {"code": "wanfang", "name": "萬芳醫院",
         "url": "https://wwww.wanfang.gov.tw/reg/register_visits_cload3.aspx",
         "adapter_name": "WanfangAdapter", "scrape_interval": 60},
        {"code": "ntuh", "name": "台大醫院",
         "url": "https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo?vHospCode=T0",
         "adapter_name": "NtuhAdapter", "scrape_interval": 60},
        {"code": "ntuh-children", "name": "台大兒童醫院",
         "url": "https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo?vHospCode=CH",
         "adapter_name": "NtuhAdapter", "scrape_interval": 60},
        {"code": "tpvgh", "name": "台北榮總",
         "url": "https://m.vghtpe.gov.tw:6443/MobileWeb/roomsta/",
         "adapter_name": "TpvghAdapter", "scrape_interval": 60},
        {"code": "changgung-taipei", "name": "台北長庚",
         "url": "https://register.cgmh.org.tw/Progress/1",
         "adapter_name": "ChangGungAdapter", "scrape_interval": 60},
        {"code": "mackay-taipei", "name": "馬偕醫院(台北)",
         "url": "https://www.mmh.org.tw/progress.php",
         "adapter_name": "MackayAdapter", "scrape_interval": 60},
        {"code": "cathay", "name": "國泰醫院",
         "url": "https://reg.cgh.org.tw/tw/reg/RealTimeTable.jsp",
         "adapter_name": "CathayAdapter", "scrape_interval": 60},
        {"code": "shinkong", "name": "新光醫院",
         "url": "https://www.skh.org.tw/skh_regis/",
         "adapter_name": "ShinkongAdapter", "scrape_interval": 60},
        {"code": "tsgh", "name": "三軍總醫院",
         "url": "https://www2.ndmutsgh.edu.tw/NumberStatus/data/cache.json",
         "adapter_name": "TsghAdapter", "scrape_interval": 60},
        # === 台北市 區域醫院 ===
        {"code": "mackay-tamsui", "name": "馬偕醫院(淡水)",
         "url": "https://www.mmh.org.tw/progress.php",
         "adapter_name": "MackayAdapter", "scrape_interval": 60},
        # === 新北市 JSON API ===
        {"code": "newtaipei-banqiao", "name": "新北聯合醫院(板橋)",
         "url": "https://data.ntpc.gov.tw/api/datasets/00f8fa51-cedc-4c1d-88b0-58c55f740b79/json",
         "adapter_name": "NewTaipeiUnitedAdapter", "scrape_interval": 300},
        {"code": "newtaipei-sanchong", "name": "新北聯合醫院(三重)",
         "url": "https://data.ntpc.gov.tw/api/datasets/0abdf2d0-3246-4614-b715-d4ed6631eb16/json",
         "adapter_name": "NewTaipeiUnitedAdapter", "scrape_interval": 300},
        # === 外縣市 ===
        {"code": "changgung-linkou", "name": "林口長庚",
         "url": "https://register.cgmh.org.tw/Progress/3",
         "adapter_name": "ChangGungAdapter", "scrape_interval": 60},
        {"code": "changgung-kaohsiung", "name": "高雄長庚",
         "url": "https://register.cgmh.org.tw/Progress/8",
         "adapter_name": "ChangGungAdapter", "scrape_interval": 60},
        {"code": "kaohsiung-united", "name": "高雄聯合醫院",
         "url": "https://api.kcg.gov.tw/api/service/Get/8cd9aba3-bbbc-4801-b267-5e9ee9ff50a6",
         "adapter_name": "KaohsiungUnitedAdapter", "scrape_interval": 60},
    ]

    async with async_session() as session:
        for seed in seeds:
            result = await session.execute(
                select(Hospital).where(Hospital.code == seed["code"])
            )
            if not result.scalar_one_or_none():
                session.add(Hospital(
                    code=seed["code"],
                    name=seed["name"],
                    url=seed["url"],
                    adapter_name=seed["adapter_name"],
                    is_active=True,
                    scrape_interval=seed["scrape_interval"],
                ))
                logger.info(f"已新增醫院: {seed['name']}")
        await session.commit()


async def _seed_hospital_aliases():
    """初始化醫院別名資料 — 讓使用者可以用簡稱/俗稱查詢醫院"""
    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.hospital_alias import HospitalAlias

    # hospital_code → [別名列表]
    # 規則：正式名稱本身不需要加（已在 hospitals.name），這裡只放簡稱/俗稱/常見寫法
    alias_map = {
        # --- 萬芳醫院 ---
        "wanfang": ["萬芳", "wanfang"],
        # --- 台大醫院 ---
        "ntuh": ["台大", "臺大", "臺大醫院", "台大總院", "ntuh"],
        # --- 台大兒童醫院 ---
        "ntuh-children": ["台大兒童", "臺大兒童", "台大兒醫"],
        # --- 台北榮總 ---
        "tpvgh": ["北榮", "台北榮總", "臺北榮總", "榮總", "tpvgh"],
        # --- 台北長庚 ---
        "changgung-taipei": ["台北長庚", "北長庚"],
        # --- 林口長庚 ---
        "changgung-linkou": ["林口長庚", "林口"],
        # --- 高雄長庚 ---
        "changgung-kaohsiung": ["高雄長庚", "高長庚"],
        # --- 馬偕醫院（台北）---
        "mackay-taipei": ["馬偕", "台北馬偕", "馬偕台北", "臺北馬偕"],
        # --- 馬偕醫院（淡水）---
        "mackay-tamsui": ["淡水馬偕", "馬偕淡水"],
        # --- 國泰醫院 ---
        "cathay": ["國泰", "cathay"],
        # --- 新光醫院 ---
        "shinkong": ["新光", "shinkong"],
        # --- 三軍總醫院 ---
        "tsgh": ["三總", "三軍", "三軍總", "tsgh"],
        # --- 新北聯合醫院（板橋）---
        "newtaipei-banqiao": ["板橋聯醫", "板橋", "新北板橋", "聯醫板橋"],
        # --- 新北聯合醫院（三重）---
        "newtaipei-sanchong": ["三重聯醫", "三重", "新北三重", "聯醫三重"],
        # --- 高雄聯合醫院 ---
        "kaohsiung-united": ["高雄聯醫", "高聯醫"],
    }

    async with async_session() as session:
        for hospital_code, aliases in alias_map.items():
            for alias in aliases:
                result = await session.execute(
                    select(HospitalAlias).where(HospitalAlias.alias == alias)
                )
                existing = result.scalar_one_or_none()
                if not existing:
                    session.add(HospitalAlias(
                        hospital_code=hospital_code,
                        alias=alias,
                    ))
                    logger.debug(f"已新增別名: {alias} → {hospital_code}")
                elif existing.hospital_code != hospital_code:
                    # 別名指向的醫院變了，更新它
                    existing.hospital_code = hospital_code
                    logger.info(f"已更新別名: {alias} → {hospital_code}")
        await session.commit()
    logger.info("✅ 醫院別名初始化完成")


app = FastAPI(
    title="叮咚到號 — 醫院看診進度通知",
    description="即時抓取醫院看診進度，透過 LINE 推播通知",
    version="0.1.0",
    lifespan=lifespan,
)

# 註冊路由
app.include_router(webhook_router)


@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/hospitals")
async def list_hospitals():
    """列出所有已註冊醫院及其 Adapter 狀態"""
    from app.scrapers.registry import AdapterRegistry
    adapters = AdapterRegistry.get_all()
    return {
        "count": len(adapters),
        "hospitals": [
            {
                "code": code,
                "name": adapter.hospital_name,
                "type": "api" if "api" in adapter.base_url or "data." in adapter.base_url else "scraper",
                "url": adapter.base_url,
            }
            for code, adapter in adapters.items()
        ],
    }


@app.get("/api/progress/{hospital_code}")
async def get_live_progress(hospital_code: str):
    """即時查詢某醫院看診進度（直接呼叫 Adapter，不經快取）"""
    from app.scrapers.registry import AdapterRegistry
    adapter = AdapterRegistry.get(hospital_code)
    if not adapter:
        return {"error": f"找不到醫院: {hospital_code}", "available": AdapterRegistry.get_all_codes()}

    progress_list = await adapter.fetch_all_progress()
    return {
        "hospital": adapter.hospital_name,
        "code": hospital_code,
        "count": len(progress_list),
        "data": [p.to_dict() for p in progress_list],
    }


@app.post("/api/admin/sync-master-data")
async def trigger_sync_master_data():
    """手動觸發診科/醫生主檔同步（從各醫院爬蟲抓取後寫入 MySQL）"""
    from app.tasks.sync_master_data import sync_master_data
    task = sync_master_data.delay()
    return {"task_id": task.id, "status": "queued"}


@app.get("/api/departments/{hospital_code}")
async def list_departments(hospital_code: str):
    """查詢某醫院的所有診科"""
    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.department import Department

    async with async_session() as session:
        result = await session.execute(
            select(Department)
            .where(Department.hospital_code == hospital_code)
            .order_by(Department.name)
        )
        departments = result.scalars().all()
        return {
            "hospital_code": hospital_code,
            "count": len(departments),
            "departments": [d.name for d in departments],
        }


@app.get("/api/doctors/{hospital_code}")
async def list_doctors(hospital_code: str, department: str | None = None):
    """查詢某醫院的所有醫生（可依科別篩選）"""
    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.doctor import Doctor

    async with async_session() as session:
        query = select(Doctor).where(Doctor.hospital_code == hospital_code)
        if department:
            query = query.where(Doctor.department == department)
        query = query.order_by(Doctor.department, Doctor.name)

        result = await session.execute(query)
        doctors = result.scalars().all()
        return {
            "hospital_code": hospital_code,
            "count": len(doctors),
            "doctors": [
                {
                    "department": d.department,
                    "name": d.name,
                    "clinic_room": d.clinic_room,
                }
                for d in doctors
            ],
        }


@app.post("/api/admin/sync-nhi")
async def trigger_nhi_sync(types: list[str] | None = None):
    """手動觸發 NHI 資料同步（管理用）"""
    from app.tasks.nhi_sync import sync_nhi_institutions
    task = sync_nhi_institutions.delay(types)
    return {"task_id": task.id, "status": "queued"}


@app.get("/api/admin/nhi-stats")
async def nhi_stats():
    """查看 NHI 資料同步統計"""
    from app.services.nhi_sync import NhiQueryService
    query = NhiQueryService()
    stats = await query.get_stats()
    return {"stats": stats}


@app.get("/api/search/hospital")
async def search_hospital(q: str, limit: int = 10):
    """搜尋醫院"""
    from app.services.nhi_sync import NhiQueryService
    query = NhiQueryService()
    results = await query.search_hospitals(q, limit)
    return {
        "results": [
            {
                "hosp_id": r.hosp_id,
                "name": r.hosp_name,
                "type": r.hosp_type,
                "address": r.address,
                "tel": r.tel,
                "departments": r.departments,
            }
            for r in results
        ]
    }


@app.get("/api/search/hospitals-by-area")
async def search_hospitals_by_area(area: str, limit: int = 50):
    """依地區搜尋醫院（醫學中心＋區域醫院）"""
    from app.services.nhi_sync import NhiQueryService
    query = NhiQueryService()
    results = await query.search_hospitals_by_area(area, limit=limit)
    return {
        "count": len(results),
        "results": [
            {
                "hosp_id": r.hosp_id,
                "name": r.hosp_name,
                "type": r.hosp_type,
                "address": r.address,
                "tel": r.tel,
                "departments": (r.departments or "")[:100],
            }
            for r in results
        ],
    }


@app.get("/api/search/pharmacy")
async def search_pharmacy(area: str, limit: int = 5):
    """搜尋附近藥局"""
    from app.services.nhi_sync import NhiQueryService
    query = NhiQueryService()
    results = await query.search_pharmacies_near(area, limit)
    return {
        "results": [
            {
                "hosp_id": r.hosp_id,
                "name": r.hosp_name,
                "address": r.address,
                "tel": r.tel,
                "schedule": r.schedule,
            }
            for r in results
        ]
    }
