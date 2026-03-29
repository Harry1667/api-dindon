"""醫院別名解析器 — 根據使用者輸入的文字找到對應的醫院

別名可重複：例如「三總」同時對應三軍總醫院和三總松山分院時，
resolve() 回傳第一個匹配，resolve_all() 回傳所有匹配。

使用方式：
    resolver = HospitalResolver()
    await resolver.load()

    # 單一結果
    result = resolver.resolve("萬芳 精神科")
    # → ResolveResult(code="wanfang", name="萬芳醫院", extra="精神科")

    # 多重結果（別名重複時）
    results = resolver.resolve_all("三總")
    # → [ResolveResult(code="tsgh", ...), ResolveResult(code="tsgh-songshan", ...)]
"""

import logging
from dataclasses import dataclass
from sqlalchemy import select

logger = logging.getLogger(__name__)


@dataclass
class ResolveResult:
    code: str           # hospital_code
    name: str           # 醫院簡稱 (short_name)
    matched_by: str     # "name" | "alias"
    matched_text: str   # 實際匹配到的文字
    extra: str = ""     # 剩餘文字（科別/醫師等）


class HospitalResolver:
    """快取在記憶體的醫院別名對照表，啟動時載入一次"""

    def __init__(self):
        # alias_text → [(hospital_code, hospital_short_name), ...]
        self._alias_map: dict[str, list[tuple[str, str]]] = {}
        # hospital_code → hospital_short_name
        self._code_to_name: dict[str, str] = {}
        self._loaded = False

    async def load(self):
        """從資料庫載入所有醫院 + 別名，建立查詢表"""
        from app.models.database import async_session
        from app.models.hospital import Hospital
        from app.models.hospital_alias import HospitalAlias

        self._alias_map.clear()
        self._code_to_name.clear()

        async with async_session() as session:
            # 載入所有啟用的醫院
            result = await session.execute(select(Hospital).where(Hospital.is_active == True))
            hospitals = result.scalars().all()
            for h in hospitals:
                self._code_to_name[h.code] = h.short_name
                # 簡稱也可匹配
                self._alias_map.setdefault(h.short_name, []).append((h.code, h.short_name))

            # 載入所有別名（允許重複 alias 指向不同醫院）
            result = await session.execute(select(HospitalAlias))
            aliases = result.scalars().all()
            for a in aliases:
                short = self._code_to_name.get(a.hospital_code)
                if short is None:
                    continue  # 該醫院未啟用，跳過
                self._alias_map.setdefault(a.alias, []).append((a.hospital_code, short))

        # 去重（同一個 alias 不會有兩筆指向同一個 code）
        for key in self._alias_map:
            self._alias_map[key] = list(dict.fromkeys(self._alias_map[key]))

        self._loaded = True
        total_entries = sum(len(v) for v in self._alias_map.values())
        logger.info(
            f"HospitalResolver 載入完成: "
            f"{len(self._code_to_name)} 間醫院, {len(self._alias_map)} 個別名, "
            f"{total_entries} 筆對應"
        )

    def resolve(self, user_input: str) -> ResolveResult | None:
        """找到第一個匹配的醫院（向後相容）"""
        results = self.resolve_all(user_input)
        return results[0] if results else None

    def resolve_all(self, user_input: str) -> list[ResolveResult]:
        """找出所有匹配的醫院（別名重複時回傳多個）"""
        if not self._loaded:
            logger.warning("HospitalResolver 尚未載入，請先呼叫 load()")
            return []

        text = user_input.strip()
        if not text:
            return []

        # 1. 完整匹配
        if text in self._alias_map:
            entries = self._alias_map[text]
            return [
                ResolveResult(
                    code=code, name=name,
                    matched_by="alias",
                    matched_text=text,
                )
                for code, name in entries
            ]

        # 2. 子字串匹配 — 按別名長度降序，優先匹配較長的
        sorted_aliases = sorted(self._alias_map.keys(), key=len, reverse=True)
        for alias in sorted_aliases:
            if alias in text:
                entries = self._alias_map[alias]
                extra = text.replace(alias, "", 1).strip()
                return [
                    ResolveResult(
                        code=code, name=name,
                        matched_by="alias",
                        matched_text=alias,
                        extra=extra,
                    )
                    for code, name in entries
                ]

        return []

    def get_name(self, hospital_code: str) -> str:
        return self._code_to_name.get(hospital_code, hospital_code)

    def list_aliases(self, hospital_code: str) -> list[str]:
        return [
            alias for alias, entries in self._alias_map.items()
            if any(code == hospital_code for code, _ in entries)
        ]


# 全域單例
hospital_resolver = HospitalResolver()
