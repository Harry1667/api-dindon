"""使用者查詢歷史 — 記錄醫院/科別/醫師的使用次數，用於個人化排序"""

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class UserQueryHistory(Base):
    __tablename__ = "user_query_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="使用者 ID（LINE user_id 或 demo session ID）",
    )
    hospital_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="醫院代碼",
    )
    department: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", comment="科別",
    )
    doctor_name: Mapped[str] = mapped_column(
        String(50), nullable=False, default="", comment="醫師姓名",
    )
    use_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="使用次數",
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
        comment="最後使用時間",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_user_hospital", "user_id", "hospital_code"),
        Index("ix_user_dept", "user_id", "hospital_code", "department"),
        Index("ix_user_doctor", "user_id", "hospital_code", "department", "doctor_name"),
    )
