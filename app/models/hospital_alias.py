"""醫院別名資料模型 — 讓使用者可以用簡稱/俗稱查詢醫院
別名可重複：例如「三總」可同時對應三軍總醫院和三總松山分院
"""

from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class HospitalAlias(Base):
    __tablename__ = "hospital_aliases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hospital_code: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("hospitals.code"),
        nullable=False,
        comment="對應 hospitals.code",
    )
    alias: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="別名（可重複，重複時 LINE 列出多家）"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_alias", "alias"),
        Index("ix_hospital_alias_unique", "hospital_code", "alias", unique=True),
    )
