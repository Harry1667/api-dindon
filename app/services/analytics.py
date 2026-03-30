"""使用分析服務 — 記錄關鍵操作事件"""

import json
import logging

from app.models.database import async_session
from app.models.analytics import AnalyticsEvent

logger = logging.getLogger(__name__)


async def track_event(event_type: str, user_id: str = None, hospital_code: str = None, metadata: dict = None):
    """記錄分析事件

    event_type: follow, query, track_start, track_end, notify, feedback
    """
    try:
        async with async_session() as session:
            event = AnalyticsEvent(
                event_type=event_type,
                user_id=user_id,
                hospital_code=hospital_code,
                metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
            )
            session.add(event)
            await session.commit()
    except Exception as e:
        # 分析記錄失敗不應影響主流程
        logger.error(f"[analytics] 記錄事件失敗 {event_type}: {e}")
