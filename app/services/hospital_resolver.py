"""醫院別名解析器 — 根據使用者輸入的文字找到對應的醫院

使用方式：
    from app.services.hospital_resolver import HospitalResolver

    resolver = HospitalResolver()
    await resolver.load()           # 啟動時載入一次

    result = resolver.resolve("三總")
    # → {"code": "tsgh", "name": "三軍總醫院", "matched_by": "alias", "matched_text": "三總"}

    result = resolver.resolve("台大 內科")
    # → {"code": "ntuh", "name": "台大醫院", "matched_by": "alias", "matched_text": "台大", "extra": "內科"}
"""

import logging
from dataclasses import dataclass
from sqlalchemy import select

logger = logging.getLogger(__name__)


@dataclass
class ResolveResult:
    code: str           # hospital_code
    name: str           # 醫院正式名稱
    matched_by: str     # "name" | "alias"
    matched_text: str   # 實際匹配到的文字
    extra: str = ""     # 剩餘文字（科別/醫師等）


class HospitalResolver:
    """快取在記憶體的醫院別名對照表，啟動時載入一次"""

    def __init__(self):
        # alias_text → (hospital_code, hospital_name)
        self._alias_map: dict[str, tuple[str, str]] = {}
        # hospital_code → hospital_name
        self._code_to_name: dict[str, str] = {}
        self._loaded = False

    async def load(self):
        """從資料庫載入所有醫院 + 別名，建立查詢表"""
        from app.models.database import async_session
        from app.models.hospital import Hospital
        from app.models.hospital_alias import HospitalAlias

        async with async_session() as session:
            # 載入所有醫院
            result = await session.execute(select(Hospital).where(Hospital.is_active == True))
            hospitals = result.scalars().all()
            for h in hospitals:
                self._code_to_name[h.code] = h.name
                # 正式名稱也可以匹配
                self._alias_map[h.name] = (h.code, h.name)

            # 載入所有別名
            result = await session.execute(select(HospitalAlias))
            aliases = result.scalars().all()
            for a in aliases:
                hosp_name = self._code_to_name.get(a.hospital_code, a.hospital_code)
                self._alias_map[a.alias] = (a.hospital_code, hosp_name)

        self._loaded = True
        logger.info(
            f"✅ HospitalResolver 載入完成: "
            f"{len(self._code_to_name)} 間醫院, {len(self._alias_map)} 個別名/名稱"
        )

    def resolve(self, user_input: str) -> ResolveResult | None:
        """
        從使用者輸入中找出醫院。

        嘗試策略（由長到短匹配，避免「台大」吃掉「台大兒童」）：
        1. 完整匹配整段文字
        2. 從最長的別名開始，檢查是否出現在文字中
        """
        if not self._loaded:
            logger.warning("HospitalResolver 尚未載入，請先呼叫 load()")
            return None

        text = user_input.strip()
        if not text:
            return None

        # 完整匹配
        if text in self._alias_map:
            code, name = self._alias_map[text]
            return ResolveResult(
                code=code, name=name,
                matched_by="alias" if text != name else "name",
                matched_text=text,
            )

        # 子字串匹配 — 按別名長度降序，優先匹配較長的別名
        sorted_aliases = sorted(self._alias_map.keys(), key=len, reverse=True)
        for alias in sorted_aliases:
            if alias in text:
                code, name = self._alias_map[alias]
                extra = text.replace(alias, "", 1).strip()
                return ResolveResult(
                    code=code, name=name,
                    matched_by="alias" if alias != name else "name",
                    matched_text=alias,
                    extra=extra,
                )

        return None

    def get_name(self, hospital_code: str) -> str:
        """根據 code 取得醫院名稱"""
        return self._code_to_name.get(hospital_code, hospital_code)

    def list_aliases(self, hospital_code: str) -> list[str]:
        """列出某醫院的所有別名"""
        return [
            alias for alias, (code, _) in self._alias_map.items()
            if code == hospital_code
        ]


# 全域單例
hospital_resolver = HospitalResolver()
