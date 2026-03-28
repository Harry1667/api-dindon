from app.scrapers.base import BaseHospitalAdapter
from app.scrapers.wanfang import WanfangAdapter
from app.scrapers.registry import AdapterRegistry

__all__ = ["BaseHospitalAdapter", "WanfangAdapter", "AdapterRegistry"]
