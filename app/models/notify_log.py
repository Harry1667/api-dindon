"""通知推播記錄 — 每次實際推播都寫一筆"""

from datetime import datetime
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.database import Base


class NotifyLog(Base):
    __tablename__ = "notify_log"
    __table_args__ = (
        Index("ix_nl_task_id", "task_id"),
        Index("ix_nl_created_at", "created_at"),
        Index("ix_nl_hospital_event", "hospital_code", "event_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 追蹤任務
    task_id: Mapped[int] = mapped_column(nullable=False, comment="tracking_tasks.id")
    source: Mapped[str] = mapped_column(nullable=False, default="line", comment="line / web / test")

    # 醫院資訊
    hospital_code: Mapped[str] = mapped_column(nullable=False)
    department: Mapped[str | None] = mapped_column(nullable=True)
    doctor_name: Mapped[str | None] = mapped_column(nullable=True)
    clinic_room: Mapped[str | None] = mapped_column(nullable=True)

    # 號碼資訊
    user_number: Mapped[int | None] = mapped_column(nullable=True, comment="用戶號碼")
    current_number: Mapped[int | None] = mapped_column(nullable=True, comment="當時看診號碼")
    remaining: Mapped[int | None] = mapped_column(nullable=True, comment="剩餘號數")

    # 事件類型
    event_type: Mapped[str] = mapped_column(
        nullable=False,
        comment="notify / arrived / passed / skipped / timeout / doctor_gone",
    )

    # 訊息預覽（前 200 字）
    message_preview: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        comment="UTC 時間",
    )
