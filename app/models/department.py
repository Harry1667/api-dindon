"""診科資料模型 — 從各醫院爬蟲中提取的科別主檔"""

from datetime import datetime
from sqlalchemy import String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Department(Base):
    """醫院診科主檔（由爬蟲同步任務自動維護）"""
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hospital_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="醫院代碼")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="科別名稱，如 精神科")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("hospital_code", "name", name="uq_dept_hospital_name"),
    )

    def __repr__(self):
        return f"<Department {self.hospital_code} {self.name}>"
