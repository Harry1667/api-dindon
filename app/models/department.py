"""診科資料模型 — 從各醫院爬蟲中提取的科別主檔 + 疾病/症狀對照"""

from datetime import datetime
from sqlalchemy import String, Text, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Department(Base):
    """醫院診科主檔（由爬蟲同步任務自動維護）"""
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hospital_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="醫院代碼")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="科別名稱，如 精神科")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="大分類：內科系/外科系/婦兒科/其他專科/中醫/牙科")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="科別說明")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("hospital_code", "name", name="uq_dept_hospital_name"),
    )


class DepartmentGuide(Base):
    """科別就醫指南 — 什麼病看什麼科（醫院無關的通用參考資料）"""
    __tablename__ = "department_guide"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    department: Mapped[str] = mapped_column(String(100), nullable=False, comment="標準科別名稱，如 骨科")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="大分類：內科系/外科系/婦兒科/其他專科")
    disease: Mapped[str] = mapped_column(String(200), nullable=False, comment="疾病名稱，如 骨折")
    symptoms: Mapped[str] = mapped_column(String(500), nullable=False, default="", comment="常見症狀，如 疼痛、腫脹")
    keywords: Mapped[str] = mapped_column(String(500), nullable=False, default="", comment="搜尋關鍵字，如 骨頭痛,手斷,腳斷")

    __table_args__ = (
        UniqueConstraint("department", "disease", name="uq_guide_dept_disease"),
        Index("ix_guide_dept", "department"),
        Index("ix_guide_disease", "disease"),
    )
