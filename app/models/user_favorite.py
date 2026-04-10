"""用戶常用醫院 + 常用科別"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class UserFavorite(Base):
    __tablename__ = "user_favorites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    line_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="LINE user ID")
    hospital_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="醫院代碼")
    hospital_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="醫院名稱")
    department: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="科別（null=醫院層級）")
    use_count: Mapped[int] = mapped_column(Integer, default=1, comment="使用次數")
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
