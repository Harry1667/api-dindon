"""LIFF 用戶 API — 註冊/查詢 LIFF 用戶、推播訊息"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.models.database import async_session
from app.models.liff_user import LiffUser
from app.models.user_favorite import UserFavorite

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/liff", tags=["LIFF"])


class LiffRegisterRequest(BaseModel):
    line_user_id: str
    display_name: str | None = None
    picture_url: str | None = None
    status_message: str | None = None
    email: str | None = None
    os: str | None = None
    language: str | None = None
    is_in_client: bool | None = None
    is_friend: bool | None = None
    context_type: str | None = None
    context_view_type: str | None = None
    group_id: str | None = None
    room_id: str | None = None
    user_agent: str | None = None
    screen_width: int | None = None
    screen_height: int | None = None


class PushMessageRequest(BaseModel):
    line_user_id: str
    message: str


@router.post("/register")
async def register_liff_user(req: LiffRegisterRequest):
    """LIFF 頁面開啟時，註冊/更新用戶資訊"""
    async with async_session() as session:
        result = await session.execute(
            select(LiffUser).where(LiffUser.line_user_id == req.line_user_id)
        )
        user = result.scalar_one_or_none()

        fields = {
            "display_name": req.display_name,
            "picture_url": req.picture_url,
            "status_message": req.status_message,
            "email": req.email,
            "os": req.os,
            "language": req.language,
            "is_in_client": req.is_in_client,
            "is_friend": req.is_friend,
            "context_type": req.context_type,
            "context_view_type": req.context_view_type,
            "group_id": req.group_id,
            "room_id": req.room_id,
            "user_agent": req.user_agent,
            "screen_width": req.screen_width,
            "screen_height": req.screen_height,
        }

        if user:
            for k, v in fields.items():
                setattr(user, k, v)
            user.visit_count = (user.visit_count or 0) + 1
            user.last_active_at = datetime.utcnow()
            is_new = False
        else:
            user = LiffUser(line_user_id=req.line_user_id, **fields)
            session.add(user)
            is_new = True

        await session.commit()
        await session.refresh(user)

        logger.info(f"LIFF 用戶{'註冊' if is_new else '更新'}: {req.line_user_id} ({req.display_name}) 第{user.visit_count}次")

    return {
        "status": "ok",
        "is_new": is_new,
        "user": {
            "line_user_id": user.line_user_id,
            "display_name": user.display_name,
            "picture_url": user.picture_url,
            "is_friend": user.is_friend,
            "visit_count": user.visit_count,
            "created_at": user.created_at.isoformat(),
            "last_active_at": user.last_active_at.isoformat(),
        },
    }


@router.get("/user/{line_user_id}")
async def get_liff_user(line_user_id: str):
    """查詢 LIFF 用戶資訊"""
    async with async_session() as session:
        result = await session.execute(
            select(LiffUser).where(LiffUser.line_user_id == line_user_id)
        )
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="用戶不存在")

    return {
        "line_user_id": user.line_user_id,
        "display_name": user.display_name,
        "picture_url": user.picture_url,
        "email": user.email,
        "os": user.os,
        "language": user.language,
        "is_in_client": user.is_in_client,
        "is_friend": user.is_friend,
        "context_type": user.context_type,
        "visit_count": user.visit_count,
        "created_at": user.created_at.isoformat(),
        "last_active_at": user.last_active_at.isoformat(),
    }


@router.post("/push")
async def push_message_to_user(req: PushMessageRequest):
    """推播訊息給指定 LIFF 用戶（透過 LINE Messaging API）"""
    if not settings.line_channel_access_token:
        raise HTTPException(status_code=500, detail="LINE_CHANNEL_ACCESS_TOKEN 未設定")

    from linebot.v3.messaging import (
        Configuration, ApiClient, MessagingApi,
        PushMessageRequest as LinePushRequest, TextMessage,
    )

    configuration = Configuration(access_token=settings.line_channel_access_token)
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.push_message(LinePushRequest(
            to=req.line_user_id,
            messages=[TextMessage(text=req.message)],
        ))

    logger.info(f"推播訊息給 {req.line_user_id}: {req.message[:50]}")
    return {"status": "ok", "to": req.line_user_id}


class TrackFavoriteRequest(BaseModel):
    line_user_id: str
    hospital_code: str
    hospital_name: str
    department: str | None = None


@router.post("/favorite")
async def track_favorite(req: TrackFavoriteRequest):
    """記錄用戶查詢的醫院/科別（自動累加次數）"""
    async with async_session() as session:
        query = select(UserFavorite).where(
            UserFavorite.line_user_id == req.line_user_id,
            UserFavorite.hospital_code == req.hospital_code,
        )
        if req.department:
            query = query.where(UserFavorite.department == req.department)
        else:
            query = query.where(UserFavorite.department.is_(None))

        result = await session.execute(query)
        fav = result.scalar_one_or_none()

        if fav:
            fav.use_count = (fav.use_count or 0) + 1
            fav.last_used_at = datetime.utcnow()
        else:
            fav = UserFavorite(
                line_user_id=req.line_user_id,
                hospital_code=req.hospital_code,
                hospital_name=req.hospital_name,
                department=req.department,
            )
            session.add(fav)

        await session.commit()
    return {"status": "ok"}


@router.get("/favorites/{line_user_id}")
async def get_favorites(line_user_id: str, hospital_code: str | None = None, limit: int = 6):
    """取得用戶常用醫院或常用科別"""
    async with async_session() as session:
        query = select(UserFavorite).where(UserFavorite.line_user_id == line_user_id)

        if hospital_code:
            # 取某醫院的常用科別
            query = query.where(
                UserFavorite.hospital_code == hospital_code,
                UserFavorite.department.isnot(None),
            )
        else:
            # 取常用醫院（department 為 null 的）
            query = query.where(UserFavorite.department.is_(None))

        query = query.order_by(UserFavorite.use_count.desc(), UserFavorite.last_used_at.desc()).limit(limit)
        result = await session.execute(query)
        favs = result.scalars().all()

    return {
        "favorites": [
            {
                "hospital_code": f.hospital_code,
                "hospital_name": f.hospital_name,
                "department": f.department,
                "use_count": f.use_count,
            }
            for f in favs
        ]
    }


@router.get("/config")
async def get_liff_config():
    """前端取得 LIFF ID（不暴露其他 secret）"""
    if not settings.liff_id:
        raise HTTPException(status_code=500, detail="LIFF_ID 未設定")
    return {"liff_id": settings.liff_id}
