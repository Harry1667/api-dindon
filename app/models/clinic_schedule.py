"""診間開關診時間表 — 從 ClinicProgress 歷史資料統計而來

每個 (hospital_code, department, clinic_room, weekday) 的開診/關診時間，
用來未來取代 ClinicProgress 作為「現在是否在看診」的判斷依據。
"""

from datetime import datetime, time
from sqlalchemy import String, Integer, Time, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class ClinicSchedule(Base):
    __tablename__ = "clinic_schedule"
    __table_args__ = (
        UniqueConstraint("hospital_code", "department", "clinic_room", "weekday",
                         name="uq_clinic_schedule"),
        Index("ix_cs_hospital_weekday", "hospital_code", "weekday"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hospital_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="醫院代碼")
    department: Mapped[str] = mapped_column(String(100), nullable=False, comment="科別")
    clinic_room: Mapped[str] = mapped_column(String(255), nullable=False, comment="診間號碼")
    weekday: Mapped[int] = mapped_column(Integer, nullable=False, comment="星期幾 0=週一 6=週日")
    open_time: Mapped[time] = mapped_column(Time, nullable=False, comment="開診時間（台灣時間）")
    close_time: Mapped[time] = mapped_column(Time, nullable=False, comment="關診時間（台灣時間）")
    sample_count: Mapped[int] = mapped_column(Integer, default=0, comment="統計樣本數")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                  onupdate=datetime.utcnow, comment="最後更新時間")
