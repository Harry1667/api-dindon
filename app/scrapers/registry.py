"""爬蟲 Adapter 註冊中心 — 管理所有醫院的爬蟲模組"""

from app.scrapers.base import BaseHospitalAdapter

# --- Imports ---
from app.scrapers.wanfang import WanfangAdapter
from app.scrapers.newtaipei_united import banqiao_adapter, sanchong_adapter
from app.scrapers.kaohsiung_united import KaohsiungUnitedAdapter
from app.scrapers.changgung import taipei_changgung, linkou_changgung, kaohsiung_changgung
from app.scrapers.ntuh import ntuh_main, ntuh_children
from app.scrapers.mackay import mackay_taipei, mackay_tamsui
from app.scrapers.tpvgh import TpvghAdapter
from app.scrapers.cathay import CathayAdapter
from app.scrapers.shinkong import ShinkongAdapter
from app.scrapers.tsgh import TsghAdapter
from app.scrapers.chgh import ChghAdapter
from app.scrapers.tzuchi import tzuchi_taipei, tzuchi_xindian
from app.scrapers.femh import FemhAdapter
from app.scrapers.tph import TphAdapter


class AdapterRegistry:
    """Adapter 註冊中心，新增醫院只需在這裡註冊"""

    _adapters: dict[str, BaseHospitalAdapter] = {}

    @classmethod
    def register(cls, adapter: BaseHospitalAdapter):
        cls._adapters[adapter.hospital_code] = adapter

    @classmethod
    def get(cls, hospital_code: str) -> BaseHospitalAdapter | None:
        return cls._adapters.get(hospital_code)

    @classmethod
    def get_all(cls) -> dict[str, BaseHospitalAdapter]:
        return cls._adapters

    @classmethod
    def get_all_codes(cls) -> list[str]:
        return list(cls._adapters.keys())


# ============================================================
# 註冊所有 Adapter
# ============================================================

# --- 台北市 醫學中心 ---
AdapterRegistry.register(WanfangAdapter())            # 萬芳醫院（HTML 爬蟲）
AdapterRegistry.register(ntuh_main)                    # 台大醫院（POST AJAX）
AdapterRegistry.register(ntuh_children)                # 台大兒童醫院
AdapterRegistry.register(TpvghAdapter())               # 台北榮總（GET + 科別連結）
AdapterRegistry.register(taipei_changgung)             # 台北長庚（POST form）
AdapterRegistry.register(mackay_taipei)                # 馬偕醫院 台北（GET params）
AdapterRegistry.register(CathayAdapter())              # 國泰醫院
AdapterRegistry.register(ShinkongAdapter())            # 新光醫院
AdapterRegistry.register(TsghAdapter())                # 三軍總醫院
AdapterRegistry.register(ChghAdapter())                # 振興醫院
AdapterRegistry.register(tzuchi_taipei)                # 台北慈濟醫院
AdapterRegistry.register(tzuchi_xindian)               # 台北慈濟醫院(新店)
AdapterRegistry.register(FemhAdapter())                # 亞東紀念醫院
AdapterRegistry.register(TphAdapter())                 # 衛福部臺北醫院

# --- 台北市 區域醫院 ---
AdapterRegistry.register(mackay_tamsui)                # 馬偕醫院 淡水

# --- 新北市 — 政府開放資料 JSON API ---
AdapterRegistry.register(banqiao_adapter)              # 新北聯合醫院 板橋
AdapterRegistry.register(sanchong_adapter)             # 新北聯合醫院 三重

# --- 外縣市 ---
AdapterRegistry.register(linkou_changgung)             # 林口長庚
AdapterRegistry.register(kaohsiung_changgung)          # 高雄長庚
AdapterRegistry.register(KaohsiungUnitedAdapter())     # 高雄聯合醫院（JSON API）
