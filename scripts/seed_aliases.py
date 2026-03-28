"""
一次性腳本：建立 hospital_aliases 表 + 塞入所有別名資料
用法：在專案根目錄執行
    python scripts/seed_aliases.py
"""

import os
import sys

# 確保能 import app 模組
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import pymysql
from app.config import settings

# ========== 別名資料 ==========
# hospital_code → [別名列表]
ALIAS_MAP = {
    # --- 萬芳醫院 ---
    "wanfang": ["萬芳", "wanfang"],
    # --- 台大醫院 ---
    "ntuh": ["台大", "臺大", "臺大醫院", "台大總院", "ntuh"],
    # --- 台大兒童醫院 ---
    "ntuh-children": ["台大兒童", "臺大兒童", "台大兒醫"],
    # --- 台北榮總 ---
    "tpvgh": ["北榮", "台北榮總", "臺北榮總", "榮總", "tpvgh"],
    # --- 台北長庚 ---
    "changgung-taipei": ["台北長庚", "北長庚"],
    # --- 林口長庚 ---
    "changgung-linkou": ["林口長庚", "林口"],
    # --- 高雄長庚 ---
    "changgung-kaohsiung": ["高雄長庚", "高長庚"],
    # --- 馬偕醫院（台北）---
    "mackay-taipei": ["馬偕", "台北馬偕", "馬偕台北", "臺北馬偕"],
    # --- 馬偕醫院（淡水）---
    "mackay-tamsui": ["淡水馬偕", "馬偕淡水"],
    # --- 國泰醫院 ---
    "cathay": ["國泰", "cathay"],
    # --- 新光醫院 ---
    "shinkong": ["新光", "shinkong"],
    # --- 三軍總醫院 ---
    "tsgh": ["三總", "三軍", "三軍總", "tsgh"],
    # --- 新北聯合醫院（板橋）---
    "newtaipei-banqiao": ["板橋聯醫", "板橋", "新北板橋", "聯醫板橋"],
    # --- 新北聯合醫院（三重）---
    "newtaipei-sanchong": ["三重聯醫", "三重", "新北三重", "聯醫三重"],
    # --- 高雄聯合醫院 ---
    "kaohsiung-united": ["高雄聯醫", "高聯醫"],
}


def main():
    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
    )
    cur = conn.cursor()

    # ---- 1. 建表（如果不存在）----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hospital_aliases (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            hospital_code VARCHAR(50)  NOT NULL COMMENT '對應 hospitals.code',
            alias       VARCHAR(100) NOT NULL COMMENT '別名（如：三總、北榮）',
            created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_alias (alias),
            KEY ix_hospital_code (hospital_code),
            CONSTRAINT fk_alias_hospital
                FOREIGN KEY (hospital_code) REFERENCES hospitals(code)
                ON UPDATE CASCADE ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='醫院別名表 — 讓使用者用簡稱查詢醫院';
    """)
    print("✅ hospital_aliases 表已建立（或已存在）")

    # ---- 2. 塞入別名（跳過已存在的）----
    inserted = 0
    updated = 0
    for hospital_code, aliases in ALIAS_MAP.items():
        for alias in aliases:
            # 先檢查是否已存在
            cur.execute(
                "SELECT id, hospital_code FROM hospital_aliases WHERE alias = %s",
                (alias,),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO hospital_aliases (hospital_code, alias) VALUES (%s, %s)",
                    (hospital_code, alias),
                )
                inserted += 1
                print(f"  + {alias} → {hospital_code}")
            elif row[1] != hospital_code:
                # 別名存在但指向不同醫院，更新
                cur.execute(
                    "UPDATE hospital_aliases SET hospital_code = %s WHERE id = %s",
                    (hospital_code, row[0]),
                )
                updated += 1
                print(f"  ↻ {alias} → {hospital_code}（原本指向 {row[1]}）")

    conn.commit()
    print(f"\n✅ 完成！新增 {inserted} 筆，更新 {updated} 筆")

    # ---- 3. 顯示目前所有別名 ----
    cur.execute("""
        SELECT a.alias, a.hospital_code, h.name
        FROM hospital_aliases a
        LEFT JOIN hospitals h ON h.code = a.hospital_code
        ORDER BY a.hospital_code, a.alias
    """)
    rows = cur.fetchall()
    print(f"\n📋 目前共 {len(rows)} 個別名：")
    current_code = None
    for alias, code, name in rows:
        if code != current_code:
            current_code = code
            print(f"\n  【{name or code}】")
        print(f"    • {alias}")

    # ---- 4. 建立 user_query_history 表 ----
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_query_history (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            user_id       VARCHAR(64)  NOT NULL COMMENT '使用者 ID（LINE user_id）',
            hospital_code VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '醫院代碼',
            department    VARCHAR(100) NOT NULL DEFAULT '' COMMENT '科別',
            doctor_name   VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '醫師姓名',
            use_count     INT          NOT NULL DEFAULT 1  COMMENT '使用次數',
            last_used_at  DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                                       COMMENT '最後使用時間',
            created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
            INDEX ix_user_hospital (user_id, hospital_code),
            INDEX ix_user_dept     (user_id, hospital_code, department),
            INDEX ix_user_doctor   (user_id, hospital_code, department, doctor_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='使用者查詢歷史 — 記錄醫院/科別/醫師使用次數';
    """)
    conn.commit()
    print("\n✅ user_query_history 表已建立（或已存在）")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
