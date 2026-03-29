#!/usr/bin/env python3
"""叮咚到號 — 資料庫遷移腳本

用法（在 Docker 容器內執行）:
    docker exec ajz-dindon python migrate.py

或在伺服器專案目錄執行:
    cd /opt/docker/ajz-dingdon
    docker compose exec linebot python migrate.py

功能:
    1. 檢查各表是否存在 & 欄位是否完整
    2. 缺表 → 建立
    3. 舊表欄位不足 → DROP 重建（僅限空表或參考表）
    4. 有資料的表 → ALTER TABLE 補欄位
    5. 全程有 log，不會靜默失敗
"""

import os
import sys

# ---- 載入 .env ----
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

import pymysql

MYSQL_HOST = os.environ.get("MYSQL_HOST", "host.docker.internal")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "")
MYSQL_PASS = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB   = os.environ.get("MYSQL_DATABASE", "")


def get_conn():
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def log(msg):
    print(f"  [migrate] {msg}")


def get_existing_tables(cur):
    cur.execute("SHOW TABLES")
    return {list(row.values())[0] for row in cur.fetchall()}


def get_columns(cur, table):
    cur.execute(f"DESCRIBE `{table}`")
    return {row["Field"] for row in cur.fetchall()}


def get_row_count(cur, table):
    cur.execute(f"SELECT COUNT(*) AS cnt FROM `{table}`")
    return cur.fetchone()["cnt"]


# ============================================================
# 表定義（與 line_bot.py _init_tables 完全一致）
# ============================================================

TABLES = {
    "line_users": """
        CREATE TABLE line_users (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            line_uid    VARCHAR(64)  NOT NULL UNIQUE,
            name        VARCHAR(100) NOT NULL DEFAULT '',
            first_seen  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_active DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "hospitals": """
        CREATE TABLE hospitals (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            code            VARCHAR(50)   NOT NULL UNIQUE COMMENT '醫院代碼 eg. cgmh_taipei',
            name            VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '顯示名 eg. 台北長庚',
            aliases         TEXT           COMMENT '別名,逗號分隔（搜尋用）',
            city            VARCHAR(20)   NOT NULL DEFAULT '' COMMENT '市/縣 eg. 台北市',
            district        VARCHAR(20)   NOT NULL DEFAULT '' COMMENT '區 eg. 信義區',
            address         VARCHAR(200)  NOT NULL DEFAULT '' COMMENT '完整地址',
            lat             DECIMAL(10,7) DEFAULT NULL COMMENT '緯度',
            lng             DECIMAL(10,7) DEFAULT NULL COMMENT '經度',
            phone           VARCHAR(30)   NOT NULL DEFAULT '' COMMENT '服務電話',
            emergency_phone VARCHAR(30)   NOT NULL DEFAULT '' COMMENT '急診電話',
            fax             VARCHAR(30)   NOT NULL DEFAULT '' COMMENT '傳真',
            website         VARCHAR(300)  NOT NULL DEFAULT '' COMMENT '官方網站',
            register_url    VARCHAR(300)  NOT NULL DEFAULT '' COMMENT '網路掛號網址',
            level           VARCHAR(20)   NOT NULL DEFAULT '' COMMENT '醫學中心/區域醫院/地區醫院/診所',
            type            VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '綜合醫院/專科醫院/中醫院',
            beds            INT            DEFAULT NULL COMMENT '病床數',
            business_hours  TEXT           COMMENT '營業時間 JSON',
            traffic_info    TEXT           COMMENT '交通方式',
            note            TEXT           COMMENT '備註',
            enabled         TINYINT(1)    NOT NULL DEFAULT 1,
            created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_city_district (city, district)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "departments": """
        CREATE TABLE departments (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            hospital_id     INT           NOT NULL COMMENT 'FK → hospitals',
            name            VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '科別名 eg. 心臟內科',
            category        VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '大分類：內科/外科/婦兒科/中醫/牙科/其他',
            treats          TEXT           COMMENT '主治疾病（逗號分隔）',
            symptoms        TEXT           COMMENT '常見症狀（逗號分隔）',
            description     TEXT           COMMENT '科別說明',
            register_note   TEXT           COMMENT '掛號提醒',
            enabled         TINYINT(1)    NOT NULL DEFAULT 1,
            INDEX idx_hospital_dept (hospital_id),
            UNIQUE KEY uk_dept (hospital_id, name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    "doctors": """
        CREATE TABLE doctors (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            hospital_id     INT           NOT NULL COMMENT 'FK → hospitals',
            dept_id         INT           DEFAULT NULL COMMENT 'FK → departments',
            dept            VARCHAR(100)  NOT NULL DEFAULT '' COMMENT '科別名（冗餘）',
            name            VARCHAR(50)   NOT NULL DEFAULT '',
            gender          VARCHAR(5)    NOT NULL DEFAULT '' COMMENT '男/女',
            title           VARCHAR(50)   NOT NULL DEFAULT '' COMMENT '職稱',
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
    """,

    "tracking_logs": """
        CREATE TABLE tracking_logs (
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
    """,

    "doctor_daily_logs": """
        CREATE TABLE doctor_daily_logs (
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
    """,
}

# 每張表應有的欄位（用來判斷是否需要重建）
EXPECTED_COLUMNS = {
    "line_users":        {"id", "line_uid", "name", "first_seen", "last_active"},
    "hospitals":         {"id", "code", "name", "aliases", "city", "district", "address",
                          "lat", "lng", "phone", "emergency_phone", "fax", "website",
                          "register_url", "level", "type", "beds", "business_hours",
                          "traffic_info", "note", "enabled", "created_at", "updated_at"},
    "departments":       {"id", "hospital_id", "name", "category", "treats", "symptoms",
                          "description", "register_note", "enabled"},
    "doctors":           {"id", "hospital_id", "dept_id", "dept", "name", "gender", "title",
                          "specialty", "education", "experience", "available_days", "room",
                          "session_period", "photo_url", "note", "enabled", "created_at", "updated_at"},
    "tracking_logs":     {"id", "line_uid", "hospital", "dept", "doctor", "room", "session_period",
                          "user_number", "start_number", "end_number", "start_time", "end_time",
                          "wait_seconds", "status", "push_count", "number_changes", "user_skipped"},
    "doctor_daily_logs": {"id", "date", "hospital", "dept", "doctor", "room", "session_period",
                          "first_number", "last_number", "first_seen_at", "last_seen_at",
                          "total_calls", "skip_count", "poll_count"},
}

# 有用戶資料的表 → 不能隨便 DROP，要用 ALTER TABLE 補欄位
PROTECT_TABLES = {"line_users", "tracking_logs", "doctor_daily_logs"}


def _find_fk_references(cur, table):
    """找出所有外鍵引用此表的約束 → [(子表, 約束名), ...]"""
    cur.execute("""
        SELECT TABLE_NAME, CONSTRAINT_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE REFERENCED_TABLE_NAME = %s
          AND TABLE_SCHEMA = %s
    """, (table, MYSQL_DB))
    return [(row["TABLE_NAME"], row["CONSTRAINT_NAME"]) for row in cur.fetchall()]


def migrate():
    print("=" * 60)
    print("叮咚到號 — 資料庫遷移")
    print(f"  MySQL: {MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}")
    print("=" * 60)

    conn = get_conn()
    cur = conn.cursor()

    # 全程關閉外鍵檢查，避免 FK 約束擋住 DROP
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    conn.commit()
    log("已關閉外鍵檢查 (FOREIGN_KEY_CHECKS = 0)")

    existing = get_existing_tables(cur)
    log(f"現有資料表: {', '.join(sorted(existing)) if existing else '(無)'}")

    # 建立順序：hospitals → departments → doctors → 其他
    ordered = ["line_users", "hospitals", "departments", "doctors",
               "tracking_logs", "doctor_daily_logs"]

    for table in ordered:
        print()
        expected_cols = EXPECTED_COLUMNS[table]
        create_sql = TABLES[table]

        if table not in existing:
            # ---- 表不存在 → 直接建立 ----
            log(f"[{table}] 不存在 → 建立中...")
            cur.execute(create_sql)
            conn.commit()
            log(f"[{table}] ✅ 建立完成 ({len(expected_cols)} 個欄位)")
            continue

        # ---- 表已存在 → 檢查欄位 ----
        current_cols = get_columns(cur, table)
        missing_cols = expected_cols - current_cols
        extra_cols = current_cols - expected_cols

        if not missing_cols:
            log(f"[{table}] ✅ 欄位完整 ({len(current_cols)} 個)")
            if extra_cols:
                log(f"  ⚠️  多出的欄位（不影響）: {', '.join(sorted(extra_cols))}")
            continue

        log(f"[{table}] 缺少欄位: {', '.join(sorted(missing_cols))}")

        row_count = get_row_count(cur, table)

        if table in PROTECT_TABLES and row_count > 0:
            # ---- 有資料的受保護表 → ALTER TABLE 補欄位 ----
            log(f"[{table}] 有 {row_count} 筆資料，使用 ALTER TABLE 補欄位...")
            for col in sorted(missing_cols):
                col_def = _get_alter_column_def(table, col)
                if col_def:
                    alter_sql = f"ALTER TABLE `{table}` ADD COLUMN {col_def}"
                    log(f"  執行: {alter_sql[:100]}...")
                    cur.execute(alter_sql)
                    conn.commit()
                    log(f"  ✅ {col} 已新增")
                else:
                    log(f"  ⚠️  {col} 無法自動補欄位，請手動處理")
        else:
            # ---- 空表或參考表 → DROP 重建 ----
            if row_count > 0:
                log(f"[{table}] 有 {row_count} 筆資料但不在保護名單，DROP 重建...")
            else:
                log(f"[{table}] 空表，DROP 重建...")

            # 先 DROP 我們管理的依賴子表
            dependents = _get_dependents(table)
            for dep in dependents:
                if dep in existing:
                    try:
                        dep_count = get_row_count(cur, dep)
                    except Exception:
                        dep_count = 0
                    if dep_count > 0 and dep in PROTECT_TABLES:
                        log(f"  ⚠️  {dep} 有 {dep_count} 筆資料且受保護，跳過重建")
                        continue
                    log(f"  先 DROP {dep}...")
                    cur.execute(f"DROP TABLE IF EXISTS `{dep}`")
                    conn.commit()

            # DROP 並重建主表（FK_CHECKS 已在開頭全域關閉）
            cur.execute(f"DROP TABLE IF EXISTS `{table}`")
            cur.execute(create_sql)
            conn.commit()
            log(f"[{table}] ✅ 重建完成 ({len(expected_cols)} 個欄位)")

            # 重建被 DROP 的依賴表
            for dep in dependents:
                if dep in TABLES:
                    log(f"  重建 {dep}...")
                    cur.execute(f"DROP TABLE IF EXISTS `{dep}`")
                    cur.execute(TABLES[dep])
                    conn.commit()
                    log(f"  ✅ {dep} 重建完成")

    # 重新開啟外鍵檢查
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    log("已重新開啟外鍵檢查")

    # ---- 最終驗證 ----
    print()
    print("-" * 60)
    log("最終驗證:")
    final_tables = get_existing_tables(cur)
    all_ok = True
    for table in ordered:
        if table not in final_tables:
            log(f"  ❌ {table} 不存在!")
            all_ok = False
            continue
        cols = get_columns(cur, table)
        missing = EXPECTED_COLUMNS[table] - cols
        count = get_row_count(cur, table)
        if missing:
            log(f"  ⚠️  {table}: 仍缺 {', '.join(sorted(missing))} ({count} 筆資料)")
            all_ok = False
        else:
            log(f"  ✅ {table}: {len(cols)} 欄位, {count} 筆資料")

    print()
    if all_ok:
        print("🎉 遷移完成！所有資料表結構正確。")
    else:
        print("⚠️  遷移完成，但部分表可能需要手動處理。")

    cur.close()
    conn.close()


def _get_dependents(table):
    """回傳依賴此表的子表（需要先 DROP 的）"""
    deps = {
        "hospitals": ["doctors", "departments"],
    }
    return deps.get(table, [])


def _get_alter_column_def(table, col):
    """回傳 ALTER TABLE ADD COLUMN 的欄位定義"""
    # 所有可能需要 ALTER 補上的欄位定義
    defs = {
        # tracking_logs
        ("tracking_logs", "session_period"): "session_period VARCHAR(10) NOT NULL DEFAULT '' COMMENT '上午/下午/夜晚'",
        ("tracking_logs", "push_count"):     "push_count INT NOT NULL DEFAULT 0",
        ("tracking_logs", "number_changes"): "number_changes INT NOT NULL DEFAULT 0",
        ("tracking_logs", "user_skipped"):   "user_skipped TINYINT(1) NOT NULL DEFAULT 0",
        # doctor_daily_logs (以防需要)
        ("doctor_daily_logs", "dept"):            "dept VARCHAR(100) NOT NULL DEFAULT ''",
        ("doctor_daily_logs", "room"):            "room VARCHAR(20) NOT NULL DEFAULT ''",
        ("doctor_daily_logs", "session_period"):  "session_period VARCHAR(10) NOT NULL DEFAULT '' COMMENT '上午/下午/夜晚'",
        # line_users (以防需要)
        ("line_users", "last_active"): "last_active DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
    }
    return defs.get((table, col))


if __name__ == "__main__":
    try:
        migrate()
    except pymysql.OperationalError as e:
        print(f"\n❌ MySQL 連線失敗: {e}")
        print(f"   請確認 .env 中的 MYSQL_HOST 設定")
        print(f"   Docker 容器內應使用: MYSQL_HOST=host.docker.internal")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 遷移失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
