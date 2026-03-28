"""醫院資料模型"""

from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="醫院代碼，如 wanfang")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="醫院名稱")
    url: Mapped[str] = mapped_column(Text, nullable=False, comment="看診進度查詢網址")
    adapter_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="爬蟲 Adapter 名稱")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否啟用")
    scrape_interval: Mapped[int] = mapped_column(default=60, comment="爬蟲間隔（秒）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
