"""醫生資料模型 — 從各醫院爬蟲中提取的醫師主檔 + 醫師簡歷"""

from datetime import datetime
from sqlalchemy import String, Text, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Doctor(Base):
    """醫院醫師主檔（由爬蟲同步任務自動維護）"""
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hospital_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="醫院代碼")
    department: Mapped[str] = mapped_column(String(100), nullable=False, comment="科別名稱")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="醫師姓名")
    clinic_room: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="最近看診的診間號碼")
    title: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="職稱，如 主任醫師、主治醫師")
    specialty: Mapped[str | None] = mapped_column(Text, nullable=True, comment="專長描述")
    education: Mapped[str | None] = mapped_column(Text, nullable=True, comment="學歷")
    experience: Mapped[str | None] = mapped_column(Text, nullable=True, comment="經歷")
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="醫師照片 URL")
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="醫師個人頁面 URL")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("hospital_code", "department", "name", name="uq_doc_hospital_dept_name"),
        Index("ix_doc_hospital", "hospital_code"),
        Index("ix_doc_name", "name"),
    )
