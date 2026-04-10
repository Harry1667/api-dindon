"""LIFF 用戶資料模型 — 從 LIFF 頁面取得的 LINE 用戶"""

from datetime import datetime
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class LiffUser(Base):
    __tablename__ = "liff_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    line_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="LINE user ID")
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="LINE 顯示名稱")
    picture_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="LINE 頭貼 URL")
    status_message: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="LINE 狀態訊息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
