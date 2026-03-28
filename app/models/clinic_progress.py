"""看診進度快照資料模型"""

from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class ClinicProgress(Base):
    __tablename__ = "clinic_progress"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hospital_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="醫院代碼")
    date: Mapped[str] = mapped_column(String(20), nullable=False, comment="看診日期 如 2026/03/28")
    session: Mapped[str] = mapped_column(String(20), nullable=False, comment="診別 如 上午診/午診/夜診")
    department: Mapped[str] = mapped_column(String(100), nullable=False, comment="科別")
    doctor_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="醫師姓名")
    clinic_room: Mapped[str] = mapped_column(String(20), nullable=False, comment="診間號碼 如 282診")
    current_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="目前號碼")
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="下一號碼")
    is_current_skipped: Mapped[bool] = mapped_column(Boolean, default=False, comment="目前號碼是否過號")
    is_next_skipped: Mapped[bool] = mapped_column(Boolean, default=False, comment="下一號碼是否過號")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="抓取時間")
