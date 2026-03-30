"""種子資料載入服務 — 從 JSON 檔載入醫院和別名資料"""

import json
import logging
from pathlib import Path

from sqlalchemy import select

from app.models.database import async_session
from app.models.hospital import Hospital
from app.models.hospital_alias import HospitalAlias

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"


async def seed_hospitals():
    """從 data/seed_hospitals.json 初始化醫院資料"""
    json_path = DATA_DIR / "seed_hospitals.json"
    if not json_path.exists():
        logger.warning(f"[seeder] 找不到種子資料: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        seeds = json.load(f)

    from app.config import settings

    async with async_session() as session:
        for h in seeds:
            result = await session.execute(
                select(Hospital).where(Hospital.code == h["code"])
            )
            if result.scalar_one_or_none():
                continue

            # 萬芳醫院由 feature flag 控制
            is_active = h.get("is_active", False)
            if h["code"] == "wanfang":
                is_active = settings.enable_wanfang_scraper

            session.add(Hospital(
                code=h["code"],
                name=h["name"],
                short_name=h.get("short_name", ""),
                level=h.get("level", ""),
                city=h.get("city", ""),
                district=h.get("district", ""),
                phone=h.get("phone", ""),
                url=h.get("url"),
                adapter_name=h.get("adapter_name"),
                is_active=is_active,
                scrape_interval=h.get("scrape_interval", 60),
            ))

        await session.commit()
    logger.info(f"✅ 醫院資料初始化完成（{len(seeds)} 筆）")


async def seed_hospital_aliases():
    """從 data/seed_aliases.json 初始化醫院別名資料"""
    json_path = DATA_DIR / "seed_aliases.json"
    if not json_path.exists():
        logger.warning(f"[seeder] 找不到別名資料: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        alias_map = json.load(f)

    async with async_session() as session:
        for hospital_code, aliases in alias_map.items():
            for alias in aliases:
                result = await session.execute(
                    select(HospitalAlias).where(
                        HospitalAlias.hospital_code == hospital_code,
                        HospitalAlias.alias == alias,
                    )
                )
                if not result.scalar_one_or_none():
                    session.add(HospitalAlias(
                        hospital_code=hospital_code,
                        alias=alias,
                    ))

        await session.commit()

    total = sum(len(v) for v in alias_map.values())
    logger.info(f"✅ 醫院別名初始化完成（{len(alias_map)} 家醫院，{total} 個別名）")
