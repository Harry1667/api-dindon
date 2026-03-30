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

            # 先檢查是否在多步驟流程中（追蹤/預約追蹤）
            if await _handle_track_flow(user_id, text, event.reply_token):
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
        # 查目前號碼
        current_hint = ""
        try:
            import json
            from demo_chat import _redis_client, HOSPITAL_ALIASES
            # 找 hospital_code
            h_code = None
            for alias, (code, name) in HOSPITAL_ALIASES.items():
                if name == hospital:
                    h_code = code
                    break
            if h_code:
                keys = _redis_client.keys(f"progress:{h_code}:*{doctor}*")
                if keys:
                    val = _redis_client.get(keys[0])
                    if val:
                        d = json.loads(val)
                        current_hint = f"\n目前看到第 {d['current_number']} 號"
        except Exception:
            pass
        # 進入等待號碼狀態
        _conversations[user_id] = {
            "state": "waiting_track_number",
            "track_hospital": hospital,
            "track_dept": dept,
            "track_doctor": doctor,
        }
        return (
            f"🔔 追蹤 {hospital} {dept} {doctor}\n"
            f"{current_hint}\n"
            f"請輸入您的掛號號碼："
        )
    return reply


async def _handle_track_flow(user_id: str, text: str, reply_token: str) -> bool:
    """處理追蹤多步驟流程，回傳 True 表示已處理"""
    conv = _conversations.get(user_id, {})
    state = conv.get("state", "")

    if state not in ("waiting_track_number", "waiting_track_mode"):
        return False

    # 取消
    if text in ("取消", "返回", "0"):
        reset_conv(user_id)
        await line_bot_service.reply(reply_token, "已取消追蹤\n\n📋 輸入醫院名稱繼續查詢")
        return True

    # Step 1: 等待號碼
    if state == "waiting_track_number":
        import re
        numbers = re.findall(r"\d+", text)
        if not numbers:
            await line_bot_service.reply(reply_token, "請輸入數字號碼\n輸入「取消」可取消")
            return True

        conv["track_number"] = int(numbers[0])
        conv["state"] = "waiting_track_mode"
        await line_bot_service.reply(reply_token, (
            f"您是第 {conv['track_number']} 號\n\n"
            f"請選擇提醒模式：\n\n"
            f"  1. 📢 每號提醒 — 每次叫號都通知\n"
            f"  2. 🔔 輕量提醒 — 剩 10、5、3、1 號時通知（推薦）\n"
            f"  3. 🔕 最後提醒 — 剩 3 號內才通知"
        ))
        return True

    # Step 2: 等待模式選擇
    if state == "waiting_track_mode":
        mode_map = {
            "1": "normal", "每號": "normal", "每號提醒": "normal",
            "2": "light", "輕量": "light", "輕量提醒": "light",
            "3": "final", "最後": "final", "最後提醒": "final",
        }
        mode = mode_map.get(text.strip(), None)
        if not mode:
            await line_bot_service.reply(reply_token, "請輸入 1、2 或 3 選擇模式")
            return True

        hospital = conv["track_hospital"]
        dept = conv["track_dept"]
        doctor = conv["track_doctor"]
        user_number = conv["track_number"]
        reset_conv(user_id)

        # 建立追蹤
        reply = await line_bot_service._handle_track_with_mode(
            user_id, hospital, dept, doctor, user_number, mode
        )
        await line_bot_service.reply(reply_token, reply)
        return True

    return False


# ============================================================
# 預約追蹤流程（提前設定，看診時段開始後自動監控）
# ============================================================

async def _handle_pretrack_flow(user_id: str, text: str, reply_token: str) -> bool:
    """處理預約追蹤的多步驟流程"""
    conv = _conversations.get(user_id, {})
    state = conv.get("state", "")

    if not state.startswith("pretrack_"):
        return False

    # 任何步驟都可取消
    if text in ("取消", "返回", "0"):
        reset_conv(user_id)
        await line_bot_service.reply(reply_token, "已取消\n\n📋 輸入醫院名稱繼續查詢")
        return True

    # Step 1: 選時段
    if state == "pretrack_session":
        session_map = {"1": "上午診", "2": "下午診", "3": "夜診", "上午": "上午診", "下午": "下午診", "夜": "夜診"}
        session_time = session_map.get(text.strip(), None)
        if not session_time:
            await line_bot_service.reply(reply_token, "請輸入 1、2 或 3：\n\n  1. 上午診\n  2. 下午診\n  3. 夜診")
            return True
        conv["pretrack_session"] = session_time
        conv["state"] = "pretrack_dept"
        await line_bot_service.reply(reply_token, f"⏰ {session_time}\n\n請輸入科別名稱：\n（例如：骨科、心臟內科）")
        return True

    # Step 2: 輸入科別
    if state == "pretrack_dept":
        conv["pretrack_dept"] = text.strip()
        conv["state"] = "pretrack_doctor"
        await line_bot_service.reply(reply_token, f"📌 {conv['pretrack_dept']}\n\n請輸入醫師姓名：")
        return True

    # Step 3: 輸入醫師
    if state == "pretrack_doctor":
        conv["pretrack_doctor"] = text.strip()
        conv["state"] = "pretrack_number"
        await line_bot_service.reply(reply_token, f"👨‍⚕️ {conv['pretrack_doctor']}\n\n請輸入您的掛號號碼：")
        return True

    # Step 4: 輸入號碼
    if state == "pretrack_number":
        import re
        numbers = re.findall(r"\d+", text)
        if not numbers:
            await line_bot_service.reply(reply_token, "請輸入數字號碼")
            return True
        conv["pretrack_number"] = int(numbers[0])
        conv["state"] = "pretrack_mode"
        await line_bot_service.reply(reply_token, (
            f"您是第 {conv['pretrack_number']} 號\n\n"
            f"請選擇提醒模式：\n\n"
            f"  1. 📢 每號提醒\n"
            f"  2. 🔔 輕量提醒（推薦）\n"
            f"  3. 🔕 最後提醒"
        ))
        return True

    # Step 5: 選模式 → 建立
    if state == "pretrack_mode":
        mode_map = {"1": "normal", "2": "light", "3": "final"}
        mode = mode_map.get(text.strip(), None)
        if not mode:
            await line_bot_service.reply(reply_token, "請輸入 1、2 或 3")
            return True

        hospital = conv["pretrack_hospital"]
        hospital_code = conv["pretrack_hospital_code"]
        session_time = conv["pretrack_session"]
        dept = conv["pretrack_dept"]
        doctor = conv["pretrack_doctor"]
        user_number = conv["pretrack_number"]
        reset_conv(user_id)

        from app.services.tracker import TrackerService
        from app.scrapers.registry import AdapterRegistry
        tracker = TrackerService()
        await tracker.create_task(
            line_user_id=user_id,
            hospital_code=hospital_code,
            department=dept,
            doctor_name=doctor,
            clinic_room=None,
            user_number=user_number,
            notify_mode=mode,
            session_time=session_time,
        )

        adapter = AdapterRegistry.get(hospital_code)
        hosp_name = adapter.hospital_name if adapter else hospital
        mode_labels = {"normal": "📢 每號提醒", "light": "🔔 輕量提醒", "final": "🔕 最後提醒"}

        await line_bot_service.reply(reply_token, (
            f"✅ 預約追蹤成功！\n\n"
            f"🏥 {hosp_name}\n"
            f"⏰ {session_time}\n"
            f"📌 {dept} — {doctor}\n"
            f"🎫 第 {user_number} 號\n"
            f"模式：{mode_labels.get(mode, '🔔')}\n\n"
            f"看診開始後系統會自動監控，快到號時通知您"
        ))
        return True

    return False
