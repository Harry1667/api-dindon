"""LINE Webhook 處理 — 接收 LINE Platform 的事件

使用 demo_chat.handle_message 處理對話邏輯（互動式查詢），
透過 LineBotService 回覆訊息。
"""

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
from demo_chat import handle_message, reset_conv, _conversations

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
        user_id = event.source.user_id
        logger.info(f"新用戶加入: {user_id}")
        reply = await handle_message("說明", user_id)
        await line_bot_service.reply(event.reply_token, reply)

    elif isinstance(event, MessageEvent):
        if isinstance(event.message, TextMessageContent):
            user_id = event.source.user_id
            text = event.message.text
            logger.info(f"收到訊息: user={user_id} text={text}")

            # 先檢查是否在等待追蹤號碼
            if await _handle_track_number(user_id, text, event.reply_token):
                return

            reply = await handle_message(text, user_id)
            reply = _convert_for_line(reply, user_id)
            await line_bot_service.reply(event.reply_token, reply)


def _convert_for_line(reply: str, user_id: str) -> str:
    """將 demo_chat 的特殊指令轉為 LINE 互動式追蹤流程

    __TRACK__醫院\t科別\t醫師 → 詢問掛號號碼，進入等待號碼狀態
    """
    if reply.startswith("__TRACK__"):
        parts = reply.replace("__TRACK__", "").split("\t")
        hospital = parts[0].strip() if len(parts) > 0 else ""
        dept = parts[1].strip() if len(parts) > 1 else ""
        doctor = parts[2].strip() if len(parts) > 2 else ""
        # 進入等待號碼狀態
        _conversations[user_id] = {
            "state": "waiting_track_number",
            "track_hospital": hospital,
            "track_dept": dept,
            "track_doctor": doctor,
        }
        return (
            f"🔔 追蹤 {hospital} {dept} {doctor}\n\n"
            f"請輸入您的掛號號碼：\n"
            f"（例如：60）"
        )
    return reply


async def _handle_track_number(user_id: str, text: str, reply_token: str) -> bool:
    """處理等待掛號號碼的狀態，回傳 True 表示已處理"""
    conv = _conversations.get(user_id, {})
    if conv.get("state") != "waiting_track_number":
        return False

    # 取消
    if text in ("取消", "返回", "0"):
        reset_conv(user_id)
        await line_bot_service.reply(reply_token, "已取消追蹤\n\n📋 輸入醫院名稱繼續查詢")
        return True

    # 提取號碼
    import re
    numbers = re.findall(r"\d+", text)
    if not numbers:
        await line_bot_service.reply(reply_token, "請輸入數字號碼（例如：60）\n輸入「取消」可取消")
        return True

    user_number = int(numbers[0])
    hospital = conv["track_hospital"]
    dept = conv["track_dept"]
    doctor = conv["track_doctor"]
    reset_conv(user_id)

    # 組合追蹤指令，交給 LineBotService 處理
    track_text = f"追蹤 {hospital} {dept} {doctor} 我是{user_number}號"
    reply = await line_bot_service._handle_track_command(user_id, track_text)
    await line_bot_service.reply(reply_token, reply)
    return True
