"""系統負載指標資料模型"""

from datetime import datetime
from sqlalchemy import Integer, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class SystemMetrics(Base):
    __tablename__ = "system_metrics"
    __table_args__ = (
        Index("ix_sm_recorded_at", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="記錄時間（台灣時間）")
    redis_queue: Mapped[int] = mapped_column(Integer, default=0, comment="Redis queue 積壓數")
    db_writes: Mapped[int] = mapped_column(Integer, default=0, comment="過去 1 分鐘 DB 寫入筆數")
    active_hospitals: Mapped[int] = mapped_column(Integer, default=0, comment="有回傳資料的醫院數")
    scraper_errors: Mapped[int] = mapped_column(Integer, default=0, comment="爬蟲錯誤累計數")
    line_notifications: Mapped[int] = mapped_column(Integer, default=0, comment="LINE 通知發送數")
    slowdown_hospitals: Mapped[int] = mapped_column(Integer, default=0, comment="降速中醫院數")
    active_tasks: Mapped[int] = mapped_column(Integer, default=0, comment="Active 追蹤任務數")
    scrape_duration: Mapped[int] = mapped_column(Integer, default=0, comment="上輪爬蟲耗時（秒）")
    worker_mem_mb: Mapped[int] = mapped_column(Integer, default=0, comment="Worker 記憶體 MB")
