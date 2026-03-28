"""LINE Webhook 處理 — 接收 LINE Platform 的事件"""

import logging

from fastapi import APIRouter, Request, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    FollowEvent,
)

from app.config import settings
from app.services.line_bot import LineBotService

logger = logging.getLogger(__name__)
router = APIRouter()

parser = WebhookParser(settings.line_channel_secret)
line_bot_service = LineBotService()


@router.post("/webhook")
async def webhook(request: Request):
    """LINE Webhook endpoint

    LINE Platform 會將用戶訊息 POST 到此 endpoint
    需驗證 X-Line-Signature 確保來源合法
    """
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        events = parser.parse(body_str, signature)
    except InvalidSignatureError:
        logger.warning("Invalid LINE signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        try:
            await _handle_event(event)
        except Exception as e:
            logger.error(f"處理事件失敗: {e}", exc_info=True)

    return "OK"


async def _handle_event(event):
    """分派處理不同類型的事件"""

    if isinstance(event, FollowEvent):
        # 用戶加入好友
        user_id = event.source.user_id
        logger.info(f"新用戶加入: {user_id}")
        await line_bot_service.handle_text_message(
            user_id=user_id,
            text="說明",
            reply_token=event.reply_token,
        )

    elif isinstance(event, MessageEvent):
        if isinstance(event.message, TextMessageContent):
            user_id = event.source.user_id
            text = event.message.text
            logger.info(f"收到訊息: user={user_id} text={text}")
            await line_bot_service.handle_text_message(
                user_id=user_id,
                text=text,
                reply_token=event.reply_token,
            )
