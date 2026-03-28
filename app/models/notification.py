"""推播通知紀錄"""

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tracking_task_id: Mapped[int] = mapped_column(ForeignKey("tracking_tasks.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, comment="推播訊息內容")
    status: Mapped[str] = mapped_column(String(20), default="sent", comment="sent/failed")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
