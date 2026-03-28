"""LINE Bot 互動邏輯 — 解析用戶訊息並回覆看診進度"""

import re
import logging

from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)

from app.config import settings
from app.services.cache import CacheService
from app.services.tracker import TrackerService
from app.scrapers.registry import AdapterRegistry

logger = logging.getLogger(__name__)

# 醫院名稱對照
HOSPITAL_ALIASES = {
    "萬芳": "wanfang",
    "萬芳醫院": "wanfang",
    # 未來新增:
    # "台大": "ntuh",
    # "榮總": "tpvgh",
}


class LineBotService:
    """處理 LINE 訊息互動"""

    def __init__(self):
        config = Configuration(access_token=settings.line_channel_access_token)
        self.api_client = AsyncApiClient(config)
        self.api = AsyncMessagingApi(self.api_client)
        self.cache = CacheService()
        self.tracker = TrackerService()

    async def handle_text_message(self, user_id: str, text: str, reply_token: str):
        """處理用戶文字訊息"""
        text = text.strip()

        # 1. 追蹤指令: 「追蹤 萬芳 精神科 許元彰 我是60號」
        if text.startswith("追蹤"):
            reply = await self._handle_track_command(user_id, text)
        # 2. 取消追蹤
        elif text.startswith("取消追蹤") or text.startswith("停止追蹤"):
            reply = await self._handle_cancel_track(user_id, text)
        # 3. 查看我的追蹤
        elif text in ("我的追蹤", "追蹤列表", "追蹤狀態"):
            reply = await self._handle_list_tracks(user_id)
        # 4. 說明
        elif text in ("說明", "幫助", "help", "使用說明"):
            reply = self._get_help_message()
        # 5. 一般查詢: 「萬芳 精神科」「萬芳 許元彰」「萬芳 282診」
        else:
            reply = await self._handle_query(text)

        await self.api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=reply)],
            )
        )

    async def push_message(self, user_id: str, text: str):
        """主動推播訊息給用戶"""
        await self.api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=text)],
            )
        )

    async def _handle_query(self, text: str) -> str:
        """處理看診進度查詢

        支援格式:
          「萬芳 精神科」
          「萬芳 許元彰」
          「萬芳 282診」
          「萬芳 精神科 許元彰」
        """
        parts = text.split()
        if not parts:
            return self._get_help_message()

        # 第一個詞嘗試匹配醫院
        hospital_code = None
        for alias, code in HOSPITAL_ALIASES.items():
            if alias in parts[0]:
                hospital_code = code
                break

        if not hospital_code:
            # 如果沒指定醫院，預設萬芳（MVP 階段只有一家）
            hospital_code = "wanfang"
            search_parts = parts
        else:
            search_parts = parts[1:]

        if not search_parts:
            # 只輸入醫院名，回傳所有診間
            all_progress = await self.cache.get_all_progress(hospital_code)
            if not all_progress:
                return f"目前沒有看診中的診間資料，可能是非看診時段或資料尚未更新。"
            messages = [p.format_message() for p in all_progress]
            return "\n".join(messages)

        # 解析搜尋條件
        department = None
        doctor_name = None
        clinic_room = None

        for part in search_parts:
            if re.match(r"\d+診", part):
                clinic_room = part
            elif any(kw in part for kw in ["科", "部", "中心"]):
                department = part
            else:
                # 假設是醫師名字
                doctor_name = part

        results = await self.cache.search_progress(
            hospital_code=hospital_code,
            department=department,
            doctor_name=doctor_name,
            clinic_room=clinic_room,
        )

        if not results:
            search_desc = " ".join(search_parts)
            return f"找不到「{search_desc}」的看診進度，請確認科別或醫師名稱是否正確。"

        messages = [p.format_message() for p in results]
        return "\n".join(messages)

    async def _handle_track_command(self, user_id: str, text: str) -> str:
        """處理追蹤指令

        格式: 追蹤 萬芳 精神科 許元彰 我是60號
        或:   追蹤 萬芳 282診 60號
        """
        # 提取號碼
        number_match = re.search(r"(\d+)\s*號", text)
        if not number_match:
            return "請提供您的掛號號碼，例如:\n追蹤 萬芳 精神科 許元彰 我是60號"

        user_number = int(number_match.group(1))

        # 移除「追蹤」和號碼部分，解析剩餘條件
        clean_text = re.sub(r"追蹤\s*", "", text)
        clean_text = re.sub(r"我?是?\d+\s*號", "", clean_text).strip()

        parts = clean_text.split()
        if not parts:
            return "請提供醫院和科別資訊，例如:\n追蹤 萬芳 精神科 許元彰 我是60號"

        # 解析醫院
        hospital_code = None
        for alias, code in HOSPITAL_ALIASES.items():
            if alias in parts[0]:
                hospital_code = code
                break

        if not hospital_code:
            hospital_code = "wanfang"
            search_parts = parts
        else:
            search_parts = parts[1:]

        # 解析科別/醫師/診間
        department = None
        doctor_name = None
        clinic_room = None

        for part in search_parts:
            if re.match(r"\d+診", part):
                clinic_room = part
            elif any(kw in part for kw in ["科", "部", "中心"]):
                department = part
            else:
                doctor_name = part

        if not department and not doctor_name and not clinic_room:
            return "請至少提供科別或醫師名稱，例如:\n追蹤 萬芳 精神科 許元彰 我是60號"

        # 先查詢當前進度確認診間存在
        results = await self.cache.search_progress(
            hospital_code=hospital_code,
            department=department,
            doctor_name=doctor_name,
            clinic_room=clinic_room,
        )

        # 建立追蹤任務
        adapter = AdapterRegistry.get(hospital_code)
        hospital_name = adapter.hospital_name if adapter else hospital_code

        task = await self.tracker.create_task(
            line_user_id=user_id,
            hospital_code=hospital_code,
            department=department or "",
            doctor_name=doctor_name,
            clinic_room=clinic_room,
            user_number=user_number,
        )

        if results:
            p = results[0]
            remaining = user_number - p.current_number
            reply = (
                f"已開始追蹤 {hospital_name} "
                f"{p.department} {p.doctor_name} {p.clinic_room}\n"
                f"您是第 {user_number} 號\n"
                f"目前看到第 {p.current_number} 號，還有約 {max(0, remaining)} 位\n"
                f"快到時會通知您！"
            )
        else:
            desc = " ".join(filter(None, [department, doctor_name, clinic_room]))
            reply = (
                f"已建立追蹤：{hospital_name} {desc}\n"
                f"您是第 {user_number} 號\n"
                f"目前暫無該診間的即時資料，系統會持續監控，快到時通知您。"
            )

        return reply

    async def _handle_cancel_track(self, user_id: str, text: str) -> str:
        """取消追蹤"""
        cancelled = await self.tracker.cancel_all_tasks(line_user_id=user_id)
        if cancelled > 0:
            return f"已取消 {cancelled} 筆追蹤任務。"
        return "您目前沒有進行中的追蹤任務。"

    async def _handle_list_tracks(self, user_id: str) -> str:
        """查看追蹤列表"""
        tasks = await self.tracker.get_active_tasks(line_user_id=user_id)
        if not tasks:
            return "您目前沒有進行中的追蹤任務。\n\n輸入「追蹤 萬芳 科別 醫師 我是N號」即可開始追蹤。"

        lines = ["您目前的追蹤任務：\n"]
        for t in tasks:
            desc = f"{t.hospital_code} {t.department}"
            if t.doctor_name:
                desc += f" {t.doctor_name}"
            if t.clinic_room:
                desc += f" {t.clinic_room}"
            lines.append(f"• {desc} — 您是第 {t.user_number} 號")

        lines.append("\n輸入「取消追蹤」可取消所有追蹤。")
        return "\n".join(lines)

    def _get_help_message(self) -> str:
        return (
            "叮咚到號 — 醫院看診進度通知\n"
            "────────────\n"
            "📋 查詢進度：\n"
            "  萬芳 精神科\n"
            "  萬芳 許元彰\n"
            "  萬芳 282診\n"
            "\n"
            "🔔 追蹤掛號（快到號自動通知）：\n"
            "  追蹤 萬芳 精神科 許元彰 我是60號\n"
            "\n"
            "📌 其他指令：\n"
            "  我的追蹤 — 查看追蹤列表\n"
            "  取消追蹤 — 取消所有追蹤\n"
            "  說明 — 顯示此說明"
        )
