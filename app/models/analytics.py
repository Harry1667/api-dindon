"""使用分析事件模型"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text
from app.models.database import Base


class AnalyticsEvent(Base):
    """使用分析事件表

    記錄關鍵操作：用戶加入、查詢、追蹤、到號通知
    用於漏斗分析：加入 → 查詢 → 追蹤 → 到號
    """
    __tablename__ = "analytics_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)  # follow, query, track_start, track_end, notify
    user_id = Column(String(100), nullable=True, index=True)
    hospital_code = Column(String(50), nullable=True)
    metadata_json = Column(Text, nullable=True)  # JSON 格式的額外資訊
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
