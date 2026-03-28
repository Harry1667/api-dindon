"""健保特約醫事機構資料模型 — 來自 NHI 開放資料 API"""

from datetime import datetime
from sqlalchemy import String, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class NhiInstitution(Base):
    """健保特約醫事機構（醫學中心、區域醫院、地區醫院、診所、藥局）"""
    __tablename__ = "nhi_institutions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # === NHI 原始欄位 ===
    hosp_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, comment="醫事機構代碼")
    hosp_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="機構名稱")
    hosp_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="機構種類：醫學中心/區域醫院/地區醫院/診所/藥局")
    tel: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="電話")
    address: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="地址")
    branch_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="分區業務組")
    special_type: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="特約類別代碼")
    service: Mapped[str | None] = mapped_column(Text, nullable=True, comment="服務項目")
    departments: Mapped[str | None] = mapped_column(Text, nullable=True, comment="診療科別")
    close_date: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="終止合約或歇業日期")
    schedule: Mapped[str | None] = mapped_column(Text, nullable=True, comment="固定看診時段")
    schedule_remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="時段備註")
    gov_area_no: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="縣市別代碼")
    contract_start: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="合約起日")

    # === 系統欄位 ===
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_nhi_hosp_name", "hosp_name"),
        Index("ix_nhi_hosp_type", "hosp_type"),
        Index("ix_nhi_gov_area", "gov_area_no"),
        Index("ix_nhi_departments", "departments", mysql_length=255),
    )

    def __repr__(self):
        return f"<NhiInstitution {self.hosp_id} {self.hosp_name}>"
