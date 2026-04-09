"""FastAPI 主程式入口"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from app.middleware.auth import verify_api_token, check_rate_limit
from dotenv import load_dotenv

load_dotenv()

from app.config import settings
from app.api.webhook import router as webhook_router
from app.api.admin import router as admin_router
from app.api.test_harness import router as test_router
from app.api.live_test import router as live_test_router
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
import app.models.department  # noqa: F401 (Department + DepartmentGuide)
import app.models.doctor  # noqa: F401
import app.models.tracking_feedback  # noqa: F401
import app.models.analytics  # noqa: F401

# 設定 logging（結構化 JSON 日誌）
try:
    from pythonjsonlogger import jsonlogger
    handler = logging.StreamHandler()
    handler.setFormatter(jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    ))
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.DEBUG if settings.app_debug else logging.INFO)
except ImportError:
    logging.basicConfig(
        level=logging.DEBUG if settings.app_debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    logger.info("🚀 醫院掛號排隊通知系統啟動中...")
    logger.info(
        f"📋 Feature Flags: env={settings.app_env}, "
        f"mock_hospital={settings.enable_mock_hospital}, "
        f"wanfang_scraper={settings.enable_wanfang_scraper}, "
        f"auto_create_tables={settings.enable_auto_create_tables}"
    )

    # 建立資料表（由 ENABLE_AUTO_CREATE_TABLES 控制，正式環境用 Alembic migration）
    if settings.enable_auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ 資料庫自動建表完成")
    else:
        logger.info("⏭️ 自動建表已停用，使用 Alembic migration")

    # 插入預設醫院資料（從 JSON 檔載入）
    from app.services.seeder import seed_hospitals, seed_hospital_aliases
    await seed_hospitals()
    await seed_hospital_aliases()

    # 載入別名解析器到記憶體
    from app.services.hospital_resolver import hospital_resolver
    await hospital_resolver.load()

    # 預熱 demo_chat 的 DB 連線（避免第一次查追蹤等 2 秒）
    try:
        from demo_chat import _warmup_db
        _warmup_db()
        logger.info("✅ demo_chat DB 連線預熱完成")
    except Exception as e:
        logger.warning(f"⚠️ DB 預熱失敗（不影響功能）: {e}")

    # 建立共用 CacheService（所有 API route 透過 request.app.state.cache 取用）
    from app.services.cache import CacheService
    app.state.cache = CacheService()
    logger.info("✅ CacheService 共用實例已建立")

    yield

    # 關閉連線
    await app.state.cache.close()
    await engine.dispose()
    logger.info("👋 系統已關閉")



app = FastAPI(
    title="叮咚到號 — 醫院看診進度通知",
    description="即時抓取醫院看診進度，透過 LINE 推播通知",
    version="0.1.0",
    lifespan=lifespan,
)

# 全域例外處理 — 未捕獲的 500 錯誤轉統一 JSON 格式
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未捕獲的例外: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "伺服器內部錯誤"}},
    )

# 註冊路由
app.include_router(webhook_router)
app.include_router(admin_router)
app.include_router(test_router)
app.include_router(live_test_router)


@app.get("/health")
async def health_check(request: Request):
    """健康檢查 — 含 Redis 和 DB 連線狀態"""
    from app.models.database import async_session
    from sqlalchemy import text

    checks = {"redis": False, "database": False}

    # Redis 檢查（用共用 CacheService）
    try:
        checks["redis"] = await request.app.state.cache.is_healthy()
    except Exception:
        pass

    # DB 檢查
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
            checks["database"] = True
    except Exception:
        pass

    all_healthy = all(checks.values())
    return {
        "status": "ok" if all_healthy else "degraded",
        "version": "0.1.0",
        "checks": checks,
    }


@app.get("/api/hospitals", dependencies=[Depends(verify_api_token), Depends(check_rate_limit)])
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


@app.get("/api/progress/{hospital_code}", dependencies=[Depends(verify_api_token), Depends(check_rate_limit)])
async def get_progress(request: Request, hospital_code: str):
    """查詢某醫院看診進度（讀 Redis 快取，資料延遲 ≤ 60 秒）"""
    from app.scrapers.registry import AdapterRegistry
    adapter = AdapterRegistry.get(hospital_code)
    if not adapter:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": f"找不到醫院: {hospital_code}"}, "available": AdapterRegistry.get_all_codes()},
        )

    cache = request.app.state.cache
    progress_list = await cache.get_all_progress(hospital_code)
    return {
        "hospital": adapter.hospital_name,
        "code": hospital_code,
        "count": len(progress_list),
        "data": [p.to_dict() for p in progress_list],
    }


@app.get("/api/admin/live-progress/{hospital_code}")
async def get_live_progress(hospital_code: str):
    """即時查詢某醫院看診進度（直接呼叫 Adapter，僅 admin 使用）"""
    from app.scrapers.registry import AdapterRegistry
    adapter = AdapterRegistry.get(hospital_code)
    if not adapter:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": f"找不到醫院: {hospital_code}"}, "available": AdapterRegistry.get_all_codes()},
        )

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


@app.get("/api/departments/{hospital_code}", dependencies=[Depends(verify_api_token), Depends(check_rate_limit)])
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


@app.get("/api/doctors/{hospital_code}", dependencies=[Depends(verify_api_token), Depends(check_rate_limit)])
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


@app.get("/api/search/hospital", dependencies=[Depends(verify_api_token), Depends(check_rate_limit)])
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


@app.get("/api/search/hospitals-by-area", dependencies=[Depends(verify_api_token), Depends(check_rate_limit)])
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


@app.get("/api/guide/which-department", dependencies=[Depends(verify_api_token), Depends(check_rate_limit)])
async def which_department(q: str, limit: int = 10):
    """查詢症狀/疾病對應的科別（供 LINE Bot 使用）"""
    from sqlalchemy import select, or_
    from app.models.database import async_session
    from app.models.department import DepartmentGuide

    keyword = q.strip()
    if not keyword:
        return {"results": []}

    async with async_session() as session:
        result = await session.execute(
            select(DepartmentGuide).where(
                or_(
                    DepartmentGuide.disease.contains(keyword),
                    DepartmentGuide.symptoms.contains(keyword),
                    DepartmentGuide.keywords.contains(keyword),
                    DepartmentGuide.department.contains(keyword),
                )
            ).limit(limit)
        )
        guides = result.scalars().all()

    return {
        "query": keyword,
        "count": len(guides),
        "results": [
            {
                "department": g.department,
                "category": g.category,
                "disease": g.disease,
                "symptoms": g.symptoms,
            }
            for g in guides
        ],
    }


@app.get("/api/search/pharmacy", dependencies=[Depends(verify_api_token), Depends(check_rate_limit)])
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


# === 靜態網頁（對話式查詢介面）===
import os
from fastapi.responses import FileResponse

@app.get("/chat")
async def chat_page():
    """對話式看診進度查詢頁面"""
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "頁面不存在"})
