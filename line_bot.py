"""叮咚到號 — LINE Bot (FastAPI)

直接複用 demo_chat.py 的 handle_message 狀態機，
追蹤功能改為 server-side threading + LINE push message。

啟動（開發）: uvicorn line_bot:app --host 0.0.0.0 --port 5000
啟動（正式）: 見 Dockerfile / docker-compose.yml
"""

import asyncio
import json
import os
import re
import logging
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)

# 複用 demo_chat 的核心邏輯
from demo_chat import (
    handle_message,
    get_mock_results,
    poll_mock_doctor,
    MOCK_BRANCH_ID,
    MOCK_HOSPITAL_NAME,
    ENABLE_MOCK_HOSPITAL,
    TW_TZ,
    _resolve_hospital,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== 環境變數 ==========

def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("請設定 LINE_CHANNEL_SECRET 和 LINE_CHANNEL_ACCESS_TOKEN")

parser = WebhookParser(CHANNEL_SECRET)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)

ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "dingdon2026")

security = HTTPBasic()


# ========== 用戶註冊表（MySQL） ==========

import pymysql

MYSQL_HOST = os.environ.get("MYSQL_HOST", "host.docker.internal")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "")
MYSQL_PASS = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB = os.environ.get("MYSQL_DATABASE", "")


def _get_db():
    """取得 MySQL 連線"""
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _init_tables():
    """建立所有資料表（若不存在）"""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            # 用戶表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS line_users (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    line_uid    VARCHAR(64)  NOT NULL UNIQUE,
                    name        VARCHAR(100) NOT NULL DEFAULT '',
                    first_seen  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_active DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 醫院參考表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hospitals (
                    id              INT AUTO_INCREMENT PRIMARY KEY,
                    code            VARCHAR(50)   NOT NULL UNIQUE COMMENT '醫院代碼 eg. cgmh_taipei',
                    name            VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '顯示名 eg. 台北長庚',
                    aliases         TEXT           COMMENT '別名,逗號分隔（搜尋用）',
                    -- 地理位置
                    city            VARCHAR(20)   NOT NULL DEFAULT '' COMMENT '市/縣 eg. 台北市',
                    district        VARCHAR(20)   NOT NULL DEFAULT '' COMMENT '區 eg. 信義區',
                    address         VARCHAR(200)  NOT NULL DEFAULT '' COMMENT '完整地址',
                    lat             DECIMAL(10,7) DEFAULT NULL COMMENT '緯度（未來距離計算）',
                    lng             DECIMAL(10,7) DEFAULT NULL COMMENT '經度',
                    -- 聯絡資訊
                    phone           VARCHAR(30)   NOT NULL DEFAULT '' COMMENT '服務電話',
                    emergency_phone VARCHAR(30)   NOT NULL DEFAULT '' COMMENT '急診電話',
                    fax             VARCHAR(30)   NOT NULL DEFAULT '' COMMENT '傳真',
                    -- 線上資源
                    website         VARCHAR(300)  NOT NULL DEFAULT '' COMMENT '官方網站',
                    register_url    VARCHAR(300)  NOT NULL DEFAULT '' COMMENT '網路掛號網址',
                    -- 醫院屬性
                    level           VARCHAR(20)   NOT NULL DEFAULT '' COMMENT '醫學中心/區域醫院/地區醫院/診所',
                    type            VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '綜合醫院/專科醫院/中醫院',
                    beds            INT            DEFAULT NULL COMMENT '病床數',
                    -- 營運資訊
                    business_hours  TEXT           COMMENT '營業時間 JSON eg. {"Mon":"08:30-17:00",...}',
                    traffic_info    TEXT           COMMENT '交通方式（捷運/公車/停車場）',
                    note            TEXT           COMMENT '備註（特殊公告等）',
                    -- 狀態
                    enabled         TINYINT(1)    NOT NULL DEFAULT 1,
                    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_city_district (city, district)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 科別參考表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS departments (
                    id              INT AUTO_INCREMENT PRIMARY KEY,
                    hospital_id     INT           NOT NULL COMMENT 'FK → hospitals',
                    name            VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '科別名 eg. 心臟內科',
                    category        VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '大分類：內科/外科/婦兒科/中醫/牙科/其他',
                    treats          TEXT           COMMENT '主治疾病（逗號分隔）eg. 心臟病,高血壓,心律不整',
                    symptoms        TEXT           COMMENT '常見症狀（逗號分隔）eg. 胸悶,心悸,呼吸困難',
                    description     TEXT           COMMENT '科別說明',
                    register_note   TEXT           COMMENT '掛號提醒 eg. 初診請攜帶轉診單',
                    enabled         TINYINT(1)    NOT NULL DEFAULT 1,
                    INDEX idx_hospital_dept (hospital_id),
                    UNIQUE KEY uk_dept (hospital_id, name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 醫師參考表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS doctors (
                    id              INT AUTO_INCREMENT PRIMARY KEY,
                    hospital_id     INT           NOT NULL COMMENT 'FK → hospitals',
                    dept_id         INT           DEFAULT NULL COMMENT 'FK → departments',
                    dept            VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '科別名（冗餘，方便查詢）',
                    name            VARCHAR(50)   NOT NULL DEFAULT '',
                    gender          VARCHAR(5)    NOT NULL DEFAULT '' COMMENT '男/女',
                    title           VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '職稱：主任醫師/主治醫師/住院醫師',
                    specialty       TEXT           COMMENT '專長描述（逗號分隔）',
                    education       TEXT           COMMENT '學歷（逗號分隔）',
                    experience      TEXT           COMMENT '經歷（逗號分隔）',
                    available_days  VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '看診日 eg. 一,三,五',
                    room            VARCHAR(20)   NOT NULL DEFAULT '',
                    session_period  VARCHAR(10)   NOT NULL DEFAULT '' COMMENT '上午/下午/夜晚',
                    photo_url       VARCHAR(300)  NOT NULL DEFAULT '' COMMENT '醫師照片 URL',
                    note            TEXT           COMMENT '備註',
                    enabled         TINYINT(1)    NOT NULL DEFAULT 1,
                    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_hospital (hospital_id),
                    INDEX idx_dept_id (dept_id),
                    INDEX idx_name (name),
                    UNIQUE KEY uk_doc (hospital_id, dept, name, session_period)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 追蹤記錄表（用戶角度）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tracking_logs (
                    id              INT AUTO_INCREMENT PRIMARY KEY,
                    line_uid        VARCHAR(64)  NOT NULL,
                    hospital        VARCHAR(100) NOT NULL DEFAULT '',
                    dept            VARCHAR(100) NOT NULL DEFAULT '',
                    doctor          VARCHAR(50)  NOT NULL DEFAULT '',
                    room            VARCHAR(20)  NOT NULL DEFAULT '',
                    session_period  VARCHAR(10)  NOT NULL DEFAULT '' COMMENT '上午/下午/夜晚',
                    user_number     INT          DEFAULT NULL,
                    start_number    INT          NOT NULL DEFAULT 0,
                    end_number      INT          DEFAULT NULL,
                    start_time      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    end_time        DATETIME     DEFAULT NULL,
                    wait_seconds    INT          DEFAULT NULL,
                    status          VARCHAR(20)  NOT NULL DEFAULT 'active',
                    push_count      INT          NOT NULL DEFAULT 0,
                    number_changes  INT          NOT NULL DEFAULT 0,
                    user_skipped    TINYINT(1)   NOT NULL DEFAULT 0,
                    INDEX idx_line_uid (line_uid),
                    INDEX idx_start_time (start_time),
                    INDEX idx_doctor (doctor),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 醫師每日看診統計（診間角度）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS doctor_daily_logs (
                    id              INT AUTO_INCREMENT PRIMARY KEY,
                    date            DATE         NOT NULL,
                    hospital        VARCHAR(100) NOT NULL DEFAULT '',
                    dept            VARCHAR(100) NOT NULL DEFAULT '',
                    doctor          VARCHAR(50)  NOT NULL DEFAULT '',
                    room            VARCHAR(20)  NOT NULL DEFAULT '',
                    session_period  VARCHAR(10)  NOT NULL DEFAULT '' COMMENT '上午/下午/夜晚',
                    first_number    INT          NOT NULL DEFAULT 0 COMMENT '第一個叫到的號',
                    last_number     INT          NOT NULL DEFAULT 0 COMMENT '最後一個叫到的號',
                    first_seen_at   DATETIME     DEFAULT NULL COMMENT '第一次偵測到號碼變動',
                    last_seen_at    DATETIME     DEFAULT NULL COMMENT '最後一次號碼變動',
                    total_calls     INT          NOT NULL DEFAULT 0 COMMENT '叫號次數',
                    skip_count      INT          NOT NULL DEFAULT 0 COMMENT '過號次數',
                    poll_count      INT          NOT NULL DEFAULT 0 COMMENT '偵測次數',
                    UNIQUE KEY uk_daily (date, hospital, doctor, session_period),
                    INDEX idx_date (date),
                    INDEX idx_doctor_daily (doctor, date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
        conn.close()
        logger.info("所有資料表已就緒 (line_users, hospitals, doctors, tracking_logs, doctor_daily_logs)")
    except Exception as e:
        logger.error(f"建立資料表失敗: {e}")


_init_tables()


# ---- 追蹤記錄寫入 ----

def _save_track_log(line_uid: str, hospital: str, dept: str, doctor: str,
                    room: str, session_period: str, start_number: int) -> int:
    """開始追蹤時寫入一筆記錄，回傳 log_id"""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tracking_logs "
                "(line_uid, hospital, dept, doctor, room, session_period, start_number) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (line_uid, hospital, dept, doctor, room, session_period, start_number),
            )
            log_id = cur.lastrowid
        conn.commit()
        conn.close()
        return log_id
    except Exception as e:
        logger.error(f"寫入追蹤記錄失敗: {e}")
        return 0


def _update_track_log(log_id: int, **kwargs):
    """更新追蹤記錄欄位（彈性更新）"""
    if not log_id or not kwargs:
        return
    allowed = {
        "user_number", "end_number", "end_time", "wait_seconds",
        "status", "push_count", "number_changes", "user_skipped",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    try:
        set_clause = ", ".join(f"{k}=%s" for k in fields)
        values = list(fields.values()) + [log_id]
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(f"UPDATE tracking_logs SET {set_clause} WHERE id=%s", values)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"更新追蹤記錄失敗: {e}")


def _finish_track_log(t: dict, status: str, end_number: int):
    """追蹤結束時一次性更新所有結束欄位"""
    log_id = t.get("log_id", 0)
    if not log_id:
        return
    now = datetime.now(TW_TZ)
    start = t.get("start_time")
    wait_sec = int((now - start).total_seconds()) if start else None
    _update_track_log(
        log_id,
        status=status,
        end_number=end_number,
        end_time=now.strftime("%Y-%m-%d %H:%M:%S"),
        wait_seconds=wait_sec,
        push_count=t.get("push_count", 0),
        number_changes=t.get("number_changes", 0),
        user_number=t.get("user_number"),
    )


# ---- 醫師每日看診統計寫入 ----

def _record_doctor_poll(hospital: str, dept: str, doctor: str, room: str,
                        session_period: str, cur_number: int, is_skipped: bool):
    """每次 polling 偵測到號碼變動時呼叫，用 UPSERT 累積統計"""
    now = datetime.now(TW_TZ)
    today = now.strftime("%Y-%m-%d")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            # INSERT ... ON DUPLICATE KEY UPDATE (利用 uk_daily 唯一鍵)
            cur.execute("""
                INSERT INTO doctor_daily_logs
                    (date, hospital, dept, doctor, room, session_period,
                     first_number, last_number, first_seen_at, last_seen_at,
                     total_calls, skip_count, poll_count)
                VALUES (%s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        1, %s, 1)
                ON DUPLICATE KEY UPDATE
                    last_number  = %s,
                    last_seen_at = %s,
                    total_calls  = total_calls + 1,
                    skip_count   = skip_count + %s,
                    poll_count   = poll_count + 1,
                    room         = %s
            """, (
                today, hospital, dept, doctor, room, session_period,
                cur_number, cur_number, now_str, now_str,
                1 if is_skipped else 0,
                # ON DUPLICATE KEY UPDATE params:
                cur_number, now_str,
                1 if is_skipped else 0,
                room,
            ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"更新 doctor_daily_logs 失敗: {e}")


def _get_doctor_daily_stats(days: int = 7) -> list[dict]:
    """取最近 N 天的醫師看診統計"""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT date, hospital, dept, doctor, room, session_period,
                       first_number, last_number,
                       first_seen_at, last_seen_at,
                       total_calls, skip_count, poll_count
                FROM doctor_daily_logs
                WHERE date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                ORDER BY date DESC, hospital, session_period, doctor
            """, (days,))
            rows = cur.fetchall()
        conn.close()

        result = []
        for r in rows:
            # 計算持續時間
            duration_min = None
            if r["first_seen_at"] and r["last_seen_at"]:
                delta = r["last_seen_at"] - r["first_seen_at"]
                duration_min = round(delta.total_seconds() / 60, 1)

            # 計算平均每號分鐘數
            avg_min_per_num = None
            if duration_min and r["total_calls"] > 1:
                avg_min_per_num = round(duration_min / r["total_calls"], 1)

            # 過號率
            skip_rate = None
            if r["total_calls"] > 0:
                skip_rate = round(r["skip_count"] / r["total_calls"] * 100, 1)

            result.append({
                "date": r["date"].strftime("%m/%d") if r["date"] else "",
                "hospital": r["hospital"],
                "dept": r["dept"],
                "doctor": r["doctor"],
                "room": r["room"],
                "session": r["session_period"],
                "first_num": r["first_number"],
                "last_num": r["last_number"],
                "first_time": r["first_seen_at"].strftime("%H:%M") if r["first_seen_at"] else "",
                "last_time": r["last_seen_at"].strftime("%H:%M") if r["last_seen_at"] else "",
                "duration_min": duration_min,
                "total_calls": r["total_calls"],
                "avg_min": avg_min_per_num,
                "skip_count": r["skip_count"],
                "skip_rate": skip_rate,
                "poll_count": r["poll_count"],
            })
        return result
    except Exception as e:
        logger.error(f"查詢 doctor_daily_stats 失敗: {e}")
        return []


class UserRegistry:
    """管理 LINE 用戶資料（MySQL 儲存）

    line_uid = LINE 的 User ID（U 開頭 33 碼），全域唯一
    id = MySQL 自增流水號，方便後台顯示 #001, #002...
    """

    def __init__(self):
        self._lock = threading.Lock()
        # 記憶體快取，避免每次都查 DB
        self._cache: dict[str, dict] = {}
        self._load_cache()

    def _load_cache(self):
        try:
            conn = _get_db()
            with conn.cursor() as cur:
                cur.execute("SELECT id, line_uid, name, first_seen FROM line_users ORDER BY id")
                rows = cur.fetchall()
            conn.close()
            for r in rows:
                self._cache[r["line_uid"]] = {
                    "no": r["id"],
                    "name": r["name"],
                    "first_seen": r["first_seen"].strftime("%Y-%m-%d %H:%M") if r["first_seen"] else "",
                }
            logger.info(f"已載入 {len(self._cache)} 位用戶")
        except Exception as e:
            logger.error(f"載入用戶快取失敗: {e}")

    def register(self, user_id: str, display_name: str = "") -> dict:
        """註冊或更新用戶"""
        with self._lock:
            # 快取命中 → 檢查是否需要更新暱稱
            if user_id in self._cache:
                u = self._cache[user_id]
                if display_name and display_name != u["name"]:
                    u["name"] = display_name
                    try:
                        conn = _get_db()
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE line_users SET name=%s, last_active=NOW() WHERE line_uid=%s",
                                (display_name, user_id),
                            )
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        logger.error(f"更新用戶失敗: {e}")
                else:
                    # 更新最後活躍時間（非同步不阻塞，偶爾失敗沒關係）
                    try:
                        conn = _get_db()
                        with conn.cursor() as cur:
                            cur.execute("UPDATE line_users SET last_active=NOW() WHERE line_uid=%s", (user_id,))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
                return u

            # 新用戶 → 寫入 MySQL
            name = display_name or ""
            try:
                conn = _get_db()
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO line_users (line_uid, name) VALUES (%s, %s)",
                        (user_id, name),
                    )
                    new_id = cur.lastrowid
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"新增用戶失敗: {e}")
                return {"no": 0, "name": name or user_id[-6:], "first_seen": ""}

            u = {
                "no": new_id,
                "name": name or f"用戶{new_id}",
                "first_seen": datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M"),
            }
            self._cache[user_id] = u
            logger.info(f"新用戶 #{new_id} {u['name']} ({user_id})")
            return u

    def get(self, user_id: str) -> dict | None:
        with self._lock:
            return self._cache.get(user_id)

    def get_display(self, user_id: str) -> str:
        """回傳 '#001 暱稱' 格式"""
        u = self.get(user_id)
        if u:
            return f"#{u['no']:03d} {u['name']}"
        return user_id[-6:]

    def get_all(self) -> list[dict]:
        """從 MySQL 取全部用戶"""
        try:
            conn = _get_db()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, line_uid, name, first_seen, last_active "
                    "FROM line_users ORDER BY id"
                )
                rows = cur.fetchall()
            conn.close()
            return [{
                "no": r["id"],
                "line_uid": r["line_uid"][-8:],  # 後台只顯示尾 8 碼
                "name": r["name"],
                "first_seen": r["first_seen"].strftime("%Y-%m-%d %H:%M") if r["first_seen"] else "",
                "last_active": r["last_active"].strftime("%m/%d %H:%M") if r["last_active"] else "",
            } for r in rows]
        except Exception as e:
            logger.error(f"查詢用戶列表失敗: {e}")
            return []

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._cache)


user_reg = UserRegistry()


def _fetch_line_profile(user_id: str) -> str:
    """用 LINE API 取得用戶暱稱"""
    try:
        with ApiClient(configuration) as client:
            api = MessagingApi(client)
            profile = api.get_profile(user_id)
            return profile.display_name or ""
    except Exception as e:
        logger.warning(f"取得用戶 profile 失敗: {e}")
        return ""


# ========== 訊息分類 ==========

_NAV_COMMANDS = frozenset({
    "追蹤", "別科", "查詢別科", "換科", "返回", "主選單",
    "重置", "取消", "跳過", "略過", "skip", "狀態", "追蹤狀態",
    "醫院", "列表", "測試", "test", "有哪些", "支援",
})


def _is_chat_message(text: str) -> bool:
    """判斷是否為「對話」訊息（非選單/導航操作）
    回傳 False 的：純數字、導航指令、醫院名、取消追蹤等
    """
    t = text.strip()
    if not t:
        return False
    # 純數字 → 選單選擇
    if t.isdigit():
        return False
    # 導航指令
    if t in _NAV_COMMANDS:
        return False
    if "取消追蹤" in t or "停止追蹤" in t:
        return False
    # 是醫院名 → 導航
    try:
        if _resolve_hospital(t):
            return False
    except Exception:
        pass
    return True


# ========== 統計引擎 ==========

class Stats:
    """記憶體內統計收集器"""

    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = datetime.now(TW_TZ)
        # 計數器
        self.total_messages = 0
        self.total_follows = 0
        self.total_tracks_started = 0
        self.total_tracks_completed = 0  # 到號
        self.total_pushes = 0
        # 每小時訊息量 {日期時間字串: count}
        self.hourly_messages: dict[str, int] = defaultdict(int)
        # 每日統計 {日期: count}
        self.daily_messages: dict[str, int] = defaultdict(int)
        self.daily_users: dict[str, set] = defaultdict(set)
        # 用戶訊息數 {user_id: count}
        self.user_msg_count: dict[str, int] = defaultdict(int)
        # 用戶追蹤數 {user_id: count}
        self.user_track_count: dict[str, int] = defaultdict(int)
        # 最近訊息（最多 200 筆，只存對話訊息）
        self.recent_messages: list[dict] = []
        self.MAX_RECENT = 200
        # 熱門查詢 {醫院|科別|醫師: count}
        self.query_count: dict[str, int] = defaultdict(int)

    def record_message(self, user_id: str, text: str, show_in_recent: bool = True):
        now = datetime.now(TW_TZ)
        display = user_reg.get_display(user_id)
        with self._lock:
            self.total_messages += 1
            hour_key = now.strftime("%Y-%m-%d %H:00")
            day_key = now.strftime("%Y-%m-%d")
            self.hourly_messages[hour_key] += 1
            self.daily_messages[day_key] += 1
            self.daily_users[day_key].add(user_id)
            self.user_msg_count[user_id] += 1
            if show_in_recent:
                self.recent_messages.append({
                    "time": now.strftime("%m/%d %H:%M:%S"),
                    "user": display,
                    "text": text[:50],
                })
                if len(self.recent_messages) > self.MAX_RECENT:
                    self.recent_messages = self.recent_messages[-self.MAX_RECENT:]

    def record_follow(self):
        with self._lock:
            self.total_follows += 1

    def record_track_start(self, user_id: str, hospital: str, dept: str, doctor: str):
        with self._lock:
            self.total_tracks_started += 1
            key = f"{hospital}|{dept}|{doctor}"
            self.query_count[key] += 1
            self.user_track_count[user_id] += 1

    def record_track_complete(self):
        with self._lock:
            self.total_tracks_completed += 1

    def record_push(self):
        with self._lock:
            self.total_pushes += 1

    def get_snapshot(self) -> dict:
        now = datetime.now(TW_TZ)
        today = now.strftime("%Y-%m-%d")
        with self._lock:
            # 最近 24 小時的每小時資料
            hours_data = []
            for i in range(23, -1, -1):
                t = now - timedelta(hours=i)
                key = t.strftime("%Y-%m-%d %H:00")
                hours_data.append({
                    "hour": t.strftime("%H:00"),
                    "count": self.hourly_messages.get(key, 0),
                })

            # 最近 7 天
            days_data = []
            for i in range(6, -1, -1):
                d = now - timedelta(days=i)
                key = d.strftime("%Y-%m-%d")
                days_data.append({
                    "date": d.strftime("%m/%d"),
                    "messages": self.daily_messages.get(key, 0),
                    "users": len(self.daily_users.get(key, set())),
                })

            # 活躍追蹤
            active_tracks = []
            for uid, tracks in _tracking_store.items():
                for t in tracks:
                    if t["active"]:
                        active_tracks.append({
                            "user": user_reg.get_display(uid),
                            "doctor": t["doctor"],
                            "hospital": t["hospital"],
                            "user_number": t.get("user_number"),
                            "current": t["last_cur_n"],
                        })

            # Top 用戶（依追蹤數排序）
            top_users = sorted(
                self.user_track_count.items(),
                key=lambda x: x[1], reverse=True
            )[:10]

            # 熱門醫師（含醫院+科別）
            top_queries = sorted(
                self.query_count.items(),
                key=lambda x: x[1], reverse=True
            )[:10]

            uptime = now - self.start_time
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes = remainder // 60

            return {
                "uptime": f"{hours}h {minutes}m",
                "now": now.strftime("%Y-%m-%d %H:%M:%S"),
                "today_messages": self.daily_messages.get(today, 0),
                "today_users": len(self.daily_users.get(today, set())),
                "total_messages": self.total_messages,
                "total_follows": self.total_follows,
                "total_users": user_reg.count,
                "total_tracks_started": self.total_tracks_started,
                "total_tracks_completed": self.total_tracks_completed,
                "total_pushes": self.total_pushes,
                "active_trackings": len(active_tracks),
                "active_tracks": active_tracks,
                "hourly": hours_data,
                "daily": days_data,
                "recent": list(reversed(self.recent_messages[-50:])),
                "top_users": [{"user": user_reg.get_display(u), "tracks": c} for u, c in top_users],
                "top_queries": [
                    {
                        "hospital": parts[0] if len(parts) > 0 else "",
                        "dept": parts[1] if len(parts) > 1 else "",
                        "doctor": parts[2] if len(parts) > 2 else key,
                        "count": c,
                    }
                    for key, c in top_queries
                    for parts in [key.split("|")]
                ],
                "users_list": user_reg.get_all(),
                "tracking_logs": _get_tracking_logs(50),
                "doctor_daily": _get_doctor_daily_stats(7),
            }


stats = Stats()


# ========== 追蹤引擎（server-side） ==========

MAX_TRACKS_PER_USER = 3
POLL_INTERVAL = 15  # 秒

# 追蹤任務：{user_id: [track_obj, ...]}
_tracking_store: dict[str, list[dict]] = {}
_tracking_lock = threading.Lock()


def _get_user_tracks(user_id: str) -> list[dict]:
    with _tracking_lock:
        return _tracking_store.get(user_id, [])


def _add_track(user_id: str, track: dict) -> str | None:
    """新增追蹤，成功回傳 None，失敗回傳錯誤訊息"""
    with _tracking_lock:
        tracks = _tracking_store.setdefault(user_id, [])
        for t in tracks:
            if t["doctor"] == track["doctor"] and t["active"]:
                return f"已在追蹤 {track['doctor']}，無需重複追蹤"
        active = [t for t in tracks if t["active"]]
        if len(active) >= MAX_TRACKS_PER_USER:
            names = "、".join(t["doctor"] for t in active)
            return f"最多同時追蹤 {MAX_TRACKS_PER_USER} 位醫師\n目前追蹤中：{names}\n\n請先取消一個再追蹤新的"
        tracks.append(track)
        return None


def _stop_track(user_id: str, doctor: str = None) -> list[str]:
    """停止追蹤，回傳被停止的醫師名列表"""
    stopped = []
    with _tracking_lock:
        tracks = _tracking_store.get(user_id, [])
        for t in tracks:
            if not t["active"]:
                continue
            if doctor is None or t["doctor"] == doctor:
                t["active"] = False
                stopped.append(t["doctor"])
                _finish_track_log(t, status="cancelled", end_number=t["last_cur_n"])
        _tracking_store[user_id] = [t for t in tracks if t["active"]]
    return stopped


def _push_message(user_id: str, text: str):
    """同步推播 LINE 訊息"""
    try:
        with ApiClient(configuration) as client:
            api = MessagingApi(client)
            api.push_message(PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=text)],
            ))
        stats.record_push()
    except Exception as e:
        logger.error(f"Push message failed: {e}")


def _poll_worker():
    """背景 polling 執行緒"""
    while True:
        time.sleep(POLL_INTERVAL)
        try:
            _poll_all_tracks()
        except Exception as e:
            logger.error(f"Poll error: {e}")


def _poll_all_tracks():
    with _tracking_lock:
        all_users = list(_tracking_store.items())

    for user_id, tracks in all_users:
        for t in tracks:
            if not t["active"]:
                continue
            try:
                _poll_single_track(user_id, t)
            except Exception as e:
                logger.error(f"Poll track error: {e}")


def _poll_single_track(user_id: str, t: dict):
    """檢查單個追蹤任務的號碼變動"""
    results = get_mock_results()
    if not results:
        return

    found = None
    for r in results:
        if r["doctor_name"] == t["doctor"]:
            found = r
            break

    if not found:
        _push_message(user_id, f"{t['doctor']} 可能已休診\n追蹤已自動停止")
        t["active"] = False
        t["push_count"] = t.get("push_count", 0) + 1
        _finish_track_log(t, status="doctor_off", end_number=t["last_cur_n"])
        return

    cur_n = found["current_number"]
    nxt_n = found["next_number"]
    cur_skip = found["is_current_skipped"]

    changed = (
        cur_n != t["last_cur_n"]
        or nxt_n != t["last_nxt_n"]
        or cur_skip != t["last_cur_skip"]
    )
    if not changed:
        return

    # 號碼跳動計數 + 醫師每日統計
    if cur_n != t["last_cur_n"]:
        t["number_changes"] = t.get("number_changes", 0) + 1
        _record_doctor_poll(
            hospital=t["hospital"], dept=t["dept"], doctor=t["doctor"],
            room=t["room"], session_period=t.get("session", ""),
            cur_number=cur_n, is_skipped=cur_skip,
        )

    now = datetime.now(TW_TZ)
    ts = now.strftime("%m/%d %H:%M")

    num_lines = []
    if cur_n > 0:
        num_lines.append(f"   目前號碼:{cur_n}號{'(過號)' if cur_skip else ''}")
        if nxt_n > 0 and nxt_n != cur_n:
            nxt_skip = found["is_next_skipped"]
            num_lines.append(f"      下一號:{nxt_n}號{'(過號)' if nxt_skip else ''}")
    num_info = "\n".join(num_lines) if num_lines else "   尚未開始"

    user_number = t.get("user_number")

    # 過號偵測
    if user_number and cur_n > user_number and not t.get("_skipped_logged"):
        t["_skipped_logged"] = True
        _update_track_log(t.get("log_id", 0), user_skipped=1)

    # 到號判斷
    if user_number and cur_n == user_number and not cur_skip and not t.get("notified"):
        t["notified"] = True
        _push_message(user_id,
            f"輪到您了！ — {t['doctor']}\n{ts}\n{num_info}\n\n"
            f"您的號碼 {user_number}號，已叫號！")
        _push_message(user_id, f"{t['doctor']} 追蹤已自動停止，祝您看診順利！")
        t["active"] = False
        t["push_count"] = t.get("push_count", 0) + 2
        stats.record_track_complete()
        _finish_track_log(t, status="completed", end_number=cur_n)
    else:
        msg = f"號碼更新 — {t['doctor']}\n{ts}\n{num_info}"
        if user_number:
            if cur_n > user_number:
                msg += f"\n\n您是 {user_number}號，已過號，持續追蹤中"
            elif cur_n == user_number:
                msg += f"\n\n您的號碼 {user_number}號，正在叫號"
            else:
                remaining = user_number - cur_n
                msg += f"\n\n您是 {user_number}號，還剩約 {remaining} 號"
        _push_message(user_id, msg)
        t["push_count"] = t.get("push_count", 0) + 1

    t["last_cur_n"] = cur_n
    t["last_nxt_n"] = nxt_n
    t["last_cur_skip"] = cur_skip


# ========== 對話處理（追蹤 + 診號輸入） ==========

_waiting_number: dict[str, dict] = {}  # user_id → track_obj


async def process_message(user_id: str, text: str) -> str:

    # 1. 等待輸入診號
    if user_id in _waiting_number:
        t = _waiting_number[user_id]
        if text in ("跳過", "略過", "skip"):
            del _waiting_number[user_id]
            t["user_number"] = None
            remaining_slots = MAX_TRACKS_PER_USER - len([
                x for x in _get_user_tracks(user_id) if x["active"]
            ])
            hint = f"好的，{t['doctor']} 將持續通知號碼變動直到看診結束"
            if remaining_slots > 0:
                hint += f"\n\n您最多還可以追蹤 {remaining_slots} 位醫師"
            return hint

        try:
            num = int(text)
            if num > 0:
                del _waiting_number[user_id]
                t["user_number"] = num
                _update_track_log(t.get("log_id", 0), user_number=num)
                cur_n = t["last_cur_n"]
                if cur_n >= num:
                    return (
                        f"收到！您是 {num}號（{t['doctor']}）\n"
                        f"目前已叫到 {cur_n}號，您的號碼已過號\n"
                        f"持續追蹤中，叫到您的號時會通知"
                    )
                else:
                    remaining = num - cur_n
                    remaining_slots = MAX_TRACKS_PER_USER - len([
                        x for x in _get_user_tracks(user_id) if x["active"]
                    ])
                    msg = (
                        f"收到！您是 {num}號（{t['doctor']}）\n"
                        f"目前看到 {cur_n}號，還剩約 {remaining} 號\n"
                        f"到號時會自動通知"
                    )
                    if remaining_slots > 0:
                        msg += f"\n\n您最多還可以追蹤 {remaining_slots} 位醫師"
                    return msg
        except ValueError:
            pass

        if "取消" not in text and "停止" not in text and text != "狀態":
            return "請輸入您的掛號號碼（數字），或輸入「跳過」"

    # 2. 取消追蹤
    if "取消全部追蹤" in text or "停止全部追蹤" in text:
        stopped = _stop_track(user_id)
        if stopped:
            return f"已取消全部追蹤：{'、'.join(stopped)}"
        return "目前沒有追蹤中的醫師"

    if "取消追蹤" in text or "停止追蹤" in text:
        active = [t for t in _get_user_tracks(user_id) if t["active"]]
        if not active:
            return "目前沒有追蹤中的醫師"
        if len(active) == 1:
            stopped = _stop_track(user_id, active[0]["doctor"])
            return f"已取消追蹤 {'、'.join(stopped)}"
        rest = text.replace("取消追蹤", "").replace("停止追蹤", "").strip()
        if rest:
            for t in active:
                if rest in t["doctor"] or t["doctor"] in rest:
                    _stop_track(user_id, t["doctor"])
                    return f"已取消追蹤 {t['doctor']}"
        names = "\n".join(f"  {i+1}. {t['doctor']}" for i, t in enumerate(active))
        return f"目前追蹤 {len(active)} 位醫師：\n{names}\n\n請指定醫師名，如「取消追蹤 王大明」\n或輸入「取消全部追蹤」"

    # 3. 追蹤狀態
    if text in ("狀態", "追蹤狀態"):
        active = [t for t in _get_user_tracks(user_id) if t["active"]]
        if not active:
            return "目前沒有追蹤中的醫師"
        parts = []
        for i, t in enumerate(active):
            label = f"【{i+1}】 " if len(active) > 1 else ""
            s = (
                f"{label}{t['hospital']}\n"
                f"{t['dept']} / {t['doctor']}\n"
                f"   目前號碼:{t['last_cur_n']}號"
            )
            if t.get("user_number"):
                un = t["user_number"]
                if t["last_cur_n"] > un:
                    s += f"\n您是 {un}號，已過號，持續追蹤中"
                elif t["last_cur_n"] == un:
                    s += f"\n您的號碼 {un}號，正在叫號"
                else:
                    s += f"\n您是 {un}號，還剩約 {un - t['last_cur_n']} 號"
            parts.append(s)
        return f"追蹤中（{len(active)}/{MAX_TRACKS_PER_USER}）\n\n" + "\n\n".join(parts)

    # 4. 數字穿透到後端
    # （讓選擇科別/醫師的數字正常運作）

    # 5. 呼叫後端 handle_message
    reply = await handle_message(text, user_id)

    # 6. 攔截 __TRACK__ 指令
    if reply and reply.startswith("__TRACK__"):
        parts = reply.replace("__TRACK__", "").split("\t")
        hospital = parts[0] if len(parts) > 0 else ""
        dept = parts[1] if len(parts) > 1 else ""
        doctor = parts[2] if len(parts) > 2 else ""

        results = get_mock_results()
        found = None
        for r in results:
            if r["doctor_name"] == doctor:
                found = r
                break

        if not found:
            return f"找不到 {doctor} 的看診資料\n可能尚未開始看診或已結束"

        actual_dept = dept or found["department"]
        track = {
            "active": True,
            "hospital": hospital,
            "dept": actual_dept,
            "doctor": doctor,
            "room": found["clinic_room"],
            "session": found["session"],
            "last_cur_n": found["current_number"],
            "last_nxt_n": found["next_number"],
            "last_cur_skip": found["is_current_skipped"],
            "user_number": None,
            "notified": False,
            "push_count": 0,
            "number_changes": 0,
            "start_time": datetime.now(TW_TZ),
        }

        err = _add_track(user_id, track)
        if err:
            return err

        # 寫入 MySQL 追蹤記錄
        log_id = _save_track_log(
            line_uid=user_id, hospital=hospital, dept=actual_dept,
            doctor=doctor, room=found["clinic_room"],
            session_period=found["session"], start_number=found["current_number"],
        )
        track["log_id"] = log_id

        stats.record_track_start(user_id, hospital, actual_dept, doctor)
        _waiting_number[user_id] = track

        cur_n = found["current_number"]
        nxt_n = found["next_number"]
        cur_skip = found["is_current_skipped"]
        nxt_skip = found["is_next_skipped"]

        num_lines = []
        if cur_n > 0:
            num_lines.append(f"   目前號碼:{cur_n}號{'(過號)' if cur_skip else ''}")
            if nxt_n > 0 and nxt_n != cur_n:
                num_lines.append(f"      下一號:{nxt_n}號{'(過號)' if nxt_skip else ''}")
        num_info = "\n".join(num_lines) if num_lines else "   尚未開始"

        now = datetime.now(TW_TZ)
        ts = now.strftime("%m/%d %H:%M")
        count = len([t for t in _get_user_tracks(user_id) if t["active"]])
        label = f" ({count}/{MAX_TRACKS_PER_USER})" if count > 1 else ""

        return (
            f"{hospital} 看診進度{label}\n"
            f"{ts}\n"
            f"{found['department']} / {doctor} [{found['clinic_room']}] {found['session']}\n"
            f"{num_info}\n\n"
            f"已開始追蹤 {doctor}\n"
            f"每 {POLL_INTERVAL} 秒自動檢查，號碼變動時通知\n"
            f"輸入「取消追蹤」可停止\n\n"
            f"請問您的掛號號碼是幾號？\n"
            f"（直接輸入數字，或輸入「跳過」）"
        )

    return reply


# ========== FastAPI 路由 ==========

def _get_tracking_logs(limit: int = 50) -> list[dict]:
    """從 MySQL 取最近的追蹤記錄"""
    try:
        conn = _get_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.id, t.line_uid, u.name AS user_name, "
                "t.hospital, t.dept, t.doctor, t.room, t.session_period, "
                "t.user_number, t.start_number, t.end_number, "
                "t.start_time, t.end_time, t.wait_seconds, "
                "t.status, t.push_count, t.number_changes, t.user_skipped "
                "FROM tracking_logs t "
                "LEFT JOIN line_users u ON t.line_uid = u.line_uid "
                "ORDER BY t.id DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        conn.close()

        STATUS_LABELS = {
            "active": "追蹤中", "completed": "到號",
            "cancelled": "取消", "doctor_off": "休診",
        }

        result = []
        for r in rows:
            wait_min = round(r["wait_seconds"] / 60, 1) if r["wait_seconds"] else None
            result.append({
                "id": r["id"],
                "user": r["user_name"] or r["line_uid"][-6:],
                "hospital": r["hospital"],
                "dept": r["dept"],
                "doctor": r["doctor"],
                "room": r["room"],
                "session": r["session_period"],
                "user_number": r["user_number"],
                "start_number": r["start_number"],
                "end_number": r["end_number"],
                "start_time": r["start_time"].strftime("%m/%d %H:%M") if r["start_time"] else "",
                "end_time": r["end_time"].strftime("%m/%d %H:%M") if r["end_time"] else "",
                "wait_min": wait_min,
                "status": STATUS_LABELS.get(r["status"], r["status"]),
                "status_raw": r["status"],
                "pushes": r["push_count"],
                "changes": r["number_changes"],
                "skipped": r["user_skipped"],
            })
        return result
    except Exception as e:
        logger.error(f"查詢追蹤記錄失敗: {e}")
        return []


@asynccontextmanager
async def lifespan(application: FastAPI):
    """啟動時開始 polling 執行緒"""
    poll_thread = threading.Thread(target=_poll_worker, daemon=True)
    poll_thread.start()
    logger.info(f"追蹤 polling 已啟動（每 {POLL_INTERVAL} 秒）")
    yield

app = FastAPI(title="叮咚到號 LINE Bot", lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request):
    """LINE Webhook endpoint"""
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_text = body.decode("utf-8")

    try:
        events = parser.parse(body_text, signature)
    except InvalidSignatureError:
        logger.warning("Invalid LINE signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        try:
            await _handle_event(event)
        except Exception as e:
            logger.error(f"處理事件失敗: {e}", exc_info=True)

    return PlainTextResponse("OK")


@app.get("/health")
async def health():
    """健康檢查端點"""
    active_count = sum(
        len([t for t in tracks if t["active"]])
        for tracks in _tracking_store.values()
    )
    return {
        "status": "ok",
        "active_trackings": active_count,
    }


async def _handle_event(event):
    """處理 LINE 事件"""
    if isinstance(event, FollowEvent):
        user_id = event.source.user_id
        logger.info(f"新用戶加入: {user_id}")
        stats.record_follow()
        # 取得 LINE 暱稱並註冊
        name = _fetch_line_profile(user_id)
        u = user_reg.register(user_id, name)
        reply_text = (
            f"您好！{u['name']}，我是叮咚到號小幫手\n\n"
            "輸入醫院名稱查詢看診進度\n"
            "查到醫師後可追蹤叫號\n\n"
            "試試輸入「測試」體驗功能\n"
            "輸入「醫院」查看支援列表"
        )
        _reply(event.reply_token, reply_text)

    elif isinstance(event, MessageEvent):
        if isinstance(event.message, TextMessageContent):
            user_id = event.source.user_id
            text = event.message.text.strip()

            # 確保用戶已註冊（首次發訊息時註冊）
            if not user_reg.get(user_id):
                name = _fetch_line_profile(user_id)
                user_reg.register(user_id, name)

            logger.info(f"收到訊息: {user_reg.get_display(user_id)} text={text}")

            # 判斷是否為對話訊息（非導航操作）
            is_waiting = user_id in _waiting_number
            show = _is_chat_message(text) and not is_waiting
            stats.record_message(user_id, text, show_in_recent=show)
            reply_text = await process_message(user_id, text)
            _reply(event.reply_token, reply_text)


def _reply(reply_token: str, text: str):
    """回覆 LINE 訊息"""
    if len(text) > 5000:
        text = text[:4990] + "\n...(已截斷)"
    try:
        with ApiClient(configuration) as client:
            api = MessagingApi(client)
            api.reply_message(ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)],
            ))
    except Exception as e:
        logger.error(f"Reply failed: {e}")


# ========== 後台管理 ==========

def _verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="Unauthorized",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials.username


@app.get("/admin/api/stats")
async def admin_api_stats(user: str = Depends(_verify_admin)):
    return JSONResponse(stats.get_snapshot())


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(user: str = Depends(_verify_admin)):
    return ADMIN_HTML


ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>叮咚到號 — 後台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f0f2f5;color:#1a1a2e}
.header{background:linear-gradient(135deg,#0066ff,#5c4dff);color:#fff;padding:20px 32px;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:22px;font-weight:600}
.header .time{font-size:13px;opacity:.8}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;padding:24px 32px}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card .label{font-size:12px;color:#666;margin-bottom:4px}
.card .value{font-size:28px;font-weight:700;color:#0066ff}
.card .sub{font-size:11px;color:#999;margin-top:2px}
.section{padding:0 32px 24px}
.section h2{font-size:16px;font-weight:600;margin-bottom:12px;color:#333}
.chart-box{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:20px}
.bar-chart{display:flex;align-items:flex-end;gap:4px;height:120px}
.bar-chart .bar{flex:1;background:linear-gradient(180deg,#0066ff,#5c4dff);border-radius:4px 4px 0 0;min-width:8px;position:relative;transition:height .3s}
.bar-chart .bar:hover{opacity:.8}
.bar-chart .bar .tip{display:none;position:absolute;top:-24px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:2px 6px;border-radius:4px;font-size:11px;white-space:nowrap}
.bar-chart .bar:hover .tip{display:block}
.bar-labels{display:flex;gap:4px;margin-top:4px}
.bar-labels span{flex:1;text-align:center;font-size:10px;color:#999}
table{width:100%;border-collapse:collapse}
table th{text-align:left;font-size:12px;color:#666;padding:8px 12px;border-bottom:2px solid #eee}
table td{padding:8px 12px;font-size:13px;border-bottom:1px solid #f0f0f0}
table tr:hover{background:#f8f9ff}
.tag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500}
.tag-active{background:#e6f9ed;color:#0a8a3e}
.tag-num{background:#eef0ff;color:#3b4dcc}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:768px){.two-col{grid-template-columns:1fr}.grid{grid-template-columns:repeat(2,1fr);padding:16px}.section{padding:0 16px 16px}.header{padding:16px}}
.refresh-info{font-size:11px;color:#999;text-align:right;padding:8px 32px}
</style>
</head>
<body>
<div class="header">
  <h1>叮咚到號 後台</h1>
  <div class="time" id="headerTime"></div>
</div>

<div class="grid" id="cards"></div>

<div class="section">
  <div class="chart-box">
    <h2>最近 24 小時訊息量</h2>
    <div class="bar-chart" id="hourlyChart"></div>
    <div class="bar-labels" id="hourlyLabels"></div>
  </div>
</div>

<div class="section">
  <div class="two-col">
    <div class="chart-box">
      <h2>活躍追蹤</h2>
      <table id="trackTable">
        <thead><tr><th>用戶</th><th>醫師</th><th>掛號</th><th>目前</th></tr></thead>
        <tbody></tbody>
      </table>
      <p id="noTrack" style="color:#999;font-size:13px;padding:12px;display:none">目前無追蹤中</p>
    </div>
    <div class="chart-box">
      <h2>最近訊息</h2>
      <div style="max-height:320px;overflow-y:auto">
        <table id="msgTable">
          <thead><tr><th>時間</th><th>用戶</th><th>內容</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<div class="section">
  <div class="two-col">
    <div class="chart-box">
      <h2>Top 用戶（追蹤數）</h2>
      <table id="topUserTable">
        <thead><tr><th>#</th><th>用戶</th><th>追蹤數</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <div class="chart-box">
      <h2>熱門追蹤醫師</h2>
      <table id="topQueryTable">
        <thead><tr><th>#</th><th>醫院</th><th>科別</th><th>醫師</th><th>追蹤次數</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</div>

<div class="section">
  <div class="chart-box">
    <h2>用戶列表</h2>
    <div style="max-height:280px;overflow-y:auto">
      <table id="userListTable">
        <thead><tr><th>編號</th><th>LINE UID</th><th>暱稱</th><th>加入時間</th><th>最後活躍</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</div>

<div class="section">
  <div class="chart-box">
    <h2>追蹤記錄</h2>
    <div style="max-height:400px;overflow-y:auto;overflow-x:auto">
      <table id="trackLogTable" style="min-width:900px">
        <thead><tr>
          <th>#</th><th>用戶</th><th>醫院</th><th>科別</th><th>醫師</th>
          <th>掛號</th><th>開始號</th><th>結束號</th>
          <th>開始時間</th><th>結束時間</th><th>等候</th>
          <th>狀態</th><th>推播</th><th>跳號</th><th>過號</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</div>

<div class="section">
  <div class="chart-box">
    <h2>醫師看診統計（近 7 天）</h2>
    <div style="max-height:400px;overflow-y:auto;overflow-x:auto">
      <table id="doctorDailyTable" style="min-width:1000px">
        <thead><tr>
          <th>日期</th><th>醫院</th><th>科別</th><th>醫師</th><th>診間</th><th>午別</th>
          <th>首號</th><th>末號</th><th>開始</th><th>結束</th>
          <th>時長</th><th>叫號數</th><th>均/號</th><th>過號</th><th>過號率</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</div>

<div class="section">
  <div class="chart-box">
    <h2>每日趨勢（近 7 天）</h2>
    <div class="bar-chart" id="dailyChart" style="height:100px"></div>
    <div class="bar-labels" id="dailyLabels"></div>
  </div>
</div>

<div class="refresh-info">每 10 秒自動更新 | 啟動時間 <span id="uptime"></span></div>

<script>
async function fetchStats(){
  try{
    const r=await fetch('/admin/api/stats');
    if(!r.ok)return;
    const d=await r.json();
    render(d);
  }catch(e){console.error(e)}
}

function render(d){
  document.getElementById('headerTime').textContent=d.now;
  document.getElementById('uptime').textContent=d.uptime;

  // cards
  document.getElementById('cards').innerHTML=`
    <div class="card"><div class="label">今日訊息</div><div class="value">${d.today_messages}</div></div>
    <div class="card"><div class="label">今日用戶</div><div class="value">${d.today_users}</div></div>
    <div class="card"><div class="label">追蹤中</div><div class="value">${d.active_trackings}</div></div>
    <div class="card"><div class="label">累計訊息</div><div class="value">${d.total_messages}</div></div>
    <div class="card"><div class="label">註冊用戶</div><div class="value">${d.total_users}</div><div class="sub">加好友 ${d.total_follows}</div></div>
    <div class="card"><div class="label">累計追蹤</div><div class="value">${d.total_tracks_started}</div><div class="sub">完成 ${d.total_tracks_completed}</div></div>
    <div class="card"><div class="label">累計推播</div><div class="value">${d.total_pushes}</div></div>
  `;

  // hourly chart
  const maxH=Math.max(...d.hourly.map(h=>h.count),1);
  document.getElementById('hourlyChart').innerHTML=d.hourly.map(h=>{
    const pct=Math.max(h.count/maxH*100,2);
    return `<div class="bar" style="height:${pct}%"><span class="tip">${h.hour} : ${h.count}</span></div>`;
  }).join('');
  document.getElementById('hourlyLabels').innerHTML=d.hourly.map((h,i)=>
    i%3===0?`<span>${h.hour}</span>`:`<span></span>`
  ).join('');

  // daily chart
  const maxD=Math.max(...d.daily.map(x=>x.messages),1);
  document.getElementById('dailyChart').innerHTML=d.daily.map(x=>{
    const pct=Math.max(x.messages/maxD*100,2);
    return `<div class="bar" style="height:${pct}%"><span class="tip">${x.date} : ${x.messages}msg / ${x.users}users</span></div>`;
  }).join('');
  document.getElementById('dailyLabels').innerHTML=d.daily.map(x=>`<span>${x.date}</span>`).join('');

  // active tracks
  const tb=document.querySelector('#trackTable tbody');
  const nt=document.getElementById('noTrack');
  if(d.active_tracks.length===0){tb.innerHTML='';nt.style.display='block'}
  else{
    nt.style.display='none';
    tb.innerHTML=d.active_tracks.map(t=>`<tr>
      <td>${t.user}</td>
      <td>${t.doctor}</td>
      <td>${t.user_number||'-'}</td>
      <td><span class="tag tag-num">${t.current}號</span></td>
    </tr>`).join('');
  }

  // recent messages
  document.querySelector('#msgTable tbody').innerHTML=d.recent.map(m=>`<tr>
    <td style="white-space:nowrap">${m.time}</td>
    <td>${m.user}</td>
    <td>${m.text}</td>
  </tr>`).join('');

  // top users (by tracking count)
  document.querySelector('#topUserTable tbody').innerHTML=d.top_users.map((u,i)=>`<tr>
    <td>${i+1}</td><td>${u.user}</td><td>${u.tracks}</td>
  </tr>`).join('');

  // top queries (hospital + dept + doctor)
  document.querySelector('#topQueryTable tbody').innerHTML=d.top_queries.map((q,i)=>`<tr>
    <td>${i+1}</td><td style="font-size:12px">${q.hospital}</td><td style="font-size:12px">${q.dept}</td><td>${q.doctor}</td><td>${q.count}</td>
  </tr>`).join('');

  // users list
  document.querySelector('#userListTable tbody').innerHTML=(d.users_list||[]).map(u=>`<tr>
    <td><span class="tag tag-num">#${String(u.no).padStart(3,'0')}</span></td>
    <td style="font-size:11px;color:#888;font-family:monospace">${u.line_uid||''}</td>
    <td>${u.name}</td>
    <td style="font-size:12px;color:#666">${u.first_seen||''}</td>
    <td style="font-size:12px;color:#666">${u.last_active||''}</td>
  </tr>`).join('');

  // tracking logs
  const statusColor={'completed':'#0a8a3e','cancelled':'#cc6600','doctor_off':'#cc3333','active':'#3b4dcc'};
  document.querySelector('#trackLogTable tbody').innerHTML=(d.tracking_logs||[]).map(r=>{
    const sc=statusColor[r.status_raw]||'#666';
    return `<tr>
      <td style="font-size:11px">${r.id}</td>
      <td>${r.user}</td>
      <td style="font-size:12px">${r.hospital}</td>
      <td style="font-size:12px">${r.dept}</td>
      <td>${r.doctor}</td>
      <td>${r.user_number||'-'}</td>
      <td>${r.start_number}</td>
      <td>${r.end_number!=null?r.end_number:'-'}</td>
      <td style="font-size:11px;white-space:nowrap">${r.start_time}</td>
      <td style="font-size:11px;white-space:nowrap">${r.end_time||'-'}</td>
      <td>${r.wait_min!=null?r.wait_min+'m':'-'}</td>
      <td><span class="tag" style="background:${sc}22;color:${sc}">${r.status}</span></td>
      <td>${r.pushes}</td>
      <td>${r.changes}</td>
      <td>${r.skipped?'<span style="color:#cc3333">是</span>':'-'}</td>
    </tr>`}).join('');

  // doctor daily stats
  document.querySelector('#doctorDailyTable tbody').innerHTML=(d.doctor_daily||[]).map(r=>`<tr>
    <td style="white-space:nowrap">${r.date}</td>
    <td style="font-size:12px">${r.hospital}</td>
    <td style="font-size:12px">${r.dept}</td>
    <td>${r.doctor}</td>
    <td>${r.room}</td>
    <td>${r.session}</td>
    <td>${r.first_num}</td>
    <td>${r.last_num}</td>
    <td>${r.first_time}</td>
    <td>${r.last_time}</td>
    <td>${r.duration_min!=null?r.duration_min+'m':'-'}</td>
    <td><span class="tag tag-num">${r.total_calls}</span></td>
    <td>${r.avg_min!=null?r.avg_min+'m':'-'}</td>
    <td>${r.skip_count}</td>
    <td>${r.skip_rate!=null?r.skip_rate+'%':'-'}</td>
  </tr>`).join('');
}

fetchStats();
setInterval(fetchStats,10000);
</script>
</body>
</html>"""


# ========== 本地開發用 ==========

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"LINE Bot 啟動中... http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
