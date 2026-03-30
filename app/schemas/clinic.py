"""看診進度統一資料結構"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ClinicProgressData:
    """各醫院爬蟲解析後的標準化資料"""
    hospital_code: str
    hospital_name: str
    date: str                  # 如 "2026/03/28"
    session: str               # 如 "上午診"
    department: str            # 如 "精神科"
    doctor_name: str           # 如 "許元彰"
    clinic_room: str           # 如 "282診"
    current_number: int        # 目前號碼
    next_number: int           # 下一號碼
    is_current_skipped: bool   # 目前號碼是否過號
    is_next_skipped: bool      # 下一號碼是否過號
    fetched_at: datetime       # 抓取時間

    def format_message(self) -> str:
        """格式化為 LINE 推播訊息格式
        範例: 03/28 15:24 萬芳醫院-精神科 許元彰 282診 目前45號 46下一號
        """
        time_str = self.fetched_at.strftime("%m/%d %H:%M")

        # 目前號碼
        current_str = f"目前{self.current_number}號"
        if self.is_current_skipped:
            current_str += "(過號)"

        # 下一號碼
        next_str = f"{self.next_number}下一號"
        if self.is_next_skipped:
            next_str += "(過號)"

        return (
            f"{time_str} {self.hospital_name}-{self.department} "
            f"{self.doctor_name} {self.clinic_room} "
            f"{current_str} {next_str}"
        )

    def to_cache_key(self) -> str:
        """Redis 快取 key — 用 department + doctor_name + clinic_room 確保唯一"""
        return f"progress:{self.hospital_code}:{self.department}:{self.doctor_name}:{self.clinic_room}"

    def to_dict(self) -> dict:
        """轉為字典（存入 Redis）"""
        return {
            "hospital_code": self.hospital_code,
            "hospital_name": self.hospital_name,
            "date": self.date,
            "session": self.session,
            "department": self.department,
            "doctor_name": self.doctor_name,
            "clinic_room": self.clinic_room,
            "current_number": self.current_number,
            "next_number": self.next_number,
            "is_current_skipped": self.is_current_skipped,
            "is_next_skipped": self.is_next_skipped,
            "fetched_at": self.fetched_at.isoformat(),
        }
