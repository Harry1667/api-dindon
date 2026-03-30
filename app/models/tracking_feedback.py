"""追蹤結果回饋資料模型"""

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class TrackingFeedback(Base):
    __tablename__ = "tracking_feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 追蹤任務資訊
    task_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="追蹤任務 ID")
    line_user_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="LINE user ID")
    hospital_code: Mapped[str] = mapped_column(String(50), nullable=False)
    hospital_name: Mapped[str] = mapped_column(String(100), nullable=False, default="", comment="醫院名稱")
    department: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    doctor_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    clinic_room: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    session: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="上午診/下午診/夜診")
    user_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="用戶掛號號碼")
    notify_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="light")

    # 追蹤過程
    track_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="追蹤建立時間")
    start_current: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="建立追蹤時的看診號碼")
    final_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="結束時的看診號碼")
    notify_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="總共通知次數")
    final_message: Mapped[str] = mapped_column(Text, nullable=False, comment="最後通知內容")
    end_reason: Mapped[str] = mapped_column(String(50), nullable=False, default="arrived", comment="結束原因: arrived/passed/doctor_gone/timeout/cancelled")

    # 對話記錄
    conversation_log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON: [{time,role,message},...]")

    # 用戶回饋
    is_correct: Mapped[bool | None] = mapped_column(nullable=True, comment="True=正確 False=錯誤 None=未回饋")
    user_comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用戶補充說明")

    # 時間
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="回饋建立時間")
