"""叮咚到號 — LINE 模擬對話測試頁面

啟動：python demo_chat.py
瀏覽：http://localhost:5000
"""

import asyncio
import re
import logging
import random
import time
import hashlib
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, request, render_template_string

import json
import httpx
import redis as sync_redis
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
TW_TZ = timezone(timedelta(hours=8))

# Redis 連線（讀取 FastAPI 爬蟲的看診進度快取）
# 本機開發時 Docker Redis 映射到 6380；Docker 內用 6379
_redis_url = os.getenv("REDIS_URL", "redis://localhost:6380/0")
_redis_client = sync_redis.from_url(_redis_url, decode_responses=True)


# ================================================================
# 📊 使用者查詢歷史（SQLite，demo 用；正式用 MySQL user_query_history 表）
# ================================================================

# SQLite 歷史記錄檔，放在程式同目錄；若不可寫則 fallback 到系統暫存
_db_dir = os.path.dirname(os.path.abspath(__file__))
try:
    _test_file = os.path.join(_db_dir, ".write_test")
    with open(_test_file, "w") as f:
        f.write("test")
    os.remove(_test_file)
except OSError:
    import tempfile
    _db_dir = tempfile.gettempdir()
DB_PATH = os.path.join(_db_dir, "demo_history.db")


def _init_history_db():
    """建立 SQLite 歷史記錄表"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_query_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT    NOT NULL DEFAULT 'demo',
            hospital_code TEXT  NOT NULL DEFAULT '',
            department  TEXT    NOT NULL DEFAULT '',
            doctor_name TEXT    NOT NULL DEFAULT '',
            use_count   INTEGER NOT NULL DEFAULT 1,
            last_used_at TEXT   NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_hist_user_hosp
        ON user_query_history(user_id, hospital_code)
    """)
    conn.commit()
    conn.close()


_init_history_db()


def record_history(user_id: str, hospital_code: str, department: str = "", doctor_name: str = ""):
    """記錄一次查詢，若已存在則 use_count + 1"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, use_count FROM user_query_history "
        "WHERE user_id=? AND hospital_code=? AND department=? AND doctor_name=?",
        (user_id, hospital_code, department, doctor_name),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE user_query_history SET use_count=?, last_used_at=datetime('now') WHERE id=?",
            (row[1] + 1, row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO user_query_history (user_id, hospital_code, department, doctor_name) "
            "VALUES (?, ?, ?, ?)",
            (user_id, hospital_code, department, doctor_name),
        )
    conn.commit()
    conn.close()


def _code_to_name(code: str) -> str:
    """hospital_code → 顯示名稱"""
    for alias, (c, name) in HOSPITAL_ALIASES.items():
        if c == code:
            return name
    return code


def _main_menu(user_id: str) -> str:
    """產生主選單，含用戶常用醫院快捷（可輸入數字快速查詢）"""
    top = get_top_hospitals(user_id, limit=3)
    if top:
        recent = "\n".join(f"  {i+1}. {_code_to_name(c)}" for i, c in enumerate(top))
        # 把快捷對應存到 conversation
        _conversations.setdefault(user_id, {})["quick_hospitals"] = top
        return (
            f"📋 輸入醫院名稱查詢看診進度\n"
            f"🏥 輸入「醫院」查看支援列表\n\n"
            f"⭐ 常用醫院（輸入數字快速查詢）：\n{recent}"
        )
    return (
        "📋 輸入醫院名稱查詢看診進度\n"
        "🏥 輸入「醫院」查看支援列表"
    )


def get_top_hospitals(user_id: str, limit: int = 3) -> list[str]:
    """取得使用者最常查詢的醫院 code（依 use_count 降序）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT hospital_code, SUM(use_count) as total FROM user_query_history "
        "WHERE user_id=? AND hospital_code!='' "
        "GROUP BY hospital_code ORDER BY total DESC LIMIT ?",
        (user_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_history_counts(user_id: str, hospital_code: str = "", field: str = "department") -> dict[str, int]:
    """取得某使用者在特定醫院下各科別/醫師的使用次數
    field: "department" 或 "doctor_name"
    回傳: {name: count}
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if field == "department" and hospital_code:
        cur.execute(
            "SELECT department, SUM(use_count) FROM user_query_history "
            "WHERE user_id=? AND hospital_code=? AND department!='' "
            "GROUP BY department ORDER BY SUM(use_count) DESC",
            (user_id, hospital_code),
        )
    elif field == "doctor_name" and hospital_code:
        cur.execute(
            "SELECT doctor_name, SUM(use_count) FROM user_query_history "
            "WHERE user_id=? AND hospital_code=? AND doctor_name!='' "
            "GROUP BY doctor_name ORDER BY SUM(use_count) DESC",
            (user_id, hospital_code),
        )
    elif field == "hospital":
        cur.execute(
            "SELECT hospital_code, SUM(use_count) FROM user_query_history "
            "WHERE user_id=? AND hospital_code!='' "
            "GROUP BY hospital_code ORDER BY SUM(use_count) DESC",
            (user_id,),
        )
    else:
        conn.close()
        return {}
    result = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return result


def sort_by_history(items: list[str], history_counts: dict[str, int]) -> list[str]:
    """依照歷史使用次數排序，常用的排前面，沒用過的保持原順序"""
    in_history = [(name, history_counts[name]) for name in items if name in history_counts]
    in_history.sort(key=lambda x: -x[1])
    not_in_history = [name for name in items if name not in history_counts]
    return [name for name, _ in in_history] + not_in_history


# ================================================================
# 💬 對話狀態管理（demo 用 in-memory，正式用 Redis / DB）
# ================================================================

# user_id → {state, hospital_code, hospital_name, results, depts, ...}
_conversations: dict[str, dict] = {}

DEMO_USER_ID = "demo"


def get_conv(user_id: str = DEMO_USER_ID) -> dict:
    """取得使用者的對話狀態"""
    if user_id not in _conversations:
        _conversations[user_id] = {"state": "idle"}
    return _conversations[user_id]


def reset_conv(user_id: str = DEMO_USER_ID):
    """重置對話狀態"""
    _conversations[user_id] = {"state": "idle"}


def set_after_result(user_id: str, hospital_code: str, hospital_label: str,
                     results: list, dept_name: str = "", doctor_name: str = ""):
    """顯示結果後進入 after_result 狀態，保留醫院上下文"""
    _conversations[user_id] = {
        "state": "after_result",
        "hospital_code": hospital_code,
        "hospital_label": hospital_label,
        "results": results,          # 該醫院的完整結果（重新選科用）
        "last_dept": dept_name,
        "last_doctor": doctor_name,
    }

# ================================================================
# 🔧 測試模式開關：True = 啟用測試醫院, False = 只用真實醫院
# ================================================================
ENABLE_MOCK_HOSPITAL = True


# ========== 測試醫院模擬器 ==========

MOCK_HOSPITAL_NAME = "測試醫院"
MOCK_BRANCH_ID = "mock"

MOCK_DOCTORS = [
    {"dept": "內科",     "doctor": "王大明", "room": "診間101", "session_times": ["1", "2"]},
    {"dept": "內科",     "doctor": "李小華", "room": "診間102", "session_times": ["1", "2"]},
    {"dept": "外科",     "doctor": "張志遠", "room": "診間201", "session_times": ["1", "2", "3"]},
    {"dept": "兒科",     "doctor": "陳美玲", "room": "診間301", "session_times": ["2"]},
    {"dept": "中醫內科", "doctor": "林正宏", "room": "診間401", "session_times": ["1", "2", "3"]},
    {"dept": "中醫內科", "doctor": "黃雅芳", "room": "診間402", "session_times": ["2", "3"]},
    {"dept": "牙科",     "doctor": "吳建民", "room": "診間501", "session_times": ["1", "2"]},
    {"dept": "眼科",     "doctor": "趙文傑", "room": "診間601", "session_times": ["1"]},
]


def _mock_seed(doctor_name: str, hour: int) -> int:
    """每位醫師每小時產生一個固定的隨機種子，確保同一小時內結果一致"""
    s = f"{doctor_name}:{hour}"
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)


def _get_mock_state(doctor_name: str, now: datetime) -> dict:
    """
    計算某位醫師在 now 這個時間點的看診狀態。
    - 每小時從 1 號開始
    - 每 15 秒 ~ 3 分鐘叫一次號（用 seed 決定每次間隔）
    - 約 15% 機率產生過號
    """
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    elapsed = (now - hour_start).total_seconds()

    # 用醫師名+小時做 seed，產生這一小時的叫號時間序列
    seed = _mock_seed(doctor_name, now.hour)
    rng = random.Random(seed)

    current_number = 0
    next_number = 0
    is_current_skipped = False
    is_next_skipped = False

    # 模擬從第 1 號開始的叫號時間表
    t = 0.0  # 累計秒數
    num = 0
    called_at = []  # [(number, call_time, is_skipped)]

    while t < 3600:  # 一小時內
        num += 1
        interval = rng.uniform(15, 180)  # 15 秒 ~ 3 分鐘
        t += interval
        is_skip = rng.random() < 0.15  # 15% 過號
        called_at.append((num, t, is_skip))

    # 找出 elapsed 時間點對應的狀態
    current_number = 0
    is_current_skipped = False
    next_number = 0
    is_next_skipped = False

    for i, (num, call_t, skip) in enumerate(called_at):
        if call_t <= elapsed:
            current_number = num
            is_current_skipped = skip
            # 看下一號
            if i + 1 < len(called_at):
                next_number = called_at[i + 1][0]
                is_next_skipped = called_at[i + 1][2]
            else:
                next_number = 0
                is_next_skipped = False
        else:
            # 還沒叫到這號，它就是「下一號」
            if current_number == 0:
                next_number = num
                is_next_skipped = skip
            break

    return {
        "current_number": current_number,
        "next_number": next_number,
        "is_current_skipped": is_current_skipped,
        "is_next_skipped": is_next_skipped,
    }


def get_mock_results(time_filter: str = None, dept_filter: str = None, doctor_filter: str = None):
    """取得測試醫院的全部/篩選後看診進度"""
    now = datetime.now(TW_TZ)
    hour = now.hour

    # 判斷目前時段
    if hour < 12:
        current_sessions = ["1"]
    elif hour < 17:
        current_sessions = ["1", "2"]
    else:
        current_sessions = ["2", "3"]

    results = []
    for doc in MOCK_DOCTORS:
        # 檢查這位醫師是否在當前時段看診
        active_session = None
        for s in current_sessions:
            if s in doc["session_times"]:
                active_session = s
                break  # 取最早的一個
        if not active_session:
            continue
        if time_filter and active_session != time_filter:
            continue

        state = _get_mock_state(doc["doctor"], now)

        # 都是 0 就跳過（還沒開始）
        if state["current_number"] == 0 and state["next_number"] == 0:
            continue

        session_name = TIME_CODES.get(active_session, "未知")

        item = {
            "hospital_name": MOCK_HOSPITAL_NAME,
            "date": now.strftime("%Y/%m/%d"),
            "session": session_name,
            "department": doc["dept"],
            "doctor_name": doc["doctor"],
            "clinic_room": doc["room"],
            "current_number": state["current_number"],
            "next_number": state["next_number"],
            "is_current_skipped": state["is_current_skipped"],
            "is_next_skipped": state["is_next_skipped"],
            "fetched_at": now.strftime("%H:%M:%S"),
        }

        # 篩選科別/醫師
        if dept_filter and dept_filter not in doc["dept"]:
            continue
        if doctor_filter and doctor_filter not in doc["doctor"]:
            continue

        results.append(item)

    return results


def find_mock_doctor(doctor_filter: str, dept_filter: str = ""):
    """在測試醫院中找到醫師，回傳 dept_code/time_code 格式"""
    now = datetime.now(TW_TZ)
    hour = now.hour
    if hour < 12:
        current_sessions = ["1"]
    elif hour < 17:
        current_sessions = ["1", "2"]
    else:
        current_sessions = ["2", "3"]

    for doc in MOCK_DOCTORS:
        if doctor_filter not in doc["doctor"]:
            continue
        if dept_filter and dept_filter not in doc["dept"]:
            continue
        active_session = None
        for s in current_sessions:
            if s in doc["session_times"]:
                active_session = s
                break
        if not active_session:
            continue

        state = _get_mock_state(doc["doctor"], now)
        return {
            "dept": doc["dept"],
            "doctor": doc["doctor"],
            "room": doc["room"],
            "session": TIME_CODES.get(active_session, "未知"),
            "curN": state["current_number"],
            "nxtN": state["next_number"],
            "curSkip": state["is_current_skipped"],
            "nxtSkip": state["is_next_skipped"],
            "dept_code": "mock_dept",
            "time_code": active_session,
        }
    return None


def poll_mock_doctor(doctor_filter: str, dept_filter: str = ""):
    """輪詢測試醫院的醫師號碼"""
    now = datetime.now(TW_TZ)
    for doc in MOCK_DOCTORS:
        if doctor_filter not in doc["doctor"]:
            continue
        if dept_filter and dept_filter not in doc["dept"]:
            continue
        state = _get_mock_state(doc["doctor"], now)
        return {
            "found": True,
            "curN": state["current_number"],
            "nxtN": state["next_number"],
            "curSkip": state["is_current_skipped"],
            "nxtSkip": state["is_next_skipped"],
        }
    return {"found": False}

# ========== 長庚 Scraper (inline) ==========

DEPT_CODES = {
    "02": "內科", "03": "外科", "04": "牙科", "05": "婦產科",
    "06": "兒童專科", "07": "其它專科", "08": "中醫", "09": "聯合門診", "13": "自費門診",
}
TIME_CODES = {"1": "上午診", "2": "下午診", "3": "夜診"}

BRANCHES = {
    "taipei": ("1", "台北長庚"),
    "linkou": ("3", "林口長庚"),
    "kaohsiung": ("8", "高雄長庚"),
}


async def fetch_changgung(branch_id: str, hospital_name: str):
    """抓取長庚看診進度"""
    now = datetime.now(TW_TZ)
    hour = now.hour
    if hour < 12:
        active_times = ["1"]
    elif hour < 17:
        active_times = ["1", "2"]
    else:
        active_times = ["2", "3"]

    base_url = f"https://register.cgmh.org.tw/Progress/{branch_id}"
    all_results = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for time_code in active_times:
            for dept_code, dept_label in DEPT_CODES.items():
                try:
                    resp = await client.post(
                        base_url,
                        data={"dept": dept_code, "time": time_code},
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Referer": base_url,
                        },
                    )
                    resp.raise_for_status()
                    rows = parse_changgung_html(resp.text, hospital_name, time_code, now)
                    all_results.extend(rows)
                except Exception as e:
                    logger.warning(f"[{hospital_name}] dept={dept_code} time={time_code}: {e}")

    return all_results


def parse_changgung_html(html, hospital_name, time_code, now):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    date_str = now.strftime("%Y/%m/%d")
    session = TIME_CODES.get(time_code, "未知")
    results = []

    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        dept = cells[0].get_text(strip=True)
        location = cells[1].get_text(strip=True)
        doctor = cells[2].get_text(strip=True)
        current_text = cells[3].get_text(strip=True)
        next_text = cells[4].get_text(strip=True)

        if not dept or not doctor:
            continue

        current_number = 0
        is_current_skipped = False
        next_number = 0
        is_next_skipped = False

        cur_nums = re.findall(r"\d+", current_text)
        if cur_nums:
            current_number = int(cur_nums[0])
        if "過號" in current_text:
            is_current_skipped = True

        nxt_nums = re.findall(r"\d+", next_text)
        if nxt_nums:
            next_number = int(nxt_nums[0])
        if "過號" in next_text:
            is_next_skipped = True

        if current_number == 0 and next_number == 0:
            continue

        # 取「／」或「/」前的樓層資訊（去掉地址）
        if "／" in location:
            clinic_room = location.split("／")[0].strip()
        elif "/" in location:
            clinic_room = location.split("/")[0].strip()
        else:
            clinic_room = location

        results.append({
            "hospital_name": hospital_name,
            "date": date_str,
            "session": session,
            "department": dept,
            "doctor_name": doctor,
            "clinic_room": clinic_room,
            "current_number": current_number,
            "next_number": next_number,
            "is_current_skipped": is_current_skipped,
            "is_next_skipped": is_next_skipped,
            "fetched_at": now.strftime("%H:%M:%S"),
        })

    return results


# ========== 新北聯合 API (inline) ==========

NTPC_DATASETS = {
    "banqiao": ("00f8fa51-cedc-4c1d-88b0-58c55f740b79", "新北聯合醫院(板橋)"),
    "sanchong": ("0abdf2d0-3246-4614-b715-d4ed6631eb16", "新北聯合醫院(三重)"),
}


async def fetch_newtaipei(dataset_id: str, hospital_name: str):
    now = datetime.now(TW_TZ)
    url = f"https://data.ntpc.gov.tw/api/datasets/{dataset_id}/json"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params={"size": 200})
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, list):
        return []

    results = []
    opdtime_map = {"1": "上午診", "2": "下午診", "3": "夜診"}

    for rec in data:
        dept = (rec.get("deptname") or "").strip()
        if "_" in dept:
            dept = dept.split("_", 1)[1].strip()
        doctor = (rec.get("doctorname") or "").strip()
        if not dept or not doctor:
            continue

        cur = rec.get("callednumber_seqno", "0")
        current_number = int(cur) if cur and cur.isdigit() else 0
        wait = rec.get("waitcount_person", "0")
        wait_count = int(wait) if wait and wait.isdigit() else 0

        if current_number == 0 and wait_count == 0:
            continue

        results.append({
            "hospital_name": hospital_name,
            "date": now.strftime("%Y/%m/%d"),
            "session": opdtime_map.get(rec.get("opdtimeid", ""), "未知"),
            "department": dept,
            "doctor_name": doctor,
            "clinic_room": (rec.get("roomname") or "").strip(),
            "current_number": current_number,
            "next_number": current_number + 1 if current_number > 0 else 0,
            "is_current_skipped": False,
            "is_next_skipped": False,
            "fetched_at": now.strftime("%H:%M:%S"),
            "wait_count": wait_count,
        })

    return results


# ========== Flask Routes ==========

@app.route("/")
def index():
    return render_template_string(CHAT_HTML)


@app.route("/api/chat", methods=["POST"])
def chat():
    user_msg = request.json.get("message", "").strip()
    user_id = request.json.get("user_id", DEMO_USER_ID)
    if not user_msg:
        return jsonify({"reply": "請輸入訊息 😊"})

    reply = asyncio.run(handle_message(user_msg, user_id))
    return jsonify({"reply": reply})


@app.route("/api/poll", methods=["POST"])
def poll_doctor():
    """追蹤用：查詢特定科別/醫師的即時號碼（前端 setInterval 呼叫）"""
    branch_id = request.json.get("branch_id", "")
    dept_code = request.json.get("dept_code", "")
    time_code = request.json.get("time_code", "")
    doctor_filter = request.json.get("doctor", "")
    dept_filter = request.json.get("dept_filter", "")

    if not branch_id or not doctor_filter:
        return jsonify({"error": "missing params"}), 400

    # 測試醫院
    if ENABLE_MOCK_HOSPITAL and branch_id == MOCK_BRANCH_ID:
        result = poll_mock_doctor(doctor_filter, dept_filter)
        return jsonify(result)

    if not dept_code or not time_code:
        return jsonify({"error": "missing params"}), 400

    try:
        result = asyncio.run(
            poll_changgung_doctor(branch_id, dept_code, time_code, doctor_filter, dept_filter)
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/find_doctor", methods=["POST"])
def find_doctor():
    """追蹤用：全掃找到醫師所在的 dept_code + time_code"""
    branch_id = request.json.get("branch_id", "")
    doctor_filter = request.json.get("doctor", "")
    dept_filter = request.json.get("dept_filter", "")

    if not branch_id or not doctor_filter:
        return jsonify({"error": "missing params"}), 400

    # 測試醫院
    if ENABLE_MOCK_HOSPITAL and branch_id == MOCK_BRANCH_ID:
        result = find_mock_doctor(doctor_filter, dept_filter)
        if result:
            return jsonify(result)
        else:
            return jsonify({"error": "not_found"}), 404

    try:
        result = asyncio.run(
            find_changgung_doctor(branch_id, doctor_filter, dept_filter)
        )
        if result:
            return jsonify(result)
        else:
            return jsonify({"error": "not_found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


async def find_changgung_doctor(branch_id, doctor_filter, dept_filter):
    """全掃找到醫師並回傳 dept_code, time_code 及目前號碼"""
    now = datetime.now(TW_TZ)
    hour = now.hour
    if hour < 12:
        active_times = ["1"]
    elif hour < 17:
        active_times = ["1", "2"]
    else:
        active_times = ["2", "3"]

    base_url = f"https://register.cgmh.org.tw/Progress/{branch_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        for tc in active_times:
            for dc in DEPT_CODES:
                try:
                    resp = await client.post(
                        base_url,
                        data={"dept": dc, "time": tc},
                        headers={
                            "User-Agent": "Mozilla/5.0",
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                    )
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "html.parser")
                    table = soup.find("table")
                    if not table:
                        continue
                    for row in table.find_all("tr")[1:]:
                        cells = row.find_all("td")
                        if len(cells) < 5:
                            continue
                        dept = cells[0].get_text(strip=True)
                        location = cells[1].get_text(strip=True)
                        doctor = cells[2].get_text(strip=True)
                        cur_text = cells[3].get_text(strip=True)
                        nxt_text = cells[4].get_text(strip=True)
                        if doctor_filter not in doctor:
                            continue
                        if dept_filter and dept_filter not in dept:
                            continue
                        cur_nums = re.findall(r"\d+", cur_text)
                        nxt_nums = re.findall(r"\d+", nxt_text)
                        curN = int(cur_nums[0]) if cur_nums else 0
                        nxtN = int(nxt_nums[0]) if nxt_nums else 0
                        room = location
                        if "／" in location:
                            room = location.split("／")[0].strip()
                        elif "/" in location:
                            room = location.split("/")[0].strip()
                        return {
                            "dept": dept,
                            "doctor": doctor,
                            "room": room,
                            "session": TIME_CODES.get(tc, "未知"),
                            "curN": curN,
                            "nxtN": nxtN,
                            "curSkip": "過號" in cur_text,
                            "nxtSkip": "過號" in nxt_text,
                            "dept_code": dc,
                            "time_code": tc,
                        }
                except Exception:
                    pass
    return None


async def poll_changgung_doctor(branch_id, dept_code, time_code, doctor_filter, dept_filter):
    """查詢特定 dept_code + time_code 中的醫師號碼"""
    base_url = f"https://register.cgmh.org.tw/Progress/{branch_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            base_url,
            data={"dept": dept_code, "time": time_code},
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            return {"found": False}
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            dept = cells[0].get_text(strip=True)
            doctor = cells[2].get_text(strip=True)
            if doctor_filter not in doctor:
                continue
            if dept_filter and dept_filter not in dept:
                continue
            cur_text = cells[3].get_text(strip=True)
            nxt_text = cells[4].get_text(strip=True)
            cur_nums = re.findall(r"\d+", cur_text)
            nxt_nums = re.findall(r"\d+", nxt_text)
            return {
                "found": True,
                "curN": int(cur_nums[0]) if cur_nums else 0,
                "nxtN": int(nxt_nums[0]) if nxt_nums else 0,
                "curSkip": "過號" in cur_text,
                "nxtSkip": "過號" in nxt_text,
            }
    return {"found": False}


# ========== 醫院別名對照表 ==========
# 格式：alias → (hospital_code, hospital_full_name)
# hospital_code 若以 "unsupported:" 開頭，表示該醫院尚未有爬蟲，查詢時會顯示「尚未開放」
HOSPITAL_ALIASES = {}

def _build_alias_map():
    """建立別名 → (code, name) 對照表，按別名長度降序排列（長的優先匹配）"""
    # 已支援的醫院 — alias → (hospital_code, display_name)
    # hospital_code 對應 FastAPI 爬蟲 AdapterRegistry 的 code
    supported = {
        # === 台北市 醫學中心 ===
        "台大醫院":     ("ntuh", "台大醫院"),
        "台大":         ("ntuh", "台大醫院"),
        "臺大":         ("ntuh", "台大醫院"),
        "臺大醫院":     ("ntuh", "台大醫院"),
        "三軍總醫院":   ("tsgh", "三軍總醫院"),
        "三總":         ("tsgh", "三軍總醫院"),
        "台北榮總":     ("tpvgh", "台北榮總"),
        "北榮":         ("tpvgh", "台北榮總"),
        "榮總":         ("tpvgh", "台北榮總"),
        "台北長庚":     ("changgung-taipei", "台北長庚"),
        "台北長庚紀念醫院": ("changgung-taipei", "台北長庚"),
        "國泰醫院":     ("cathay", "國泰醫院"),
        "國泰":         ("cathay", "國泰醫院"),
        "馬偕醫院":     ("mackay-taipei", "馬偕醫院(台北)"),
        "馬偕":         ("mackay-taipei", "馬偕醫院(台北)"),
        "馬偕台北":     ("mackay-taipei", "馬偕醫院(台北)"),
        "新光醫院":     ("shinkong", "新光醫院"),
        "新光":         ("shinkong", "新光醫院"),
        "萬芳醫院":     ("wanfang", "萬芳醫院"),
        "萬芳":         ("wanfang", "萬芳醫院"),
        # === 台北市 區域醫院 ===
        "台大兒童醫院": ("ntuh-children", "台大兒童醫院"),
        "台大兒童":     ("ntuh-children", "台大兒童醫院"),
        "臺大兒童":     ("ntuh-children", "台大兒童醫院"),
        "振興醫院":     ("chgh", "振興醫院"),
        "振興":         ("chgh", "振興醫院"),
        # === 新北市 ===
        "亞東醫院":     ("femh", "亞東醫院"),
        "亞東":         ("femh", "亞東醫院"),
        "台北慈濟":     ("tzuchi-taipei", "台北慈濟醫院"),
        "台北慈濟醫院": ("tzuchi-taipei", "台北慈濟醫院"),
        "慈濟新店":     ("tzuchi-xindian", "台北慈濟(新店)"),
        "馬偕淡水":     ("mackay-tamsui", "馬偕醫院(淡水)"),
        "衛福部臺北醫院": ("tph", "衛福部臺北醫院"),
        "臺北醫院":     ("tph", "衛福部臺北醫院"),
        "汐止國泰":     ("cathay-xizhi", "汐止國泰"),
        "土城長庚":     ("changgung-tucheng", "土城長庚"),
        "新北聯合醫院(板橋)": ("newtaipei-banqiao", "新北聯合醫院(板橋)"),
        "板橋":         ("newtaipei-banqiao", "新北聯合醫院(板橋)"),
        "新北板橋":     ("newtaipei-banqiao", "新北聯合醫院(板橋)"),
        "新北聯合醫院(三重)": ("newtaipei-sanchong", "新北聯合醫院(三重)"),
        "三重":         ("newtaipei-sanchong", "新北聯合醫院(三重)"),
        "新北三重":     ("newtaipei-sanchong", "新北聯合醫院(三重)"),
        "輔大醫院":     ("fjuh", "輔大醫院"),
        "輔大":         ("fjuh", "輔大醫院"),
        # === 基隆 ===
        "基隆長庚":     ("changgung-keelung", "基隆長庚"),
        # === 桃園 ===
        "林口長庚":     ("changgung-linkou", "林口長庚"),
        "林口長庚紀念醫院": ("changgung-linkou", "林口長庚"),
        "長庚":         ("changgung-linkou", "林口長庚"),
        "桃園長庚":     ("changgung-taoyuan", "桃園長庚"),
        # === 台中 ===
        "豐原醫院":     ("fyh-mohw", "衛福部豐原醫院"),
        "衛福部豐原醫院": ("fyh-mohw", "衛福部豐原醫院"),
        # === 雲嘉 ===
        "雲林長庚":     ("changgung-yunlin", "雲林長庚"),
        "嘉義長庚":     ("changgung-chiayi", "嘉義長庚"),
        # === 高雄 ===
        "高雄長庚":     ("changgung-kaohsiung", "高雄長庚"),
        "高雄長庚紀念醫院": ("changgung-kaohsiung", "高雄長庚"),
        "鳳山長庚":     ("changgung-fengshan", "鳳山長庚"),
        "高雄聯合醫院": ("kaohsiung-united", "高雄聯合醫院"),
    }

    return supported

HOSPITAL_ALIASES = _build_alias_map()
# 按長度降序排列，避免「台大」先匹配到「台大兒童」的問題
_ALIAS_KEYS_SORTED = sorted(HOSPITAL_ALIASES.keys(), key=len, reverse=True)


def _resolve_hospital(msg: str):
    """從使用者訊息解析出醫院資訊，回傳 (hospital_code, hospital_label, extra_filter) 或 None"""
    msg_lower = msg.lower().strip()

    # 測試醫院
    if ENABLE_MOCK_HOSPITAL and ("測試" in msg or "test" in msg_lower):
        extra = msg.replace("測試醫院", "").replace("測試", "").replace("test", "").strip()
        return MOCK_BRANCH_ID, MOCK_HOSPITAL_NAME, extra

    # 別名匹配（長度優先）
    for alias in _ALIAS_KEYS_SORTED:
        if alias in msg:
            code, label = HOSPITAL_ALIASES[alias]
            extra = msg.replace(alias, "").strip()
            return code, label, extra

    return None


async def _fetch_results(hospital_code: str, hospital_label: str):
    """根據 hospital_code 抓取看診資料

    優先從 Redis 快取讀取（FastAPI 爬蟲每 60 秒更新），
    若 Redis 無資料則回退到直接抓取。
    """
    # 測試醫院
    if ENABLE_MOCK_HOSPITAL and hospital_code == MOCK_BRANCH_ID:
        return get_mock_results()

    # 尚未支援的醫院
    if hospital_code.startswith("unsupported:"):
        return None

    # 從 Redis 讀取 FastAPI 爬蟲快取的看診進度
    results = _fetch_from_redis(hospital_code)
    if results is not None:
        return results

    # 回退：舊的直接抓取邏輯（長庚、新北聯合）
    for key, (branch_id, name) in BRANCHES.items():
        if hospital_code == branch_id:
            return await fetch_changgung(branch_id, name)

    for key, (did, name) in NTPC_DATASETS.items():
        if hospital_code == did:
            return await fetch_newtaipei(did, name)

    return []


def _fetch_from_redis(hospital_code: str) -> list[dict] | None:
    """從 Redis 讀取指定醫院的看診進度快取

    Redis key 格式：progress:{hospital_code}:{clinic_room}
    回傳 list[dict]，無資料回傳 []，Redis 不可用回傳 None（觸發回退）
    """
    try:
        keys = _redis_client.keys(f"progress:{hospital_code}:*")
        if not keys:
            return []

        results = []
        values = _redis_client.mget(keys)
        for val in values:
            if not val:
                continue
            data = json.loads(val)
            results.append({
                "department": data.get("department", ""),
                "doctor_name": data.get("doctor_name", ""),
                "clinic_room": data.get("clinic_room", ""),
                "current_number": data.get("current_number", 0),
                "next_number": data.get("next_number", 0),
                "is_current_skipped": data.get("is_current_skipped", False),
                "is_next_skipped": data.get("is_next_skipped", False),
                "session": data.get("session", ""),
                "date": data.get("date", ""),
            })

        return results
    except Exception as e:
        logger.warning(f"[demo_chat] Redis 讀取失敗: {e}")
        return None  # 回退到直接抓取


def _after_result_menu(hospital_label: str, doctor_name: str = "", dept_name: str = "") -> str:
    """結果顯示後的操作選單"""
    track_label = f"追蹤 {doctor_name}" if doctor_name else "追蹤（選擇醫師）"
    return (
        f"\n"
        f"  1. 🔔 {track_label}\n"
        f"  2. 🔄 查詢別科（{hospital_label}）\n"
        f"  3. 🏠 返回主選單"
    )


def _format_results(results: list[dict], hospital_label: str,
                    filter_text: str = "", time_str: str = "") -> str:
    """把看診結果格式化成回覆訊息"""
    if not time_str:
        time_str = datetime.now(TW_TZ).strftime("%m/%d %H:%M")

    filter_label = ""
    if filter_text:
        filtered = [
            r for r in results
            if filter_text in r["department"] or filter_text in r["doctor_name"]
        ]
        if filtered:
            results = filtered
            filter_label = f"🔎 篩選：{filter_text}\n"

    if not results:
        return (
            f"🏥 {hospital_label}\n"
            f"⏰ 查詢時間：{time_str}\n\n"
            f"目前沒有看診中的診間資料\n"
            f"（可能為非看診時段）"
        )

    # 按科別分組
    by_dept = {}
    for r in results:
        dept = r["department"]
        if dept not in by_dept:
            by_dept[dept] = []
        by_dept[dept].append(r)

    lines = [f"🏥 {hospital_label} 看診進度", f"⏰ {time_str}"]
    if filter_label:
        lines.append(filter_label)
    else:
        lines.append("")

    for dept, items in sorted(by_dept.items()):
        lines.append(f"📌 {dept}")
        for item in items:
            cur_num = item["current_number"]
            nxt_num = item["next_number"]

            if cur_num > 0:
                cur = f"目前{cur_num}號"
                if item["is_current_skipped"]:
                    cur += "(過號)"
                if nxt_num > 0 and nxt_num != cur_num:
                    nxt = f" → 下一位{nxt_num}號"
                    if item["is_next_skipped"]:
                        nxt += "(過號)"
                else:
                    nxt = ""
            elif nxt_num > 0:
                cur = f"下一位{nxt_num}號"
                if item["is_next_skipped"]:
                    cur += "(過號)"
                nxt = ""
            else:
                continue

            room = f" [{item['clinic_room']}]" if item["clinic_room"] else ""
            session = f" {item['session']}" if item.get("session") and item["session"] != "未知" else ""
            lines.append(f"  {item['doctor_name']}{room}{session} {cur}{nxt}")
        lines.append("")

    return "\n".join(lines)


def _load_shortcuts() -> dict[str, str]:
    """從 Redis 讀取快捷指令對照表 {trigger: action}，觸發詞支援逗號分隔多個"""
    try:
        data = _redis_client.get("config:shortcuts")
        if data:
            import json
            items = json.loads(data)
            result = {}
            for s in items:
                if not s.get("trigger") or not s.get("action"):
                    continue
                for t in s["trigger"].split(","):
                    t = t.strip().lower()
                    if t:
                        result[t] = s["action"]
            return result
    except Exception:
        pass
    return {}


async def _handle_pretrack_in_chat(msg: str, user_id: str, conv: dict) -> str:
    """處理預約追蹤的多步驟流程（在 demo_chat 內完成，不依賴 webhook）"""
    state = conv.get("state", "")

    if msg in ("取消", "返回", "0"):
        reset_conv(user_id)
        return "已取消\n\n" + _main_menu(user_id)

    # Step 1: 選醫院
    if state == "pretrack_hospital":
        quick = conv.get("quick_hospitals", [])
        hospital_code, hospital_name = None, None
        if msg in ("1", "2", "3") and quick:
            idx = int(msg) - 1
            if idx < len(quick):
                hospital_code = quick[idx]
                hospital_name = _code_to_name(hospital_code)
        if not hospital_code:
            resolved = _resolve_hospital(msg)
            if resolved:
                hospital_code, hospital_name = resolved[0], resolved[1]
        if hospital_code:
            _conversations[user_id] = {
                "state": "pretrack_session",
                "pretrack_hospital": hospital_name,
                "pretrack_hospital_code": hospital_code,
            }
            return (
                f"🏥 {hospital_name}\n\n"
                f"請選擇看診時段：\n\n"
                f"  1. 上午診\n"
                f"  2. 下午診\n"
                f"  3. 夜診"
            )
        return "找不到此醫院，請重新輸入\n輸入「取消」返回"

    # Step 2: 選時段
    if state == "pretrack_session":
        session_map = {"1": "上午診", "2": "下午診", "3": "夜診",
                       "上午": "上午診", "下午": "下午診", "夜": "夜診"}
        session_time = session_map.get(msg.strip(), None)
        if not session_time:
            return "請輸入 1、2 或 3：\n\n  1. 上午診\n  2. 下午診\n  3. 夜診"
        conv["pretrack_session"] = session_time
        conv["state"] = "pretrack_dept"
        return f"⏰ {session_time}\n\n請輸入科別名稱：\n（例如：骨科、心臟內科）"

    # Step 3: 輸入科別
    if state == "pretrack_dept":
        conv["pretrack_dept"] = msg.strip()
        conv["state"] = "pretrack_doctor"
        return f"📌 {conv['pretrack_dept']}\n\n請輸入醫師姓名："

    # Step 4: 輸入醫師
    if state == "pretrack_doctor":
        conv["pretrack_doctor"] = msg.strip()
        conv["state"] = "pretrack_number"
        return f"👨‍⚕️ {conv['pretrack_doctor']}\n\n請輸入您的掛號號碼："

    # Step 5: 輸入號碼
    if state == "pretrack_number":
        numbers = re.findall(r"\d+", msg)
        if not numbers:
            return "請輸入數字號碼"
        conv["pretrack_number"] = int(numbers[0])
        conv["state"] = "pretrack_mode"
        return (
            f"您是第 {conv['pretrack_number']} 號\n\n"
            f"請選擇提醒模式：\n\n"
            f"  1. 📢 每號提醒\n"
            f"  2. 🔔 輕量提醒（推薦）\n"
            f"  3. 🔕 最後提醒"
        )

    # Step 6: 選模式 → 建立追蹤
    if state == "pretrack_mode":
        mode_map = {"1": "normal", "2": "light", "3": "final"}
        mode = mode_map.get(msg.strip(), None)
        if not mode:
            return "請輸入 1、2 或 3"

        hospital = conv["pretrack_hospital"]
        hospital_code = conv["pretrack_hospital_code"]
        session_time = conv.get("pretrack_session", "")
        dept = conv.get("pretrack_dept", "")
        doctor = conv.get("pretrack_doctor", "")
        clinic_room = conv.get("pretrack_room", None)
        user_number = conv["pretrack_number"]
        reset_conv(user_id)

        from app.services.tracker import TrackerService
        from app.scrapers.registry import AdapterRegistry
        tracker = TrackerService()
        await tracker.create_task(
            line_user_id=user_id,
            hospital_code=hospital_code,
            department=dept,
            doctor_name=doctor or None,
            clinic_room=clinic_room,
            user_number=user_number,
            notify_mode=mode,
            session_time=session_time or None,
        )

        adapter = AdapterRegistry.get(hospital_code)
        hosp_name = adapter.hospital_name if adapter else hospital
        mode_labels = {"normal": "📢 每號提醒", "light": "🔔 輕量提醒", "final": "🔕 最後提醒"}

        detail = f"{dept} — {doctor}" if dept and doctor else (clinic_room or dept or doctor or "")
        session_line = f"⏰ {session_time}\n" if session_time else ""
        return (
            f"✅ 追蹤成功！\n\n"
            f"🏥 {hosp_name}\n"
            f"{session_line}"
            f"📌 {detail}\n"
            f"🎫 第 {user_number} 號\n"
            f"模式：{mode_labels.get(mode, '🔔')}\n\n"
            f"系統會自動監控，快到號時通知您"
        )

    return "操作有誤，請重新輸入\n輸入「取消」返回"


async def handle_message(msg: str, user_id: str = DEMO_USER_ID) -> str:
    now = datetime.now(TW_TZ)
    time_str = now.strftime("%m/%d %H:%M")
    msg = msg.strip()
    msg_lower = msg.lower()

    # 快捷指令轉換（從後台設定的 shortcuts）
    shortcut_map = _load_shortcuts()
    if msg_lower in shortcut_map:
        msg = shortcut_map[msg_lower]
        msg_lower = msg.lower()

    conv = get_conv(user_id)

    # ====== 全域指令（任何狀態下都能觸發）======

    # 預約追蹤（進入 webhook 的 pretrack 流程）
    if msg in ("預約追蹤", "預約", "預先追蹤"):
        # 需要先選醫院 → 存到 conv，由 webhook pretrack flow 接手
        top = get_top_hospitals(user_id, limit=3)
        lines = ["📅 預約追蹤 — 提前設定，看診時自動通知\n"]
        if top:
            lines.append("常用醫院：")
            for i, code in enumerate(top, 1):
                lines.append(f"  {i}. {_code_to_name(code)}")
            lines.append("")
        lines.append("請輸入醫院名稱：")
        _conversations[user_id] = {"state": "pretrack_hospital", "quick_hospitals": top}
        return "\n".join(lines)

    # 說明 / 幫助
    if msg in ("說明", "幫助", "help", "使用說明", "功能介紹"):
        reset_conv(user_id)
        return (
            "📖 叮咚到號 — 使用說明\n"
            "────────────\n"
            "🔍 查詢進度：直接輸入醫院名\n"
            "   例如：萬芳、台大、三總\n\n"
            "🔔 追蹤掛號：查詢後選「追蹤」\n"
            "   系統會在快到號時通知您\n\n"
            "📅 預約追蹤：提前設定看診追蹤\n"
            "   輸入「預約」即可開始\n\n"
            "📌 快捷指令：\n"
            "   @ — 回主選單\n"
            "   / — 返回上一層\n"
            "   00 — 醫院列表\n"
            "   p — 預約追蹤\n"
            "   t — 查看追蹤狀態\n"
            "   c — 取消追蹤\n"
            "   h — 顯示此說明\n\n"
            "🏥 輸入「醫院」查看完整支援列表"
        )

    # 我的追蹤 / 追蹤狀態
    if msg in ("我的追蹤", "追蹤列表", "追蹤狀態"):
        # 讀取 Redis 裡的追蹤資料（透過 LineBotService）
        from app.services.line_bot import LineBotService
        svc = LineBotService()
        return await svc._handle_list_tracks(user_id)

    # 取消追蹤
    if msg in ("取消追蹤", "停止追蹤"):
        from app.services.line_bot import LineBotService
        svc = LineBotService()
        return await svc._handle_cancel_track(user_id, msg)

    # 預約追蹤 — 多步驟流程
    if conv.get("state", "").startswith("pretrack_"):
        return await _handle_pretrack_in_chat(msg, user_id, conv)

    # 「重置」/「取消」— 回到初始狀態
    if msg in ("重置", "取消", "返回"):
        reset_conv(user_id)
        return "✅ 已返回主選單\n\n" + _main_menu(user_id)

    # 常用醫院快捷數字（主選單的 1/2/3）
    _quick_resolved = None
    if conv["state"] == "idle" and msg in ("1", "2", "3"):
        quick = conv.get("quick_hospitals", [])
        idx = int(msg) - 1
        if idx < len(quick):
            _quick_resolved = (quick[idx], _code_to_name(quick[idx]), "")

    # 查詢醫院列表（快捷數字不觸發）
    is_mock_query = ENABLE_MOCK_HOSPITAL and ("測試" in msg or "test" in msg_lower)
    if not _quick_resolved and not is_mock_query and msg in ("醫院", "列表", "有哪些", "支援"):
        reset_conv(user_id)
        mock_section = ""
        if ENABLE_MOCK_HOSPITAL:
            mock_section = (
                "\n【🧪 測試醫院】\n"
                "• 測試醫院（輸入「測試」查詢）\n"
                "  醫師：王大明、李小華、張志遠、陳美玲\n"
                "  　　　林正宏、黃雅芳、吳建民、趙文傑\n"
                "  ⏱ 每小時重新計號，15秒~3分鐘跳號\n"
            )
        return (
            "🏥 目前支援查詢的醫院：\n\n"
            "【台北市】\n"
            "• 台大醫院、台大兒童醫院\n"
            "• 三軍總醫院（三總）\n"
            "• 台北榮總\n"
            "• 台北長庚\n"
            "• 國泰醫院\n"
            "• 馬偕醫院（台北）\n"
            "• 新光醫院\n"
            "• 萬芳醫院\n"
            "• 振興醫院\n\n"
            "【新北市】\n"
            "• 亞東醫院\n"
            "• 台北慈濟醫院\n"
            "• 馬偕醫院（淡水）\n"
            "• 衛福部臺北醫院\n"
            "• 汐止國泰\n"
            "• 土城長庚\n"
            "• 新北聯合醫院（板橋/三重）\n"
            "• 輔大醫院\n\n"
            "【基隆/桃園】\n"
            "• 基隆長庚、林口長庚、桃園長庚\n\n"
            "【台中】\n"
            "• 衛福部豐原醫院\n\n"
            "【雲嘉/高雄】\n"
            "• 雲林長庚、嘉義長庚\n"
            "• 高雄長庚、鳳山長庚\n"
            "• 高雄聯合醫院"
            f"{mock_section}\n\n"
            "💡 輸入醫院名稱即可查詢看診進度\n"
            "💡 可加科別篩選，如：台大 骨科"
        )

    # ====== 有對話狀態時，處理編號選擇 ======

    if conv["state"] == "after_result":
        # 使用者剛看完結果，選擇下一步
        if msg in ("1", "追蹤"):
            doctor = conv.get("last_doctor", "")
            if doctor:
                # 直接觸發追蹤指令，前端會攔截 "追蹤" 指令
                hosp = conv["hospital_label"]
                dept = conv.get("last_dept", "")
                reset_conv(user_id)
                # 回傳追蹤指令格式讓前端處理
                return f"__TRACK__{hosp}\t{dept}\t{doctor}"
            else:
                # 多位醫師時，引導選醫師（只列該科的醫師）
                results = conv.get("results", [])
                dept = conv.get("last_dept", "")
                dept_results = [r for r in results if r["department"] == dept] if dept else results
                doctors = list(dict.fromkeys(r["doctor_name"] for r in dept_results))
                if len(doctors) > 1:
                    hosp_label = conv["hospital_label"]
                    conv["state"] = "choose_doctor"
                    conv["doctor_list"] = doctors
                    conv["chosen_dept"] = dept
                    conv["dept_filtered"] = dept_results
                    lines = [f"🏥 {hosp_label} — {dept}", f"請選擇要追蹤的醫師：\n"]
                    for i, d in enumerate(doctors, 1):
                        lines.append(f"  {i}. {d}")
                    lines.append("\n💡 輸入數字或醫師名")
                    return "\n".join(lines)
                return "❌ 無法追蹤，請重新查詢"

        if msg in ("2", "別科", "查詢別科", "換科"):
            # 重新顯示科別列表（用已快取的 results）
            results = conv.get("results", [])
            hospital_code = conv["hospital_code"]
            hospital_label = conv["hospital_label"]

            dept_set = list(dict.fromkeys(r["department"] for r in results))
            if len(dept_set) <= 1:
                reset_conv(user_id)
                return f"🏥 {hospital_label} 目前只有 1 個科別，沒有別科可選\n\n💡 輸入其他醫院名稱查詢"

            dept_history = get_history_counts(user_id, hospital_code, field="department")
            dept_sorted = sort_by_history(dept_set, dept_history)

            conv["state"] = "choose_dept"
            conv["dept_list"] = dept_sorted

            lines = [
                f"🏥 {hospital_label}",
                f"⏰ {time_str}　共 {len(results)} 個診間、{len(dept_sorted)} 個科別\n",
                "請問您想看哪科？\n",
            ]
            for i, dept in enumerate(dept_sorted, 1):
                count = len([r for r in results if r["department"] == dept])
                mark = " ⭐" if dept in dept_history else ""
                lines.append(f"  {i}. {dept}（{count}位醫師）{mark}")
            lines.append(f"\n💡 輸入數字或科別名稱")
            lines.append(f"💡 輸入 @ 返回主選單")
            return "\n".join(lines)

        if msg in ("3", "返回", "主選單"):
            reset_conv(user_id)
            return "✅ 已返回主選單\n\n" + _main_menu(user_id)

        # 不是 1/2/3，嘗試當新查詢處理
        if _resolve_hospital(msg):
            reset_conv(user_id)
            return await handle_message(msg, user_id)

        doctor = conv.get("last_doctor", "")
        hosp = conv.get("hospital_label", "")
        track_label = f"追蹤 {doctor}" if doctor else "追蹤"
        return (
            f"請輸入 1～3：\n\n"
            f"  1. 🔔 {track_label}\n"
            f"  2. 🔄 查詢別科（{hosp}）\n"
            f"  3. 🏠 返回主選單"
        )

    if conv["state"] == "choose_session":
        # 使用者正在選時段
        results = conv.get("results", [])
        all_sessions = list(dict.fromkeys(r.get("session", "") for r in results if r.get("session")))

        if msg in ("@", "主選單"):
            reset_conv(user_id)
            return "✅ 已返回主選單\n\n" + _main_menu(user_id)

        chosen_session = None
        if msg.isdigit():
            idx = int(msg) - 1
            if idx == len(all_sessions):
                # 「全部時段」
                chosen_session = "__all__"
            elif 0 <= idx < len(all_sessions):
                chosen_session = all_sessions[idx]

        # 也支援文字匹配
        if not chosen_session:
            for s in all_sessions:
                if msg in s:
                    chosen_session = s
                    break

        if not chosen_session:
            return "請輸入數字選擇時段\n💡 輸入 @ 返回主選單"

        # 篩選結果
        if chosen_session != "__all__":
            results = [r for r in results if r.get("session") == chosen_session]
            conv["results"] = results

        # 接下來走正常的科別選擇流程
        hospital_code = conv["hospital_code"]
        hospital_label = conv["hospital_label"]
        dept_set = list(dict.fromkeys(r["department"] for r in results))
        record_history(user_id, hospital_code)

        if len(dept_set) <= 1:
            last_doc = ""
            docs_in = set(r["doctor_name"] for r in results)
            if len(docs_in) == 1:
                last_doc = list(docs_in)[0]
            result_text = _format_results(results, hospital_label, time_str=time_str)
            set_after_result(user_id, hospital_code, hospital_label, results,
                             dept_name=dept_set[0] if dept_set else "", doctor_name=last_doc)
            return result_text + _after_result_menu(hospital_label, last_doc, dept_set[0] if dept_set else "")

        dept_history = get_history_counts(user_id, hospital_code, field="department")
        dept_sorted = sort_by_history(dept_set, dept_history)
        conv["state"] = "choose_dept"
        conv["dept_list"] = dept_sorted

        session_label = f"（{chosen_session}）" if chosen_session != "__all__" else ""
        lines = [
            f"🏥 {hospital_label}{session_label}",
            f"⏰ {time_str}　共 {len(results)} 個診間、{len(dept_sorted)} 個科別\n",
            "請問您想看哪科？\n",
        ]
        for i, dept in enumerate(dept_sorted, 1):
            count = len([r for r in results if r["department"] == dept])
            mark = " ⭐" if dept in dept_history else ""
            lines.append(f"  {i}. {dept}（{count}位醫師）{mark}")
        lines.append(f"\n💡 輸入數字或科別名稱")
        lines.append(f"💡 輸入 @ 返回主選單")
        return "\n".join(lines)

    if conv["state"] == "choose_dept":
        # 使用者正在選科別
        dept_list = conv["dept_list"]
        chosen_dept = None

        # 9 = 返回主選單
        if msg in ("@", "主選單"):
            reset_conv(user_id)
            return "✅ 已返回主選單\n\n" + _main_menu(user_id)

        # 數字選擇
        if msg.isdigit():
            n = int(msg)
            if 1 <= n <= len(dept_list):
                chosen_dept = dept_list[n - 1]
            else:
                return f"❌ 請輸入 1～{len(dept_list)} 的數字，或直接輸入科別名稱\n💡 輸入 @ 返回主選單"

        # 文字匹配（優先完全匹配，再找最長子字串匹配）
        if not chosen_dept:
            for d in dept_list:
                if msg == d:
                    chosen_dept = d
                    break
            if not chosen_dept:
                candidates = [(d, len(d)) for d in dept_list if msg in d or d in msg]
                if candidates:
                    candidates.sort(key=lambda x: -x[1])
                    chosen_dept = candidates[0][0]

        if not chosen_dept:
            # 嘗試是否為新的醫院查詢
            if _resolve_hospital(msg):
                reset_conv(user_id)
                return await handle_message(msg, user_id)  # 遞迴重新處理
            return f"❌ 找不到「{msg}」\n請輸入數字編號或科別名稱\n💡 輸入 @ 返回主選單"

        # 選到科別了 → 篩選出該科的醫師
        filtered = [r for r in conv["results"] if r["department"] == chosen_dept]
        doctors = list(dict.fromkeys(r["doctor_name"] for r in filtered))  # 去重保序

        # 記錄科別歷史
        record_history(user_id, conv["hospital_code"], department=chosen_dept)

        if len(doctors) == 1:
            # 只有一位醫師，直接顯示結果
            record_history(user_id, conv["hospital_code"], department=chosen_dept, doctor_name=doctors[0])
            result_text = _format_results(filtered, conv["hospital_label"], time_str=time_str)
            set_after_result(user_id, conv["hospital_code"], conv["hospital_label"],
                             conv["results"], dept_name=chosen_dept, doctor_name=doctors[0])
            return result_text + _after_result_menu(conv["hospital_label"], doctors[0], chosen_dept)

        # 多位醫師 → 進入選醫師
        # 依歷史排序
        doc_history = get_history_counts(user_id, conv["hospital_code"], field="doctor_name")
        doctors = sort_by_history(doctors, doc_history)

        conv["state"] = "choose_doctor"
        conv["chosen_dept"] = chosen_dept
        conv["doctor_list"] = doctors
        conv["dept_filtered"] = filtered

        lines = [f"🏥 {conv['hospital_label']} — {chosen_dept}", f"共 {len(doctors)} 位醫師，請選擇：\n"]
        for i, doc in enumerate(doctors, 1):
            mark = " ⭐" if doc in doc_history else ""
            lines.append(f"  {i}. {doc}{mark}")
        lines.append(f"\n💡 輸入數字或醫師名")
        lines.append(f"💡 輸入 / 返回科別")
        lines.append(f"💡 輸入 @ 返回主選單")
        return "\n".join(lines)

    if conv["state"] == "choose_doctor":
        # 使用者正在選醫師
        doctor_list = conv["doctor_list"]
        chosen_doctor = None

        # * = 返回科別列表
        if msg in ("/", "返回", "上一層"):
            # 重新顯示科別列表
            results = conv.get("results", [])
            dept_set = list(dict.fromkeys(r["department"] for r in results))
            dept_history = get_history_counts(user_id, conv["hospital_code"], field="department")
            dept_sorted = sort_by_history(dept_set, dept_history)
            conv["state"] = "choose_dept"
            conv["dept_list"] = dept_sorted
            lines = [
                f"🏥 {conv['hospital_label']}",
                f"⏰ {time_str}　共 {len(results)} 個診間、{len(dept_sorted)} 個科別\n",
                "請問您想看哪科？\n",
            ]
            for i, dept in enumerate(dept_sorted, 1):
                count = len([r for r in results if r["department"] == dept])
                mark = " ⭐" if dept in dept_history else ""
                lines.append(f"  {i}. {dept}（{count}位醫師）{mark}")
            lines.append(f"\n💡 輸入數字或科別名稱")
            lines.append(f"💡 輸入 @ 返回主選單")
            return "\n".join(lines)

        # 9 = 返回主選單
        if msg in ("@", "主選單"):
            reset_conv(user_id)
            return "✅ 已返回主選單\n\n" + _main_menu(user_id)

        if msg.isdigit():
            idx = int(msg) - 1
            if 0 <= idx < len(doctor_list):
                chosen_doctor = doctor_list[idx]
            else:
                return f"❌ 請輸入 1～{len(doctor_list)} 的數字，或直接輸入醫師名\n💡 輸入 / 返回科別\n💡 輸入 @ 返回主選單"

        if not chosen_doctor:
            for d in doctor_list:
                if msg == d:
                    chosen_doctor = d
                    break
            if not chosen_doctor:
                candidates = [(d, len(d)) for d in doctor_list if msg in d or d in msg]
                if candidates:
                    candidates.sort(key=lambda x: -x[1])
                    chosen_doctor = candidates[0][0]

        if not chosen_doctor:
            # 嘗試是否為新的醫院查詢
            if _resolve_hospital(msg):
                reset_conv(user_id)
                return await handle_message(msg, user_id)
            return f"❌ 找不到「{msg}」\n請輸入數字編號或醫師名\n💡 輸入 / 返回科別\n💡 輸入 @ 返回主選單"

        # 找到醫師了 → 顯示結果
        filtered = [r for r in conv["dept_filtered"] if r["doctor_name"] == chosen_doctor]
        record_history(user_id, conv["hospital_code"], department=conv["chosen_dept"], doctor_name=chosen_doctor)
        result_text = _format_results(filtered, conv["hospital_label"], time_str=time_str)
        set_after_result(user_id, conv["hospital_code"], conv["hospital_label"],
                         conv["results"], dept_name=conv["chosen_dept"], doctor_name=chosen_doctor)
        return result_text + _after_result_menu(conv["hospital_label"], chosen_doctor, conv["chosen_dept"])

    # ====== idle 狀態：解析醫院名稱 ======

    resolved = _quick_resolved or _resolve_hospital(msg)

    if not resolved:
        return "👋 您好！我是叮咚到號小幫手\n\n" + _main_menu(user_id)

    hospital_code, hospital_label, extra_filter = resolved

    # 快速追蹤：「萬芳 下午 303診 8號」或「萬芳 303診 8」（不需要查資料）
    if extra_filter and re.search(r"\d+診", extra_filter) and re.search(r"\d+號?$", extra_filter.rstrip("號")):
        m_room = re.search(r"(\d+診)", extra_filter)
        m_num = re.search(r"(\d+)\s*號?\s*$", extra_filter)
        if m_room and m_num:
            clinic_room = m_room.group(1)
            user_number = int(m_num.group(1))
            # 解析時段
            quick_session = None
            for kw, val in [("上午", "上午診"), ("下午", "下午診"), ("夜", "夜診")]:
                if kw in extra_filter:
                    quick_session = val
                    break
            # 進入追蹤流程：問號碼已有，直接問模式
            _conversations[user_id] = {
                "state": "pretrack_mode",
                "pretrack_hospital": hospital_label,
                "pretrack_hospital_code": hospital_code,
                "pretrack_session": quick_session or "",
                "pretrack_dept": "",
                "pretrack_doctor": "",
                "pretrack_number": user_number,
                "pretrack_room": clinic_room,
            }
            session_hint = f"⏰ {quick_session}\n" if quick_session else ""
            return (
                f"🔔 快速追蹤\n"
                f"🏥 {hospital_label} {clinic_room}\n"
                f"{session_hint}"
                f"🎫 第 {user_number} 號\n\n"
                f"請選擇提醒模式：\n\n"
                f"  1. 📢 每號提醒\n"
                f"  2. 🔔 輕量提醒（推薦）\n"
                f"  3. 🔕 最後提醒"
            )

    # 抓取看診資料
    try:
        results = await _fetch_results(hospital_code, hospital_label)
    except Exception as e:
        return f"❌ {hospital_label} 查詢失敗：{e}"

    if results is None:
        return (
            f"🏥 {hospital_label}\n\n"
            f"此醫院尚未開放查詢\n"
            f"目前支援：台大、三總、北榮、長庚、國泰、馬偕、新光、萬芳、振興、亞東等 29 家\n\n"
            f"更多醫院陸續開放中"
        )

    if not results:
        record_history(user_id, hospital_code)
        return (
            f"🏥 {hospital_label}\n"
            f"⏰ {time_str}\n\n"
            f"目前醫師休息中，請在看診時間再查詢"
        )

    # 解析 extra_filter 中的時段關鍵字
    session_filter = None
    if extra_filter:
        for kw, val in [("上午", "上午診"), ("早", "上午診"), ("下午", "下午診"), ("午診", "下午診"), ("夜", "夜診")]:
            if kw in extra_filter:
                session_filter = val
                extra_filter = extra_filter.replace(kw, "").replace("診", "").strip()
                break

    # 時段篩選
    if session_filter:
        results = [r for r in results if r.get("session") == session_filter]
        if not results:
            return f"🏥 {hospital_label}\n⏰ {time_str}\n\n{session_filter}目前沒有看診中的診間"

    # 如果使用者已附帶篩選關鍵字（如「萬芳 骨科」），直接篩選並顯示
    if extra_filter:
        filtered = [
            r for r in results
            if extra_filter in r["department"] or extra_filter in r["doctor_name"]
        ]
        if filtered:
            # 記錄歷史
            record_history(user_id, hospital_code)
            depts_found = set(r["department"] for r in filtered)
            docs_found = set(r["doctor_name"] for r in filtered)
            for d in depts_found:
                record_history(user_id, hospital_code, department=d)
            for doc in docs_found:
                dept_of_doc = next((r["department"] for r in filtered if r["doctor_name"] == doc), "")
                record_history(user_id, hospital_code, department=dept_of_doc, doctor_name=doc)
            # 判斷結果中有幾位醫師（用於 menu 顯示）
            last_doc = ""
            last_dept = ""
            if len(docs_found) == 1:
                last_doc = list(docs_found)[0]
            if len(depts_found) == 1:
                last_dept = list(depts_found)[0]
            result_text = _format_results(filtered, hospital_label, time_str=time_str)
            set_after_result(user_id, hospital_code, hospital_label, results,
                             dept_name=last_dept, doctor_name=last_doc)
            return result_text + _after_result_menu(hospital_label, last_doc, last_dept)
        # 篩選無結果，忽略 extra_filter，進入選科流程

    # 檢查是否有多個時段 → 讓用戶先選
    all_sessions = list(dict.fromkeys(r.get("session", "") for r in results if r.get("session")))
    if len(all_sessions) > 1 and not session_filter:
        session_labels = {"上午診": "🌅 上午診", "下午診": "☀️ 下午診", "夜診": "🌙 夜診"}
        conv["state"] = "choose_session"
        conv["hospital_code"] = hospital_code
        conv["hospital_label"] = hospital_label
        conv["results"] = results
        lines = [
            f"🏥 {hospital_label}",
            f"⏰ {time_str}　共 {len(results)} 個診間\n",
            "請選擇時段：\n",
        ]
        for i, s in enumerate(all_sessions, 1):
            count = len([r for r in results if r.get("session") == s])
            lines.append(f"  {i}. {session_labels.get(s, s)}（{count}個診間）")
        lines.append(f"  {len(all_sessions)+1}. 全部時段")
        lines.append(f"\n💡 輸入數字選擇")
        return "\n".join(lines)

    # 提取所有科別
    dept_set = list(dict.fromkeys(r["department"] for r in results))

    # 記錄醫院使用
    record_history(user_id, hospital_code)

    # 若只有 1 個科別，跳過選科，直接顯示
    if len(dept_set) <= 1:
        last_doc = ""
        docs_in = set(r["doctor_name"] for r in results)
        if len(docs_in) == 1:
            last_doc = list(docs_in)[0]
        result_text = _format_results(results, hospital_label, time_str=time_str)
        set_after_result(user_id, hospital_code, hospital_label, results,
                         dept_name=dept_set[0] if dept_set else "", doctor_name=last_doc)
        return result_text + _after_result_menu(hospital_label, last_doc, dept_set[0] if dept_set else "")

    # 依歷史排序科別
    dept_history = get_history_counts(user_id, hospital_code, field="department")
    dept_sorted = sort_by_history(dept_set, dept_history)

    # 存入對話狀態
    conv["state"] = "choose_dept"
    conv["hospital_code"] = hospital_code
    conv["hospital_label"] = hospital_label
    conv["results"] = results
    conv["dept_list"] = dept_sorted

    lines = [
        f"🏥 {hospital_label}",
        f"⏰ {time_str}　共 {len(results)} 個診間、{len(dept_sorted)} 個科別\n",
        "請問您想看哪科？\n",
    ]
    for i, dept in enumerate(dept_sorted, 1):
        count = len([r for r in results if r["department"] == dept])
        mark = " ⭐" if dept in dept_history else ""
        lines.append(f"  {i}. {dept}（{count}位醫師）{mark}")
    lines.append(f"\n💡 輸入數字或科別名稱")
    lines.append(f"💡 輸入 @ 返回主選單")
    return "\n".join(lines)


# ========== LINE-like Chat HTML ==========

CHAT_HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>叮咚到號 — LINE 模擬</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    background: #7494C0;
    height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
}

.phone-frame {
    width: 390px;
    height: 750px;
    background: #7494C0;
    border-radius: 30px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    border: 8px solid #333;
}

/* Header */
.chat-header {
    background: #06C755;
    color: white;
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}

.chat-header .avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
}

.chat-header .info h3 {
    font-size: 16px;
    font-weight: 600;
}
.chat-header .info span {
    font-size: 11px;
    opacity: 0.85;
}

/* Chat area */
.chat-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    background: #7494C0;
}

.msg-row {
    display: flex;
    gap: 8px;
    max-width: 85%;
    animation: msgIn 0.25s ease-out;
}

@keyframes msgIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.msg-row.bot { align-self: flex-start; }
.msg-row.user { align-self: flex-end; flex-direction: row-reverse; }

.msg-row .bubble-avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
    margin-top: 2px;
}

.msg-row.user .bubble-avatar { display: none; }

.bubble {
    padding: 10px 14px;
    border-radius: 18px;
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
}

.msg-row.bot .bubble {
    background: white;
    color: #333;
    border-bottom-left-radius: 4px;
}

.msg-row.user .bubble {
    background: #06C755;
    color: white;
    border-bottom-right-radius: 4px;
}

.msg-time {
    font-size: 10px;
    color: rgba(255,255,255,0.7);
    align-self: flex-end;
    flex-shrink: 0;
}

/* Quick buttons */
.quick-actions {
    padding: 8px 16px;
    display: flex;
    gap: 8px;
    overflow-x: auto;
    background: #7494C0;
    flex-shrink: 0;
}

.quick-btn {
    padding: 6px 14px;
    border-radius: 20px;
    border: 1.5px solid white;
    color: white;
    font-size: 13px;
    cursor: pointer;
    white-space: nowrap;
    background: rgba(255,255,255,0.15);
    transition: all 0.2s;
}
.quick-btn:hover {
    background: rgba(255,255,255,0.35);
}

/* Input area */
.chat-input-area {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: #F7F7F7;
    border-top: 1px solid #E0E0E0;
    flex-shrink: 0;
}

.chat-input-area input {
    flex: 1;
    padding: 10px 16px;
    border: 1px solid #DDD;
    border-radius: 24px;
    font-size: 14px;
    outline: none;
    background: white;
}
.chat-input-area input:focus {
    border-color: #06C755;
}

.send-btn {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: none;
    background: #06C755;
    color: white;
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
    flex-shrink: 0;
}
.send-btn:hover { background: #05B54C; }
.send-btn:disabled { background: #CCC; cursor: not-allowed; }

/* Loading dots */
.typing-indicator {
    display: flex;
    gap: 4px;
    padding: 12px 16px;
}
.typing-indicator .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #999;
    animation: typingBounce 1.2s infinite;
}
.typing-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingBounce {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-6px); }
}

/* Scrollbar */
.chat-body::-webkit-scrollbar { width: 4px; }
.chat-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.3); border-radius: 2px; }
</style>
</head>
<body>
<div class="phone-frame">
    <!-- Header -->
    <div class="chat-header">
        <div class="avatar">🔔</div>
        <div class="info">
            <h3>叮咚到號</h3>
            <span>醫院看診進度即時通知</span>
        </div>
    </div>

    <!-- Chat Messages -->
    <div class="chat-body" id="chatBody">
        <!-- Welcome message -->
    </div>

    <!-- Quick Action Buttons -->
    <div class="quick-actions">
        <div class="quick-btn" onclick="sendQuick('測試')">🧪 測試醫院</div>
        <div class="quick-btn" onclick="sendQuick('追蹤 測試醫院 內科 王大明')">🔔 追蹤王大明</div>
        <div class="quick-btn" onclick="sendQuick('取消追蹤')">⏹ 取消追蹤</div>
        <div class="quick-btn" onclick="sendQuick('狀態')">狀態</div>
        <div class="quick-btn" onclick="sendQuick('台北長庚')">台北長庚</div>
        <div class="quick-btn" onclick="sendQuick('醫院')">🏥 列表</div>
    </div>

    <!-- Input -->
    <div class="chat-input-area">
        <input type="text" id="msgInput" placeholder="輸入醫院名稱查詢..." autocomplete="off">
        <button class="send-btn" id="sendBtn" onclick="sendMessage()">▶</button>
    </div>
</div>

<script>
const chatBody = document.getElementById('chatBody');
const msgInput = document.getElementById('msgInput');
const sendBtn = document.getElementById('sendBtn');

const BRANCHES = {'台北長庚':'1','林口長庚':'3','高雄長庚':'8','測試醫院':'mock'};
const POLL_INTERVAL = 15000;
const MAX_TRACKS = 3;
const trackings = []; // array of tracking objects, max 3

function newTrackObj() {
    return {
        active:false, intervalId:null, hospitalName:'', branchId:'',
        deptFilter:'', doctorFilter:'',
        lastCurN:-1, lastNxtN:-1, lastCurSkip:false, lastNxtSkip:false,
        deptCode:null, timeCode:null, pollCount:0, dept:'', room:'', session:'',
        userNumber:null, waitingForNumber:false, notifiedArrival:false
    };
}
function getActiveTrackings() { return trackings.filter(t => t.active); }
function getWaitingTrack() { return trackings.find(t => t.active && t.waitingForNumber); }
function findTracking(doctor) { return trackings.find(t => t.active && t.doctorFilter === doctor); }
function isAnyTracking() { return trackings.some(t => t.active); }

window.onload = () => {
    addBotMsg("👋 您好！我是叮咚到號小幫手\n\n📋 輸入醫院名稱查詢看診進度\n🔔 最多可同時追蹤 "+MAX_TRACKS+" 位醫師\n\n💡 例：追蹤 台北長庚 中醫內兒科 游汶霖");
};

function getTimeStr() {
    const d = new Date();
    return d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
}
function getTimestamp() {
    const d = new Date();
    return (d.getMonth()+1).toString().padStart(2,'0') + '/' + d.getDate().toString().padStart(2,'0') + ' ' + getTimeStr();
}
function esc(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>'); }

function addBotMsg(text) {
    const r = document.createElement('div'); r.className = 'msg-row bot';
    r.innerHTML = '<div class="bubble-avatar">🔔</div><div class="bubble">'+esc(text)+'</div><span class="msg-time">'+getTimeStr()+'</span>';
    chatBody.appendChild(r); chatBody.scrollTop = chatBody.scrollHeight;
}
function addUserMsg(text) {
    const r = document.createElement('div'); r.className = 'msg-row user';
    r.innerHTML = '<div class="bubble">'+esc(text)+'</div><span class="msg-time">'+getTimeStr()+'</span>';
    chatBody.appendChild(r); chatBody.scrollTop = chatBody.scrollHeight;
}
function addTyping() {
    const r = document.createElement('div'); r.className='msg-row bot'; r.id='typingRow';
    r.innerHTML = '<div class="bubble-avatar">🔔</div><div class="bubble"><div class="typing-indicator"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>';
    chatBody.appendChild(r); chatBody.scrollTop = chatBody.scrollHeight;
}
function removeTyping() { const el=document.getElementById('typingRow'); if(el) el.remove(); }

function formatNumInfo(curN, nxtN, curSkip, nxtSkip) {
    let lines = [];
    if (curN > 0) {
        lines.push('   目前號碼:' + curN + '號' + (curSkip ? '(過號)' : ''));
        if (nxtN > 0 && nxtN !== curN) {
            lines.push('      下一號:' + nxtN + '號' + (nxtSkip ? '(過號)' : ''));
        }
    } else if (nxtN > 0) {
        lines.push('   下一號:' + nxtN + '號' + (nxtSkip ? '(過號)' : ''));
    } else {
        lines.push('   尚未開始');
    }
    return lines.join('\n');
}
function formatUserStatus(curN, t) {
    if (!t || !t.userNumber) return '';
    const un = t.userNumber;
    if (curN > un) return '\n\n您是 ' + un + '號，已過號，持續追蹤中';
    if (curN === un) return '\n\n您的號碼 ' + un + '號，正在叫號';
    const remaining = un - curN;
    return '\n\n您是 ' + un + '號，還剩約 ' + remaining + ' 號';
}

function stopTracking(t) {
    if (t.intervalId) { clearInterval(t.intervalId); t.intervalId = null; }
    t.active = false;
    // remove from array
    const idx = trackings.indexOf(t);
    if (idx >= 0) trackings.splice(idx, 1);
    updateTitle();
}
function stopAllTracking() {
    while (trackings.length > 0) stopTracking(trackings[0]);
}
function updateTitle() {
    const active = getActiveTrackings();
    if (active.length === 0) { document.title = '叮咚到號 — LINE 模擬'; return; }
    const parts = active.map(t => {
        let n = t.lastCurN > 0 ? t.lastCurN+'號' : '等待中';
        return t.doctorFilter+' '+n;
    });
    document.title = '追蹤中：'+parts.join(' | ');
}

async function startTracking(hospitalName, branchId, deptFilter, doctorFilter) {
    // check duplicate
    if (findTracking(doctorFilter)) {
        addBotMsg('已在追蹤 '+doctorFilter+'，無需重複追蹤');
        return;
    }
    // check max
    if (getActiveTrackings().length >= MAX_TRACKS) {
        const names = getActiveTrackings().map(t => t.doctorFilter).join('、');
        addBotMsg('最多同時追蹤 '+MAX_TRACKS+' 位醫師\n目前追蹤中：'+names+'\n\n請先取消一個再追蹤新的\n輸入「取消追蹤 醫師名」或「取消全部追蹤」');
        return;
    }

    try {
        const resp = await fetch('/api/find_doctor', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({branch_id: branchId, doctor: doctorFilter, dept_filter: deptFilter})
        });
        if (!resp.ok) {
            addBotMsg('找不到 '+doctorFilter+' 的看診資料\n可能尚未開始看診或已結束');
            return;
        }
        const found = await resp.json();
        const t = newTrackObj();
        t.active = true;
        t.hospitalName = hospitalName;
        t.branchId = branchId;
        t.deptFilter = deptFilter;
        t.doctorFilter = doctorFilter;
        t.deptCode = found.dept_code;
        t.timeCode = found.time_code;
        t.lastCurN = found.curN;
        t.lastNxtN = found.nxtN;
        t.lastCurSkip = found.curSkip;
        t.lastNxtSkip = found.nxtSkip;
        t.dept = found.dept;
        t.room = found.room;
        t.session = found.session;
        t.pollCount = 0;
        t.userNumber = null;
        t.waitingForNumber = true;
        t.notifiedArrival = false;
        trackings.push(t);

        const numInfo = formatNumInfo(found.curN, found.nxtN, found.curSkip, found.nxtSkip);
        const trackCount = getActiveTrackings().length;
        let trackLabel = '';
        if (trackCount > 1) trackLabel = ' ('+trackCount+'/'+MAX_TRACKS+')';
        addBotMsg(
            hospitalName+' 看診進度'+trackLabel+'\n'+
            getTimestamp()+'\n'+
            found.dept+' / '+doctorFilter+' ['+found.room+'] '+found.session+'\n'+
            numInfo+'\n\n'+
            '已開始追蹤 '+doctorFilter+'\n'+
            '每 '+POLL_INTERVAL/1000+' 秒自動檢查，號碼變動時通知\n'+
            '輸入「取消追蹤」可停止'
        );
        addBotMsg('請問您的掛號號碼是幾號？\n（直接輸入數字，或輸入「跳過」）');
        updateTitle();
        t.intervalId = setInterval(() => pollForTrack(t), POLL_INTERVAL);
    } catch(e) {
        addBotMsg('連線錯誤：'+e.message);
    }
}

async function pollForTrack(t) {
    if (!t.active) return;
    t.pollCount++;
    try {
        const resp = await fetch('/api/poll', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({
                branch_id: t.branchId,
                dept_code: t.deptCode,
                time_code: t.timeCode,
                doctor: t.doctorFilter,
                dept_filter: t.deptFilter
            })
        });
        const data = await resp.json();
        if (!data.found) {
            addBotMsg(t.doctorFilter+' 可能已休診');
            stopTracking(t);
            addBotMsg(t.doctorFilter+' 追蹤已自動停止');
            return;
        }
        const {curN, nxtN, curSkip, nxtSkip} = data;
        const changed = curN !== t.lastCurN || nxtN !== t.lastNxtN
            || curSkip !== t.lastCurSkip || nxtSkip !== t.lastNxtSkip;

        if (changed) {
            // 判斷：目前叫號 = 用戶號碼 且 未過號 → 已叫號，自動停止
            if (t.userNumber && curN === t.userNumber && !curSkip && !t.notifiedArrival) {
                t.notifiedArrival = true;
                addBotMsg('輪到您了！ — '+t.doctorFilter+'\n'+getTimestamp()+'\n'+
                    formatNumInfo(curN, nxtN, curSkip, nxtSkip)+'\n\n'+
                    '您的號碼 '+t.userNumber+'號，已叫號！');
                stopTracking(t);
                addBotMsg(t.doctorFilter+' 追蹤已自動停止，祝您看診順利！');
                return;
            }
            // 一般號碼更新（含過號狀態顯示）
            else {
                let msg = '號碼更新 — '+t.doctorFilter+'\n'+getTimestamp()+'\n'+
                    formatNumInfo(curN, nxtN, curSkip, nxtSkip);
                msg += formatUserStatus(curN, t);
                addBotMsg(msg);
            }
            t.lastCurN = curN; t.lastNxtN = nxtN;
            t.lastCurSkip = curSkip; t.lastNxtSkip = nxtSkip;
        }
        updateTitle();
    } catch(e) {
        // silently retry
    }
}

let inBackendFlow = false; // true when user is in dept/doctor selection while tracking

function showTrackingHint(t) {
    const remaining = MAX_TRACKS - getActiveTrackings().length;
    let hint = '';
    if (remaining > 0) {
        hint += '您最多還可以追蹤 '+remaining+' 位醫師\n';
    }
    hint += '輸入 0 可查詢 '+t.hospitalName+' 其他科別';
    addBotMsg(hint);
}

async function sendMessage() {
    const text = msgInput.value.trim();
    if (!text) return;
    addUserMsg(text);
    msgInput.value = '';
    sendBtn.disabled = true;

    // 追蹤中：等待用戶輸入診號
    const waitTrack = getWaitingTrack();
    if (waitTrack) {
        if (text === '跳過' || text === '略過' || text === 'skip') {
            waitTrack.waitingForNumber = false;
            waitTrack.userNumber = null;
            addBotMsg('好的，'+waitTrack.doctorFilter+' 將持續通知號碼變動直到看診結束');
            showTrackingHint(waitTrack);
            sendBtn.disabled = false; msgInput.focus(); return;
        }
        const num = parseInt(text);
        if (!isNaN(num) && num > 0) {
            waitTrack.waitingForNumber = false;
            waitTrack.userNumber = num;
            const remaining = num - waitTrack.lastCurN;
            if (waitTrack.lastCurN >= num) {
                addBotMsg('收到！您是 '+num+'號（'+waitTrack.doctorFilter+'）\n目前已叫到 '+waitTrack.lastCurN+'號，您的號碼已過號\n持續追蹤中，叫到您的號時會通知');
                showTrackingHint(waitTrack);
            } else {
                addBotMsg('收到！您是 '+num+'號（'+waitTrack.doctorFilter+'）\n目前看到 '+waitTrack.lastCurN+'號，還剩約 '+remaining+' 號\n到號時會自動通知');
                showTrackingHint(waitTrack);
            }
            sendBtn.disabled = false; msgInput.focus(); return;
        }
        if (!text.includes('取消') && !text.includes('停止') && text !== '狀態') {
            addBotMsg('請輸入您的掛號號碼（數字），或輸入「跳過」');
            sendBtn.disabled = false; msgInput.focus(); return;
        }
    }

    // 前端攔截追蹤指令
    if (text.includes('取消全部追蹤') || text.includes('停止全部追蹤')) {
        if (isAnyTracking()) {
            const names = getActiveTrackings().map(t => t.doctorFilter).join('、');
            stopAllTracking();
            addBotMsg('已取消全部追蹤：'+names);
        } else {
            addBotMsg('目前沒有追蹤中的醫師');
        }
        sendBtn.disabled = false; msgInput.focus(); return;
    }
    if (text.includes('取消追蹤') || text.includes('停止追蹤')) {
        const active = getActiveTrackings();
        if (active.length === 0) {
            addBotMsg('目前沒有追蹤中的醫師');
        } else if (active.length === 1) {
            const n = active[0].doctorFilter;
            stopTracking(active[0]);
            addBotMsg('已取消追蹤 '+n);
        } else {
            // try to match doctor name from text
            const rest = text.replace(/取消追蹤|停止追蹤/g,'').trim();
            const found = rest ? active.find(t => t.doctorFilter.includes(rest) || rest.includes(t.doctorFilter)) : null;
            if (found) {
                stopTracking(found);
                addBotMsg('已取消追蹤 '+found.doctorFilter);
            } else {
                const names = active.map((t,i) => '  '+(i+1)+'. '+t.doctorFilter).join('\n');
                addBotMsg('目前追蹤 '+active.length+' 位醫師：\n'+names+'\n\n請指定醫師名，如「取消追蹤 王大明」\n或輸入「取消全部追蹤」');
            }
        }
        sendBtn.disabled = false; msgInput.focus(); return;
    }
    if (text === '狀態' || text === '追蹤狀態') {
        const active = getActiveTrackings();
        if (active.length === 0) {
            addBotMsg('目前沒有追蹤中的醫師');
        } else {
            let parts = [];
            active.forEach((t, i) => {
                let s = (active.length > 1 ? '【'+(i+1)+'】 ' : '') + t.hospitalName+'\n'+t.dept+' / '+t.doctorFilter+'\n'+
                    formatNumInfo(t.lastCurN,t.lastNxtN,t.lastCurSkip,t.lastNxtSkip);
                if (t.userNumber) {
                    s += '\n您是 '+t.userNumber+'號';
                    if (t.lastCurN < t.userNumber) s += '，還剩約 '+(t.userNumber - t.lastCurN)+' 號';
                }
                parts.push(s);
            });
            addBotMsg('追蹤中（'+active.length+'/'+MAX_TRACKS+'）\n\n'+parts.join('\n\n'));
        }
        sendBtn.disabled = false; msgInput.focus(); return;
    }
    if (text.includes('追蹤')) {
        let rest = text.replace('追蹤','').trim();
        let hospitalName='', branchId='';
        for (const [name,bid] of Object.entries(BRANCHES)) {
            if (rest.includes(name)) { hospitalName=name; branchId=bid; rest=rest.replace(name,'').trim(); break; }
        }
        if (!branchId) { addBotMsg('❌ 請指定醫院\n\n格式：追蹤 台北長庚 科別 醫師名'); sendBtn.disabled=false; msgInput.focus(); return; }
        const parts = rest.split(/\s+/).filter(Boolean);
        let deptFilter='', doctorFilter='';
        if (parts.length >= 2) { deptFilter=parts.slice(0,-1).join(''); doctorFilter=parts[parts.length-1]; }
        else if (parts.length===1) { doctorFilter=parts[0]; }
        else { addBotMsg('❌ 請指定醫師名\n\n例：追蹤 台北長庚 中醫內兒科 游汶霖'); sendBtn.disabled=false; msgInput.focus(); return; }
        await startTracking(hospitalName, branchId, deptFilter, doctorFilter);
        sendBtn.disabled = false; msgInput.focus(); return;
    }

    // 追蹤中輸入 0 → 查詢該醫院科別
    if (isAnyTracking() && !inBackendFlow && text === '0') {
        const t = getActiveTrackings()[0];
        inBackendFlow = true;
        addTyping();
        try {
            const resp = await fetch('/api/chat', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({message: t.hospitalName})
            });
            const data = await resp.json();
            removeTyping();
            addBotMsg(data.reply);
        } catch(e) { removeTyping(); addBotMsg('連線錯誤'); inBackendFlow = false; }
        sendBtn.disabled = false; msgInput.focus(); return;
    }
    // 追蹤中輸入純數字但不在選擇流程中 → 提示
    if (isAnyTracking() && !inBackendFlow && /^\d+$/.test(text)) {
        const active = getActiveTrackings();
        const names = active.map(t => t.doctorFilter).join('、');
        addBotMsg('目前追蹤中：'+names+'\n\n輸入 0 查詢科別\n輸入「狀態」查看追蹤進度\n輸入「取消追蹤」停止追蹤');
        sendBtn.disabled = false; msgInput.focus(); return;
    }

    // 一般訊息走後端 /api/chat
    addTyping();
    try {
        const resp = await fetch('/api/chat', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: text}),
        });
        const data = await resp.json();
        removeTyping();
        // 後端回傳追蹤指令
        if (data.reply && data.reply.startsWith('__TRACK__')) {
            inBackendFlow = false;
            const parts = data.reply.replace('__TRACK__','').split('\t');
            const hospitalName = parts[0] || '';
            const deptFilter = parts[1] || '';
            const doctorFilter = parts[2] || '';
            let branchId = BRANCHES[hospitalName] || '';
            if (branchId) {
                await startTracking(hospitalName, branchId, deptFilter, doctorFilter);
            } else {
                addBotMsg('❌ 找不到醫院「'+hospitalName+'」的追蹤資訊');
            }
        } else {
            addBotMsg(data.reply);
            // 判斷是否仍在選擇流程中（含科別/醫師選單 或 after_result 選單）
            const r = data.reply || '';
            if (r.includes('哪科') || r.includes('請選擇') || r.includes('🔔') && r.includes('查詢別科')) {
                inBackendFlow = true;
            } else {
                inBackendFlow = false;
            }
        }
    } catch (e) {
        removeTyping();
        addBotMsg('❌ 連線錯誤，請稍後再試');
    }
    sendBtn.disabled = false;
    msgInput.focus();
}

function sendQuick(text) { msgInput.value = text; sendMessage(); }
msgInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendMessage(); });
</script>
</div>
</body>
</html>"""


if __name__ == "__main__":
    print("=" * 50)
    print("  叮咚到號 — LINE 模擬對話")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
