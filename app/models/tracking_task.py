"""追蹤任務資料模型"""

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.models.database import Base


class TaskStatus(str, enum.Enum):
    ACTIVE = "active"          # 追蹤中
    NOTIFIED = "notified"      # 已通知
    COMPLETED = "completed"    # 已完成（用戶已看診）
    CANCELLED = "cancelled"    # 用戶取消


class TrackingTask(Base):
    __tablename__ = "tracking_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    hospital_code: Mapped[str] = mapped_column(String(50), nullable=False, comment="醫院代碼")
    department: Mapped[str] = mapped_column(String(100), nullable=False, comment="科別")
    doctor_name: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="醫師姓名")
    clinic_room: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="診間號碼")
    user_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="用戶掛號號碼")
    threshold: Mapped[int] = mapped_column(Integer, default=5, comment="提前幾號通知")
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus), default=TaskStatus.ACTIVE, comment="任務狀態"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="通知時間")
