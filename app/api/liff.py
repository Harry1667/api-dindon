"""LIFF 用戶 API — 註冊/查詢 LIFF 用戶、推播訊息"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.models.database import async_session
from app.models.liff_user import LiffUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/liff", tags=["LIFF"])


class LiffRegisterRequest(BaseModel):
    line_user_id: str
    display_name: str | None = None
    picture_url: str | None = None
    status_message: str | None = None


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

        if user:
            # 更新資料
            user.display_name = req.display_name
            user.picture_url = req.picture_url
            user.status_message = req.status_message
            user.last_active_at = datetime.utcnow()
            is_new = False
        else:
            # 新用戶
            user = LiffUser(
                line_user_id=req.line_user_id,
                display_name=req.display_name,
                picture_url=req.picture_url,
                status_message=req.status_message,
            )
            session.add(user)
            is_new = True

        await session.commit()
        await session.refresh(user)

        logger.info(f"LIFF 用戶{'註冊' if is_new else '更新'}: {req.line_user_id} ({req.display_name})")

    return {
        "status": "ok",
        "is_new": is_new,
        "user": {
            "line_user_id": user.line_user_id,
            "display_name": user.display_name,
            "picture_url": user.picture_url,
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


@router.get("/config")
async def get_liff_config():
    """前端取得 LIFF ID（不暴露其他 secret）"""
    if not settings.liff_id:
        raise HTTPException(status_code=500, detail="LIFF_ID 未設定")
    return {"liff_id": settings.liff_id}
