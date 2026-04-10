"""LIFF 用戶資料模型 — 從 LIFF 頁面取得的 LINE 用戶"""

from datetime import datetime
from sqlalchemy import String, DateTime, Text, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class LiffUser(Base):
    __tablename__ = "liff_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    line_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="LINE user ID")
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="LINE 顯示名稱")
    picture_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="LINE 頭貼 URL")
    status_message: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="LINE 狀態訊息")
    email: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="LINE 信箱（需 email scope）")

    # LIFF 環境資訊
    os: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="作業系統: ios/android/web")
    language: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="用戶語言: zh-TW/en/ja")
    is_in_client: Mapped[bool | None] = mapped_column(Boolean, nullable=True, comment="是否在 LINE App 內開啟")
    is_friend: Mapped[bool | None] = mapped_column(Boolean, nullable=True, comment="是否已加 Bot 好友")

    # LIFF context
    context_type: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="開啟情境: utou/room/group/external/none")
    context_view_type: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="LIFF 視窗: full/tall/compact")
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="群組 ID（從群組開啟時）")
    room_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="聊天室 ID（從聊天室開啟時）")

    # 裝置 / 瀏覽器資訊
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True, comment="瀏覽器 User-Agent")
    screen_width: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="螢幕寬度")
    screen_height: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="螢幕高度")

    # 統計
    visit_count: Mapped[int] = mapped_column(Integer, default=1, comment="造訪次數")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
