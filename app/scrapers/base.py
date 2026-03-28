"""爬蟲 Adapter 基底類別"""

from abc import ABC, abstractmethod
from app.schemas.clinic import ClinicProgressData


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
