"""爬蟲 Adapter 基底類別"""

from abc import ABC, abstractmethod
from app.schemas.clinic import ClinicProgressData
from app.config import settings


class BaseHospitalAdapter(ABC):
    """所有醫院爬蟲的基底類別，新增醫院只需繼承此類並實作方法"""

    hospital_code: str = ""
    hospital_name: str = ""
    base_url: str = ""

    @abstractmethod
    async def fetch_all_progress(self) -> list[ClinicProgressData]:
        """抓取該醫院所有目前看診中的診間進度"""
        ...

    @abstractmethod
    async def get_departments(self) -> list[str]:
        """取得該醫院所有科別名稱"""
        ...


def proxy_state_tag() -> str:
    """供 socks5-required 爬蟲在 log 訊息中標明目前 proxy 狀態，方便 production diagnose。
    回傳如 `proxy=on(socks5://...:1080)` 或 `proxy=OFF`。"""
    p = settings.socks5_proxy
    if not p:
        return "proxy=OFF"
    # 隱藏帳密但保留 host:port
    safe = p.split("@")[-1] if "@" in p else p
    return f"proxy=on({safe})"
