"""醫院資料模型 — 以衛福部評鑑合格醫院名單為基準"""

from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="系統代碼，如 ntuh")
    nhi_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, comment="健保署醫事機構代碼（10碼），待取得後填入")
    gov_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="衛福部評鑑名單流水號（縣市內編號）")
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="衛福部官方全名")
    short_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="常用簡稱，如 台大醫院")
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="醫學中心", comment="醫院層級：醫學中心/區域醫院/地區醫院")
    city: Mapped[str] = mapped_column(String(10), nullable=False, default="", comment="縣市，如 臺北市")
    district: Mapped[str] = mapped_column(String(10), nullable=False, default="", comment="區/鄉/鎮，如 中正區")
    address: Mapped[str | None] = mapped_column(Text, nullable=True, comment="完整地址")
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="醫院電話")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="醫院簡介")
    website: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="醫院官網")
    url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="看診進度查詢網址")
    adapter_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="爬蟲 Adapter 名稱，空=尚未接入")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否啟用爬蟲")
    scrape_interval: Mapped[int] = mapped_column(default=60, comment="爬蟲間隔（秒）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
