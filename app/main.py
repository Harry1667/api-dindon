"""FastAPI 主程式入口"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from app.config import settings
from app.api.webhook import router as webhook_router
from app.api.admin import router as admin_router
from app.api.test_harness import router as test_router
from app.api.live_test import router as live_test_router
from app.models.database import engine, Base

# 確保所有 Model 都被 import，create_all 才能建立資料表
import app.models.hospital  # noqa: F401
import app.models.user  # noqa: F401
import app.models.tracking_task  # noqa: F401
import app.models.clinic_progress  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.nhi_institution  # noqa: F401
import app.models.hospital_alias  # noqa: F401
import app.models.user_query_history  # noqa: F401
import app.models.department  # noqa: F401 (Department + DepartmentGuide)
import app.models.doctor  # noqa: F401
import app.models.tracking_feedback  # noqa: F401

# 設定 logging
logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    logger.info("🚀 醫院掛號排隊通知系統啟動中...")
    logger.info(
        f"📋 Feature Flags: env={settings.app_env}, "
        f"mock_hospital={settings.enable_mock_hospital}, "
        f"wanfang_scraper={settings.enable_wanfang_scraper}, "
        f"auto_create_tables={settings.enable_auto_create_tables}"
    )

    # 建立資料表（由 ENABLE_AUTO_CREATE_TABLES 控制，正式環境用 Alembic migration）
    if settings.enable_auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ 資料庫自動建表完成")
    else:
        logger.info("⏭️ 自動建表已停用，使用 Alembic migration")

    # 插入預設醫院資料
    await _seed_hospitals()
    await _seed_hospital_aliases()

    # 載入別名解析器到記憶體
    from app.services.hospital_resolver import hospital_resolver
    await hospital_resolver.load()

    yield

    # 關閉連線
    await engine.dispose()
    logger.info("👋 系統已關閉")


async def _seed_hospitals():
    """初始化醫院資料 — 以衛福部評鑑合格醫院名單為基準（醫學中心 28 + 區域醫院 78 = 106 家）"""
    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.hospital import Hospital

    # fmt: off
    # 欄位: code, name(衛福部官方全名), short_name(常用簡稱), level, city, district, phone,
    #       url(看診進度), adapter_name(爬蟲), is_active, scrape_interval
    seeds = [
        # ===================== 醫學中心（28 家）=====================
        {"code": "ntuh",               "name": "國立台灣大學醫學院附設醫院", "short_name": "台大醫院", "level": "醫學中心", "city": "臺北市", "district": "中正區", "phone": "02-23123456", "url": "https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo?vHospCode=T0", "adapter_name": "NtuhAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tsgh",               "name": "三軍總醫院附設民眾診療服務處及其汀州院區", "short_name": "三軍總醫院", "level": "醫學中心", "city": "臺北市", "district": "內湖區", "phone": "02-87923311", "url": "https://www2.ndmutsgh.edu.tw/NumberStatus/data/cache.json", "adapter_name": "TsghAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tpvgh",              "name": "臺北榮民總醫院", "short_name": "台北榮總", "level": "醫學中心", "city": "臺北市", "district": "北投區", "phone": "02-28712121", "url": "https://m.vghtpe.gov.tw:6443/MobileWeb/roomsta/", "adapter_name": "TpvghAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "changgung-taipei",   "name": "長庚醫療財團法人台北長庚紀念醫院", "short_name": "台北長庚", "level": "醫學中心", "city": "臺北市", "district": "松山區", "phone": "02-27135211", "url": "https://register.cgmh.org.tw/Progress/1", "adapter_name": "ChangGungAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "cathay",             "name": "國泰醫療財團法人國泰綜合醫院", "short_name": "國泰醫院", "level": "醫學中心", "city": "臺北市", "district": "大安區", "phone": "02-27082121", "url": "https://reg.cgh.org.tw/tw/reg/RealTimeTable.jsp", "adapter_name": "CathayAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "mackay-taipei",      "name": "台灣基督長老教會馬偕醫療財團法人馬偕紀念醫院", "short_name": "馬偕醫院(台北)", "level": "醫學中心", "city": "臺北市", "district": "中山區", "phone": "02-25433535", "url": "https://www.mmh.org.tw/progressstatus.php", "adapter_name": "MackayAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "shinkong",           "name": "新光醫療財團法人新光吳火獅紀念醫院", "short_name": "新光醫院", "level": "醫學中心", "city": "臺北市", "district": "士林區", "phone": "02-28332211", "url": "https://www.skh.org.tw/regis_api/AppointmentProgress", "adapter_name": "ShinkongAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tmuh",               "name": "臺北醫學大學附設醫院", "short_name": "北醫附醫", "level": "醫學中心", "city": "臺北市", "district": "信義區", "phone": "02-27372181", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "wanfang",            "name": "臺北市立萬芳醫院-委託臺北醫學大學辦理", "short_name": "萬芳醫院", "level": "醫學中心", "city": "臺北市", "district": "文山區", "phone": "02-29307930", "url": "https://wwww.wanfang.gov.tw/reg/register_visits_cload3.aspx", "adapter_name": "WanfangAdapter", "is_active": settings.enable_wanfang_scraper, "scrape_interval": 60},  # 由 ENABLE_WANFANG_SCRAPER 控制
        {"code": "femh",               "name": "醫療財團法人徐元智先生醫藥基金會亞東紀念醫院", "short_name": "亞東醫院", "level": "醫學中心", "city": "新北市", "district": "板橋區", "phone": "02-89667000", "url": "https://www.femh.org.tw/visit/visit.aspx?Action=9", "adapter_name": "FemhAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tzuchi-taipei",      "name": "佛教慈濟醫療財團法人台北慈濟醫院", "short_name": "台北慈濟醫院", "level": "醫學中心", "city": "新北市", "district": "新店區", "phone": "02-66289779", "url": "https://reg-prod.tzuchi-healthcare.org.tw/tchw/HIS5OpdReg/OpdProgress?Loc=TC", "adapter_name": "TzuchiAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "mackay-tamsui",      "name": "台灣基督長老教會馬偕醫療財團法人淡水馬偕紀念醫院", "short_name": "馬偕醫院(淡水)", "level": "醫學中心", "city": "新北市", "district": "淡水區", "phone": "02-28094661", "url": "https://www.mmh.org.tw/progressstatus.php", "adapter_name": "MackayAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "shuangho",           "name": "衛生福利部雙和醫院(委託臺北醫學大學興建經營)", "short_name": "雙和醫院", "level": "醫學中心", "city": "新北市", "district": "中和區", "phone": "02-22490088", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "changgung-linkou",   "name": "長庚醫療財團法人林口長庚紀念醫院", "short_name": "林口長庚", "level": "醫學中心", "city": "桃園市", "district": "龜山區", "phone": "03-3281200", "url": "https://register.cgmh.org.tw/Progress/3", "adapter_name": "ChangGungAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "changgung-taoyuan", "name": "長庚醫療財團法人桃園長庚紀念醫院", "short_name": "桃園長庚", "level": "區域醫院", "city": "桃園市", "district": "龜山區", "phone": "03-3196200", "url": "https://register.cgmh.org.tw/Progress/5", "adapter_name": "ChangGungAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "ntuh-hsinchu",       "name": "國立臺灣大學醫學院附設醫院新竹臺大分院新竹醫院", "short_name": "新竹台大", "level": "醫學中心", "city": "新竹市", "district": "北區", "phone": "03-5326151", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tcvgh",              "name": "臺中榮民總醫院", "short_name": "台中榮總", "level": "醫學中心", "city": "臺中市", "district": "西屯區", "phone": "04-23592525", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "csh",                "name": "中山醫學大學附設醫院", "short_name": "中山醫大附醫", "level": "醫學中心", "city": "臺中市", "district": "南區", "phone": "04-24739595", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "cmuh",               "name": "中國醫藥大學附設醫院", "short_name": "中國醫", "level": "醫學中心", "city": "臺中市", "district": "北區", "phone": "04-22052121", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "cch",                "name": "彰化基督教醫療財團法人彰化基督教醫院", "short_name": "彰基", "level": "醫學中心", "city": "彰化縣", "district": "彰化市", "phone": "04-7238595", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ntuh-yunlin",        "name": "國立臺灣大學醫學院附設醫院雲林分院及其虎尾院區", "short_name": "台大雲林", "level": "醫學中心", "city": "雲林縣", "district": "斗六市", "phone": "05-5323911", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "changgung-yunlin",  "name": "長庚醫療財團法人雲林長庚紀念醫院", "short_name": "雲林長庚", "level": "區域醫院", "city": "雲林縣", "district": "麥寮鄉", "phone": "05-6915151", "url": "https://register.cgmh.org.tw/Progress/M", "adapter_name": "ChangGungAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tzuchi-dalin",       "name": "佛教慈濟醫療財團法人大林慈濟醫院", "short_name": "大林慈濟", "level": "醫學中心", "city": "嘉義縣", "district": "大林鎮", "phone": "05-2648000", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "nckuh",              "name": "國立成功大學醫學院附設醫院", "short_name": "成大醫院", "level": "醫學中心", "city": "臺南市", "district": "北區", "phone": "06-2353535", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "chimei",             "name": "奇美醫療財團法人奇美醫院及其樹林院區", "short_name": "奇美醫院", "level": "醫學中心", "city": "臺南市", "district": "永康區", "phone": "06-2812811", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ksvgh",              "name": "高雄榮民總醫院", "short_name": "高雄榮總", "level": "醫學中心", "city": "高雄市", "district": "左營區", "phone": "07-3422121", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "changgung-kaohsiung","name": "長庚醫療財團法人高雄長庚紀念醫院", "short_name": "高雄長庚", "level": "醫學中心", "city": "高雄市", "district": "鳥松區", "phone": "07-7317123", "url": "https://register.cgmh.org.tw/Progress/8", "adapter_name": "ChangGungAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "changgung-fengshan","name": "長庚醫療財團法人鳳山長庚紀念醫院", "short_name": "鳳山長庚", "level": "區域醫院", "city": "高雄市", "district": "鳳山區", "phone": "07-7418151", "url": "https://register.cgmh.org.tw/Progress/T", "adapter_name": "ChangGungAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "edah",               "name": "義大醫療財團法人義大醫院", "short_name": "義大醫院", "level": "醫學中心", "city": "高雄市", "district": "燕巢區", "phone": "07-6150011", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "kmuh",               "name": "財團法人私立高雄醫學大學附設中和紀念醫院", "short_name": "高醫附醫", "level": "醫學中心", "city": "高雄市", "district": "三民區", "phone": "07-3121101", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tzuchi-hualien",     "name": "佛教慈濟醫療財團法人花蓮慈濟醫院", "short_name": "花蓮慈濟", "level": "醫學中心", "city": "花蓮縣", "district": "花蓮市", "phone": "03-8561825", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        # ===================== 區域醫院 — 已接入 =====================
        {"code": "ntuh-children",      "name": "國立台灣大學醫學院附設醫院（兒童醫院）", "short_name": "台大兒童醫院", "level": "區域醫院", "city": "臺北市", "district": "中正區", "phone": "02-23123456", "url": "https://reg.ntuh.gov.tw/WebReg/WebReg/ClinicCurrentLightNo?vHospCode=CH", "adapter_name": "NtuhAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "chgh",               "name": "振興醫療財團法人振興醫院", "short_name": "振興醫院", "level": "區域醫院", "city": "臺北市", "district": "北投區", "phone": "02-28264400", "url": "https://reg.chgh.org.tw/allroom_cload.aspx", "adapter_name": "ChghAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tzuchi-xindian",     "name": "佛教慈濟醫療財團法人台北慈濟醫院（新店院區）", "short_name": "慈濟新店", "level": "區域醫院", "city": "新北市", "district": "新店區", "phone": "02-66289779", "url": "https://reg-prod.tzuchi-healthcare.org.tw/tchw/HIS5OpdReg/OpdProgress?Loc=XD", "adapter_name": "TzuchiAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tph",                "name": "衛生福利部臺北醫院", "short_name": "衛福部臺北醫院", "level": "區域醫院", "city": "新北市", "district": "新莊區", "phone": "02-22765566", "url": "https://nreg.tph.mohw.gov.tw/OReg/VisitProgressPage", "adapter_name": "TphAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "newtaipei-banqiao",  "name": "新北市立聯合醫院及其板橋院區", "short_name": "新北聯醫(板橋)", "level": "區域醫院", "city": "新北市", "district": "板橋區", "phone": "02-29829111", "url": "https://data.ntpc.gov.tw/api/datasets/00f8fa51-cedc-4c1d-88b0-58c55f740b79/json", "adapter_name": "NewTaipeiUnitedAdapter", "is_active": True, "scrape_interval": 300},
        {"code": "newtaipei-sanchong", "name": "新北市立聯合醫院及其板橋院區（三重）", "short_name": "新北聯醫(三重)", "level": "區域醫院", "city": "新北市", "district": "三重區", "phone": "02-29829111", "url": "https://data.ntpc.gov.tw/api/datasets/0abdf2d0-3246-4614-b715-d4ed6631eb16/json", "adapter_name": "NewTaipeiUnitedAdapter", "is_active": True, "scrape_interval": 300},
        {"code": "kaohsiung-united",   "name": "高雄市立聯合醫院", "short_name": "高雄聯合醫院", "level": "區域醫院", "city": "高雄市", "district": "鼓山區", "phone": "07-5552565", "url": "https://api.kcg.gov.tw/api/service/Get/8cd9aba3-bbbc-4801-b267-5e9ee9ff50a6", "adapter_name": "KaohsiungUnitedAdapter", "is_active": True, "scrape_interval": 60},
        # ===================== 區域醫院 — 未接入（依衛福部名單）=====================
        {"code": "keelung-mohw",       "name": "衛生福利部基隆醫院", "short_name": "部基", "level": "區域醫院", "city": "基隆市", "district": "信義區", "phone": "02-24292525", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "changgung-keelung",  "name": "長庚醫療財團法人基隆長庚紀念醫院及其情人湖院區", "short_name": "基隆長庚", "level": "區域醫院", "city": "基隆市", "district": "安樂區", "phone": "02-24313131", "url": "https://register.cgmh.org.tw/Progress/2", "adapter_name": "ChangGungAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tpech-zhongxing",    "name": "臺北市立聯合醫院中興院區", "short_name": "聯醫中興", "level": "區域醫院", "city": "臺北市", "district": "大同區", "phone": "02-25523234", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tpech-yangming",     "name": "臺北市立聯合醫院陽明院區", "short_name": "聯醫陽明", "level": "區域醫院", "city": "臺北市", "district": "士林區", "phone": "02-28353456", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tpech-heping",       "name": "臺北市立聯合醫院和平婦幼院區及其婦幼院區", "short_name": "聯醫和平", "level": "區域醫院", "city": "臺北市", "district": "中正區", "phone": "02-23889595", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tpech-zhongxiao",    "name": "臺北市立聯合醫院忠孝院區", "short_name": "聯醫忠孝", "level": "區域醫院", "city": "臺北市", "district": "南港區", "phone": "02-27861288", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tpech-renai",        "name": "臺北市立聯合醫院仁愛院區", "short_name": "聯醫仁愛", "level": "區域醫院", "city": "臺北市", "district": "大安區", "phone": "02-27093600", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ntuh-cancer",        "name": "國立臺灣大學醫學院附設醫院癌醫中心分院", "short_name": "台大癌醫", "level": "區域醫院", "city": "臺北市", "district": "大安區", "phone": "02-23123456", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tsgh-songshan",      "name": "三軍總醫院松山分院附設民眾診療服務處", "short_name": "三總松山", "level": "區域醫院", "city": "臺北市", "district": "松山區", "phone": "02-27642151", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tah",                "name": "基督復臨安息日會醫療財團法人臺安醫院", "short_name": "臺安醫院", "level": "區域醫院", "city": "臺北市", "district": "松山區", "phone": "02-27718151", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "kfsyscc",            "name": "醫療財團法人辜公亮基金會和信治癌中心醫院", "short_name": "和信醫院", "level": "區域醫院", "city": "臺北市", "district": "北投區", "phone": "02-28970011", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "eck",                "name": "行天宮醫療志業醫療財團法人恩主公醫院", "short_name": "恩主公醫院", "level": "區域醫院", "city": "新北市", "district": "三峽區", "phone": "02-26723456", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "cathay-xizhi",       "name": "國泰醫療財團法人汐止國泰綜合醫院", "short_name": "汐止國泰", "level": "區域醫院", "city": "新北市", "district": "汐止區", "phone": "02-26482121", "url": "https://reg.cgh.org.tw/tw/reg/RealTimeTable.jsp", "adapter_name": "CathayAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "changgung-tucheng",  "name": "新北市立土城醫院(委託長庚醫療財團法人興建經營)", "short_name": "土城長庚", "level": "區域醫院", "city": "新北市", "district": "土城區", "phone": "02-22630588", "url": "https://register.cgmh.org.tw/Progress/V", "adapter_name": "ChangGungAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "cth",                "name": "天主教耕莘醫療財團法人耕莘醫院", "short_name": "耕莘醫院", "level": "區域醫院", "city": "新北市", "district": "新店區", "phone": "02-22193391", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "fjuh",               "name": "輔仁大學學校財團法人輔仁大學附設醫院", "short_name": "輔大醫院", "level": "區域醫院", "city": "新北市", "district": "泰山區", "phone": "02-85128888", "url": "https://www.hospital.fju.edu.tw/Process", "adapter_name": "FjuhAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tygh-mohw",          "name": "衛生福利部桃園醫院", "short_name": "部桃", "level": "區域醫院", "city": "桃園市", "district": "桃園區", "phone": "03-3699721", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "aftygh",             "name": "國軍桃園總醫院附設民眾診療服務處", "short_name": "國軍桃園", "level": "區域醫院", "city": "桃園市", "district": "龍潭區", "phone": "03-4799595", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tpvgh-taoyuan",      "name": "臺北榮民總醫院桃園分院", "short_name": "北榮桃園", "level": "區域醫院", "city": "桃園市", "district": "桃園區", "phone": "03-3384889", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tcmg",               "name": "天成醫療社團法人天晟醫院", "short_name": "天晟醫院", "level": "區域醫院", "city": "桃園市", "district": "中壢區", "phone": "03-4629292", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "sph",                "name": "沙爾德聖保祿修女會醫療財團法人聖保祿醫院", "short_name": "聖保祿醫院", "level": "區域醫院", "city": "桃園市", "district": "桃園區", "phone": "03-3613141", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ms",                 "name": "敏盛綜合醫院", "short_name": "敏盛醫院", "level": "區域醫院", "city": "桃園市", "district": "桃園區", "phone": "03-3179599", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "landseed",           "name": "聯新國際醫院", "short_name": "聯新醫院", "level": "區域醫院", "city": "桃園市", "district": "平鎮區", "phone": "03-4941234", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "mackay-hsinchu",     "name": "台灣基督長老教會馬偕醫療財團法人新竹馬偕紀念醫院", "short_name": "新竹馬偕", "level": "區域醫院", "city": "新竹市", "district": "東區", "phone": "03-6119595", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "mackay-children-hc", "name": "新竹市立馬偕兒童醫院", "short_name": "新竹馬偕兒童", "level": "區域醫院", "city": "新竹市", "district": "東區", "phone": "03-6119595", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ntuh-biomedical",    "name": "國立臺灣大學醫學院附設醫院新竹臺大分院生醫醫院及其竹東院區", "short_name": "台大生醫竹北", "level": "區域醫院", "city": "新竹縣", "district": "竹北市", "phone": "03-6142000", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tyh",                "name": "東元醫療社團法人東元綜合醫院", "short_name": "東元醫院", "level": "區域醫院", "city": "新竹縣", "district": "竹北市", "phone": "03-5527000", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "miaoli-mohw",        "name": "衛生福利部苗栗醫院", "short_name": "部苗", "level": "區域醫院", "city": "苗栗縣", "district": "苗栗市", "phone": "037-261920", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "weigong",            "name": "為恭醫療財團法人為恭紀念醫院及其東興院區", "short_name": "為恭醫院", "level": "區域醫院", "city": "苗栗縣", "district": "頭份市", "phone": "037-676811", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "taichung-mohw",      "name": "衛生福利部臺中醫院", "short_name": "部中", "level": "區域醫院", "city": "臺中市", "district": "西區", "phone": "04-22294411", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "fyh-mohw",           "name": "衛生福利部豐原醫院", "short_name": "部豐", "level": "區域醫院", "city": "臺中市", "district": "豐原區", "phone": "04-25271180", "url": "https://nreg.fyh.mohw.gov.tw/OReg/VisitProgressPage", "adapter_name": "MohwOregAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "ndmctsgh-tc",        "name": "國軍臺中總醫院附設民眾診療服務處", "short_name": "國軍台中", "level": "區域醫院", "city": "臺中市", "district": "太平區", "phone": "04-23934191", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "lshosp",             "name": "林新醫療社團法人林新醫院", "short_name": "林新醫院", "level": "區域醫院", "city": "臺中市", "district": "南屯區", "phone": "04-22586688", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ljci",               "name": "李綜合醫療社團法人大甲李綜合醫院", "short_name": "大甲李綜合", "level": "區域醫院", "city": "臺中市", "district": "大甲區", "phone": "04-26862288", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ktgh",               "name": "光田醫療社團法人光田綜合醫院及其大甲院區", "short_name": "光田醫院", "level": "區域醫院", "city": "臺中市", "district": "沙鹿區", "phone": "04-26625111", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "sltung",             "name": "童綜合醫療社團法人童綜合醫院及其沙鹿院區", "short_name": "童綜合醫院", "level": "區域醫院", "city": "臺中市", "district": "梧棲區", "phone": "04-26581919", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tzuchi-taichung",    "name": "佛教慈濟醫療財團法人台中慈濟醫院", "short_name": "台中慈濟", "level": "區域醫院", "city": "臺中市", "district": "潭子區", "phone": "04-36060666", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "jah",                "name": "仁愛醫療財團法人大里仁愛醫院", "short_name": "大里仁愛", "level": "區域醫院", "city": "臺中市", "district": "大里區", "phone": "04-24819900", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "auh",                "name": "亞洲大學附屬醫院", "short_name": "亞大醫院", "level": "區域醫院", "city": "臺中市", "district": "霧峰區", "phone": "04-23323456", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ccgh",               "name": "澄清綜合醫院", "short_name": "澄清醫院", "level": "區域醫院", "city": "臺中市", "district": "中區", "phone": "04-24632000", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ccgh-zhonggang",     "name": "澄清綜合醫院中港分院", "short_name": "澄清中港", "level": "區域醫院", "city": "臺中市", "district": "西屯區", "phone": "04-24632000", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "changhua-mohw",      "name": "衛生福利部彰化醫院", "short_name": "部彰", "level": "區域醫院", "city": "彰化縣", "district": "埔心鄉", "phone": "04-8298686", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "scmh",               "name": "秀傳醫療社團法人秀傳紀念醫院", "short_name": "彰化秀傳", "level": "區域醫院", "city": "彰化縣", "district": "彰化市", "phone": "04-7256166", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "cbshow",             "name": "秀傳醫療財團法人彰濱秀傳紀念醫院", "short_name": "彰濱秀傳", "level": "區域醫院", "city": "彰化縣", "district": "鹿港鎮", "phone": "04-7813888", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "nantou-mohw",        "name": "衛生福利部南投醫院及其中興院區", "short_name": "部投", "level": "區域醫院", "city": "南投縣", "district": "南投市", "phone": "049-2231150", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "pch",                "name": "埔基醫療財團法人埔里基督教醫院", "short_name": "埔基", "level": "區域醫院", "city": "南投縣", "district": "埔里鎮", "phone": "049-2912151", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "cmuh-beigang",       "name": "中國醫藥大學北港附設醫院", "short_name": "中醫北港", "level": "區域醫院", "city": "雲林縣", "district": "北港鎮", "phone": "05-7837901", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tcvgh-chiayi",       "name": "臺中榮民總醫院嘉義分院", "short_name": "嘉榮", "level": "區域醫院", "city": "嘉義市", "district": "西區", "phone": "05-2359630", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "cych",               "name": "戴德森醫療財團法人嘉義基督教醫院", "short_name": "嘉基", "level": "區域醫院", "city": "嘉義市", "district": "東區", "phone": "05-2765041", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "stm",                "name": "天主教中華聖母修女會醫療財團法人天主教聖馬爾定醫院及其民權院區", "short_name": "聖馬爾定", "level": "區域醫院", "city": "嘉義市", "district": "東區", "phone": "05-2756000", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "changgung-chiayi",   "name": "長庚醫療財團法人嘉義長庚紀念醫院", "short_name": "嘉義長庚", "level": "區域醫院", "city": "嘉義縣", "district": "朴子市", "phone": "05-3621000", "url": "https://register.cgmh.org.tw/Progress/6", "adapter_name": "ChangGungAdapter", "is_active": True, "scrape_interval": 60},
        {"code": "tainan-mohw",        "name": "衛生福利部臺南醫院", "short_name": "部南", "level": "區域醫院", "city": "臺南市", "district": "中西區", "phone": "06-2200055", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tmh",                "name": "台南市立醫院(委託秀傳醫療社團法人經營)", "short_name": "台南市醫", "level": "區域醫院", "city": "臺南市", "district": "東區", "phone": "06-2609926", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "sinlau",             "name": "台灣基督長老教會新樓醫療財團法人台南新樓醫院", "short_name": "新樓醫院", "level": "區域醫院", "city": "臺南市", "district": "東區", "phone": "06-2748316", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "chimei-liuying",     "name": "奇美醫療財團法人柳營奇美醫院", "short_name": "柳營奇美", "level": "區域醫院", "city": "臺南市", "district": "柳營區", "phone": "06-6226999", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "annan",              "name": "臺南市立安南醫院-委託中國醫藥大學興建經營", "short_name": "安南醫院", "level": "區域醫院", "city": "臺南市", "district": "安南區", "phone": "06-3553111", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "afkh-zuoying",       "name": "國軍左營總醫院附設民眾診療服務處", "short_name": "國軍左營", "level": "區域醫院", "city": "高雄市", "district": "左營區", "phone": "07-5817121", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "afkh",               "name": "國軍高雄總醫院附設民眾診療服務處", "short_name": "國軍高雄", "level": "區域醫院", "city": "高雄市", "district": "苓雅區", "phone": "07-7496751", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "jcgh",               "name": "阮綜合醫療社團法人阮綜合醫院", "short_name": "阮綜合", "level": "區域醫院", "city": "高雄市", "district": "苓雅區", "phone": "07-3351121", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "kmhk",               "name": "高雄市立小港醫院（委託財團法人私立高雄醫學大學經營）", "short_name": "小港醫院", "level": "區域醫院", "city": "高雄市", "district": "小港區", "phone": "07-8036783", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "edah-cancer",        "name": "義大醫療財團法人義大癌治療醫院", "short_name": "義大癌治療", "level": "區域醫院", "city": "高雄市", "district": "小港區", "phone": "07-6150011", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "pingtung-mohw",      "name": "衛生福利部屏東醫院", "short_name": "部屏", "level": "區域醫院", "city": "屏東縣", "district": "屏東市", "phone": "08-7363011", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "poja",               "name": "寶建醫療社團法人寶建醫院", "short_name": "寶建醫院", "level": "區域醫院", "city": "屏東縣", "district": "屏東市", "phone": "08-7665995", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ptch",               "name": "屏基醫療財團法人屏東基督教醫院及其瑞光院區", "short_name": "屏基", "level": "區域醫院", "city": "屏東縣", "district": "屏東市", "phone": "08-7368686", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "fy",                 "name": "輔英科技大學附設醫院", "short_name": "輔英", "level": "區域醫院", "city": "屏東縣", "district": "東港鎮", "phone": "08-8329966", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ymuh",               "name": "國立陽明交通大學附設醫院及其新民院區", "short_name": "陽交大附醫", "level": "區域醫院", "city": "宜蘭縣", "district": "宜蘭市", "phone": "03-9325192", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "pohai",              "name": "醫療財團法人羅許基金會羅東博愛醫院", "short_name": "羅東博愛", "level": "區域醫院", "city": "宜蘭縣", "district": "羅東鎮", "phone": "03-9543131", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "smh",                "name": "天主教靈醫會醫療財團法人羅東聖母醫院", "short_name": "羅東聖母", "level": "區域醫院", "city": "宜蘭縣", "district": "羅東鎮", "phone": "03-9544106", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "afhl",               "name": "國軍花蓮總醫院附設民眾診療服務處", "short_name": "國軍花蓮", "level": "區域醫院", "city": "花蓮縣", "district": "新城鄉", "phone": "03-8263151", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "mch",                "name": "臺灣基督教門諾會醫療財團法人門諾醫院", "short_name": "門諾醫院", "level": "區域醫院", "city": "花蓮縣", "district": "花蓮市", "phone": "03-8241234", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "mackay-taitung",     "name": "台灣基督長老教會馬偕醫療財團法人台東馬偕紀念醫院", "short_name": "台東馬偕", "level": "區域醫院", "city": "臺東縣", "district": "臺東市", "phone": "089-310150", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        # ===================== 地區醫院 — 六都 =====================
        # --- 臺北市 ---
        {"code": "siyuan",             "name": "西園醫療社團法人西園醫院", "short_name": "西園醫院", "level": "地區醫院", "city": "臺北市", "district": "萬華區", "phone": "02-23076968", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "pojen",              "name": "博仁綜合醫院", "short_name": "博仁醫院", "level": "地區醫院", "city": "臺北市", "district": "松山區", "phone": "02-25786677", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        # --- 新北市 ---
        {"code": "losheng",            "name": "衛生福利部樂生療養院", "short_name": "樂生療養院", "level": "地區醫院", "city": "新北市", "district": "新莊區", "phone": "02-82006600", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "cth-yonghe",         "name": "天主教耕莘醫療財團法人永和耕莘醫院", "short_name": "永和耕莘", "level": "地區醫院", "city": "新北市", "district": "永和區", "phone": "02-29286060", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "cth-ankang",         "name": "天主教耕莘醫療財團法人耕莘醫院安康院區", "short_name": "安康耕莘", "level": "地區醫院", "city": "新北市", "district": "新店區", "phone": "02-22123066", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        # --- 桃園市 ---
        {"code": "changgung-taoyuan-d","name": "長庚醫療財團法人桃園長庚紀念醫院及其長青院區", "short_name": "桃園長庚長青", "level": "地區醫院", "city": "桃園市", "district": "龜山區", "phone": "03-3196200", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "tcmg-yangmei",       "name": "天成醫院", "short_name": "天成醫院楊梅", "level": "地區醫院", "city": "桃園市", "district": "楊梅區", "phone": "03-4782350", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "yiren",              "name": "怡仁綜合醫院", "short_name": "怡仁醫院", "level": "地區醫院", "city": "桃園市", "district": "楊梅區", "phone": "03-4855566", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        # --- 臺中市 ---
        {"code": "lshosp-wuri",        "name": "林新醫療社團法人烏日林新醫院", "short_name": "烏日林新", "level": "地區醫院", "city": "臺中市", "district": "烏日區", "phone": "04-23388766", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        # --- 臺南市 ---
        {"code": "ccd",                "name": "衛生福利部胸腔病院", "short_name": "部胸", "level": "地區醫院", "city": "臺南市", "district": "仁德區", "phone": "06-2705911", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "ksvgh-tainan",       "name": "高雄榮民總醫院臺南分院", "short_name": "南榮", "level": "地區醫院", "city": "臺南市", "district": "永康區", "phone": "06-3125101", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "sinlau-madou",       "name": "台灣基督長老教會新樓醫療財團法人麻豆新樓醫院", "short_name": "麻豆新樓", "level": "地區醫院", "city": "臺南市", "district": "麻豆區", "phone": "06-5702228", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "chimei-jiali",       "name": "奇美醫療財團法人佳里奇美醫院", "short_name": "佳里奇美", "level": "地區醫院", "city": "臺南市", "district": "佳里區", "phone": "06-7263333", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "kgh",                "name": "郭綜合醫院", "short_name": "郭綜合", "level": "地區醫院", "city": "臺南市", "district": "中西區", "phone": "06-2221111", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        # --- 高雄市 ---
        {"code": "cishan-mohw",        "name": "衛生福利部旗山醫院", "short_name": "部旗", "level": "地區醫院", "city": "高雄市", "district": "旗山區", "phone": "07-6613811", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "stcmf",              "name": "天主教聖功醫療財團法人聖功醫院", "short_name": "聖功醫院", "level": "地區醫院", "city": "高雄市", "district": "苓雅區", "phone": "07-2238153", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "changgung-fengshan-d","name": "高雄市立鳳山醫院（委託長庚醫療財團法人經營）", "short_name": "鳳山市立醫院", "level": "地區醫院", "city": "高雄市", "district": "鳳山區", "phone": "07-7418151", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
        {"code": "jianren",            "name": "健仁醫院", "short_name": "健仁醫院", "level": "地區醫院", "city": "高雄市", "district": "楠梓區", "phone": "07-3517166", "url": None, "adapter_name": None, "is_active": False, "scrape_interval": 60},
    ]
    # fmt: on

    async with async_session() as session:
        for seed in seeds:
            result = await session.execute(
                select(Hospital).where(Hospital.code == seed["code"])
            )
            existing = result.scalar_one_or_none()
            if not existing:
                session.add(Hospital(
                    code=seed["code"],
                    name=seed["name"],
                    short_name=seed["short_name"],
                    level=seed["level"],
                    city=seed["city"],
                    district=seed["district"],
                    phone=seed.get("phone"),
                    url=seed.get("url"),
                    adapter_name=seed.get("adapter_name"),
                    is_active=seed.get("is_active", False),
                    scrape_interval=seed.get("scrape_interval", 60),
                ))
                logger.info(f"已新增醫院: {seed['short_name']}")
            else:
                # 更新已存在的醫院（補充新欄位）
                existing.name = seed["name"]
                existing.short_name = seed["short_name"]
                existing.level = seed["level"]
                existing.city = seed["city"]
                existing.district = seed["district"]
                if seed.get("phone"):
                    existing.phone = seed["phone"]
                if seed.get("url"):
                    existing.url = seed["url"]
                if seed.get("adapter_name"):
                    existing.adapter_name = seed["adapter_name"]
        await session.commit()
    logger.info(f"✅ 醫院資料初始化完成（{len(seeds)} 家）")


async def _seed_hospital_aliases():
    """初始化醫院別名資料 — 讓使用者可以用簡稱/俗稱查詢醫院"""
    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.hospital_alias import HospitalAlias

    # hospital_code → [別名列表]
    # 別名可重複：例如「長庚」同時指向多家長庚，LINE 查詢時會列出所有匹配的醫院
    # 規則：short_name 不需要加（resolver 會自動從 hospitals.short_name 載入）
    alias_map = {
        # ===== 台大系 =====（「台大」共用）
        "ntuh":                ["台大", "臺大", "臺大醫院", "台大醫院", "台大總院", "台大本院"],
        "ntuh-children":       ["台大", "台大兒童", "臺大兒童", "台大兒醫", "台大兒童醫院"],
        "ntuh-cancer":         ["台大", "台大癌醫", "臺大癌醫", "癌醫中心"],
        # ===== 榮總系 =====（「榮總」共用）
        "tpvgh":               ["榮總", "北榮", "台北榮總", "臺北榮總", "台北榮民"],
        # ===== 三總系 =====（「三總」共用）
        "tsgh":                ["三總", "三軍", "三軍總", "三軍總醫院", "內湖三總"],
        "tsgh-songshan":       ["三總", "三總松山", "松山三總", "松山分院"],
        # ===== 長庚系 =====（「長庚」共用）
        "changgung-taipei":    ["長庚", "台北長庚", "北長庚", "台北長庚醫院"],
        "changgung-linkou":    ["長庚", "林口長庚", "林口", "長庚總院", "長庚醫院"],
        "changgung-keelung":   ["長庚", "基隆長庚", "基隆長庚醫院"],
        "changgung-taoyuan":   ["長庚", "桃園長庚", "桃園長庚醫院"],
        "changgung-yunlin":    ["長庚", "雲林長庚", "麥寮長庚"],
        "changgung-chiayi":    ["長庚", "嘉義長庚", "嘉義長庚醫院"],
        "changgung-kaohsiung": ["長庚", "高雄長庚", "高長庚", "高雄長庚醫院"],
        "changgung-fengshan":  ["長庚", "鳳山長庚", "鳳山醫院"],
        "changgung-tucheng":   ["長庚", "土城長庚", "土城醫院"],
        # ===== 馬偕系 =====（「馬偕」共用）
        "mackay-taipei":       ["馬偕", "台北馬偕", "馬偕台北", "臺北馬偕", "馬偕醫院", "馬偕總院"],
        "mackay-tamsui":       ["馬偕", "淡水馬偕", "馬偕淡水"],
        # ===== 國泰系 =====（「國泰」共用）
        "cathay":              ["國泰", "國泰總院", "台北國泰", "國泰醫院", "國泰綜合"],
        "cathay-xizhi":        ["國泰", "汐止國泰", "國泰汐止"],
        # ===== 慈濟系 =====（「慈濟」共用）
        "tzuchi-taipei":       ["慈濟", "台北慈濟", "慈濟台北", "新店慈濟", "慈濟醫院"],
        "tzuchi-xindian":      ["慈濟", "慈濟新店"],
        # ===== 萬芳 =====
        "wanfang":             ["萬芳", "萬芳醫院"],
        # ===== 新光 =====
        "shinkong":            ["新光", "新光醫院", "新光吳火獅"],
        # ===== 振興 =====
        "chgh":                ["振興", "振興醫院"],
        # ===== 北醫系 =====（「北醫」共用）
        "tmuh":                ["北醫", "北醫附醫", "臺北醫學", "北醫附設"],
        "shuangho":            ["北醫", "雙和", "雙和醫院"],
        # ===== 亞東 =====
        "femh":                ["亞東", "亞東醫院", "亞東紀念", "板橋亞東"],
        # ===== 衛福部系 =====（「部立」共用概念）
        "tph":                 ["部立", "部北", "臺北醫院", "台北醫院", "衛福部北", "衛福部臺北"],
        "fyh-mohw":            ["部立", "部豐", "豐原醫院", "衛福部豐原"],
        "keelung-mohw":        ["部立", "部基", "基隆醫院", "衛福部基隆"],
        "tygh-mohw":           ["部立", "部桃", "桃園醫院", "衛福部桃園"],
        "miaoli-mohw":         ["部立", "部苗", "苗栗醫院", "衛福部苗栗"],
        "taichung-mohw":       ["部立", "部中", "臺中醫院", "衛福部臺中"],
        "changhua-mohw":       ["部立", "部彰", "彰化醫院", "衛福部彰化"],
        "nantou-mohw":         ["部立", "部投", "南投醫院", "衛福部南投"],
        "tainan-mohw":         ["部立", "部南", "臺南醫院", "衛福部臺南"],
        "pingtung-mohw":       ["部立", "部屏", "屏東醫院", "衛福部屏東"],
        # ===== 新北聯醫 =====（「新北聯醫」「聯醫」共用）
        "newtaipei-banqiao":   ["新北聯醫", "聯醫", "板橋聯醫", "聯醫板橋", "板橋醫院"],
        "newtaipei-sanchong":  ["新北聯醫", "聯醫", "三重聯醫", "聯醫三重", "三重醫院"],
        # ===== 高雄聯醫 =====
        "kaohsiung-united":    ["高雄聯醫", "高聯醫", "高雄聯合", "高雄市聯合"],
        # ===== 輔大 =====
        "fjuh":                ["輔大", "輔大醫院", "輔仁", "輔仁醫院"],
        # ===== 台中系 =====
        "tcvgh":               ["台中榮總", "臺中榮總", "中榮"],
        "csh":                 ["中山醫", "中山附醫", "中山醫大"],
        "cmuh":                ["中國醫", "中國附醫", "中國醫藥"],
        # ===== 彰化 =====
        "cch":                 ["彰基", "彰化基督教", "彰基醫院"],
        # ===== 台南系 =====
        "nckuh":               ["成大", "成大醫院", "成功大學附醫"],
        "chimei":              ["奇美", "奇美醫院", "永康奇美"],
        # ===== 高雄系 =====
        "ksvgh":               ["高榮", "高雄榮總", "高雄榮民"],
        "kmuh":                ["高醫", "高醫附醫", "高雄醫學"],
        "edah":                ["義大", "義大醫院"],
        # ===== 嘉義系 =====
        "cych":                ["嘉基", "嘉義基督教"],
        "stm":                 ["聖馬", "聖馬爾定"],
        "tcvgh-chiayi":        ["嘉榮", "嘉義榮總", "臺中榮總嘉義"],
        # ===== 花東系 =====
        "tzuchi-hualien":      ["慈濟", "花蓮慈濟", "慈濟花蓮"],
        "tzuchi-dalin":        ["慈濟", "大林慈濟", "慈濟大林"],
        "mackay-taitung":      ["馬偕", "台東馬偕", "馬偕台東"],
        "mch":                 ["門諾", "門諾醫院", "花蓮門諾"],
        # ===== 宜蘭系 =====
        "ymuh":                ["陽交大", "陽明交大", "宜蘭陽明"],
        "pohai":               ["博愛", "羅東博愛", "博愛醫院"],
        "smh":                 ["聖母", "羅東聖母", "聖母醫院"],
        # ===== 新北其他 =====
        "eck":                 ["恩主公", "恩主公醫院", "三峽恩主公"],
        "cth":                 ["耕莘", "耕莘醫院", "新店耕莘"],
        "changgung-tucheng":   ["土城長庚", "土城醫院"],
        # ===== 桃園其他 =====
        "aftygh":              ["國軍桃園", "桃園國軍"],
        "tpvgh-taoyuan":       ["北榮桃園", "桃園榮民"],
        "sph":                 ["聖保祿", "聖保祿醫院"],
        "landseed":            ["聯新", "聯新醫院", "壢新"],
        # ===== 新竹 =====
        "ntuh-hsinchu":        ["新竹台大", "新竹臺大"],
        "mackay-hsinchu":      ["馬偕", "新竹馬偕", "馬偕新竹"],
        "tyh":                 ["東元", "東元醫院"],
        # ===== 苗栗 =====
        "weigong":             ["為恭", "為恭醫院"],
        # ===== 台中其他 =====
        "ktgh":                ["光田", "光田醫院"],
        "sltung":              ["童綜合", "童醫院"],
        "lshosp":              ["林新", "林新醫院"],
        "tzuchi-taichung":     ["慈濟", "台中慈濟", "慈濟台中"],
        "jah":                 ["仁愛", "大里仁愛", "仁愛醫院"],
        "ndmctsgh-tc":         ["國軍台中", "台中國軍"],
        # ===== 雲林 =====
        "ntuh-yunlin":         ["台大雲林", "臺大雲林", "雲林台大"],
        "cmuh-beigang":        ["北港", "中醫北港", "北港附醫"],
        # ===== 軍醫系 =====
        "afkh-zuoying":        ["國軍左營", "左營國軍", "海軍醫院"],
        "afkh":                ["國軍高雄", "高雄國軍"],
        "afhl":                ["國軍花蓮", "花蓮國軍"],
    }

    async with async_session() as session:
        for hospital_code, aliases in alias_map.items():
            for alias in aliases:
                # 檢查是否已有 (hospital_code, alias) 這組配對
                result = await session.execute(
                    select(HospitalAlias).where(
                        HospitalAlias.hospital_code == hospital_code,
                        HospitalAlias.alias == alias,
                    )
                )
                if not result.scalar_one_or_none():
                    session.add(HospitalAlias(
                        hospital_code=hospital_code,
                        alias=alias,
                    ))
                    logger.debug(f"已新增別名: {alias} → {hospital_code}")
        await session.commit()
    logger.info("✅ 醫院別名初始化完成")


app = FastAPI(
    title="叮咚到號 — 醫院看診進度通知",
    description="即時抓取醫院看診進度，透過 LINE 推播通知",
    version="0.1.0",
    lifespan=lifespan,
)

# 註冊路由
app.include_router(webhook_router)
app.include_router(admin_router)
app.include_router(test_router)
app.include_router(live_test_router)


@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/hospitals")
async def list_hospitals():
    """列出所有已註冊醫院及其 Adapter 狀態"""
    from app.scrapers.registry import AdapterRegistry
    adapters = AdapterRegistry.get_all()
    return {
        "count": len(adapters),
        "hospitals": [
            {
                "code": code,
                "name": adapter.hospital_name,
                "type": "api" if "api" in adapter.base_url or "data." in adapter.base_url else "scraper",
                "url": adapter.base_url,
            }
            for code, adapter in adapters.items()
        ],
    }


@app.get("/api/progress/{hospital_code}")
async def get_live_progress(hospital_code: str):
    """即時查詢某醫院看診進度（直接呼叫 Adapter，不經快取）"""
    from app.scrapers.registry import AdapterRegistry
    adapter = AdapterRegistry.get(hospital_code)
    if not adapter:
        return {"error": f"找不到醫院: {hospital_code}", "available": AdapterRegistry.get_all_codes()}

    progress_list = await adapter.fetch_all_progress()
    return {
        "hospital": adapter.hospital_name,
        "code": hospital_code,
        "count": len(progress_list),
        "data": [p.to_dict() for p in progress_list],
    }


@app.post("/api/admin/sync-master-data")
async def trigger_sync_master_data():
    """手動觸發診科/醫生主檔同步（從各醫院爬蟲抓取後寫入 MySQL）"""
    from app.tasks.sync_master_data import sync_master_data
    task = sync_master_data.delay()
    return {"task_id": task.id, "status": "queued"}


@app.get("/api/departments/{hospital_code}")
async def list_departments(hospital_code: str):
    """查詢某醫院的所有診科"""
    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.department import Department

    async with async_session() as session:
        result = await session.execute(
            select(Department)
            .where(Department.hospital_code == hospital_code)
            .order_by(Department.name)
        )
        departments = result.scalars().all()
        return {
            "hospital_code": hospital_code,
            "count": len(departments),
            "departments": [d.name for d in departments],
        }


@app.get("/api/doctors/{hospital_code}")
async def list_doctors(hospital_code: str, department: str | None = None):
    """查詢某醫院的所有醫生（可依科別篩選）"""
    from sqlalchemy import select
    from app.models.database import async_session
    from app.models.doctor import Doctor

    async with async_session() as session:
        query = select(Doctor).where(Doctor.hospital_code == hospital_code)
        if department:
            query = query.where(Doctor.department == department)
        query = query.order_by(Doctor.department, Doctor.name)

        result = await session.execute(query)
        doctors = result.scalars().all()
        return {
            "hospital_code": hospital_code,
            "count": len(doctors),
            "doctors": [
                {
                    "department": d.department,
                    "name": d.name,
                    "clinic_room": d.clinic_room,
                }
                for d in doctors
            ],
        }


@app.post("/api/admin/sync-nhi")
async def trigger_nhi_sync(types: list[str] | None = None):
    """手動觸發 NHI 資料同步（管理用）"""
    from app.tasks.nhi_sync import sync_nhi_institutions
    task = sync_nhi_institutions.delay(types)
    return {"task_id": task.id, "status": "queued"}


@app.get("/api/admin/nhi-stats")
async def nhi_stats():
    """查看 NHI 資料同步統計"""
    from app.services.nhi_sync import NhiQueryService
    query = NhiQueryService()
    stats = await query.get_stats()
    return {"stats": stats}


@app.get("/api/search/hospital")
async def search_hospital(q: str, limit: int = 10):
    """搜尋醫院"""
    from app.services.nhi_sync import NhiQueryService
    query = NhiQueryService()
    results = await query.search_hospitals(q, limit)
    return {
        "results": [
            {
                "hosp_id": r.hosp_id,
                "name": r.hosp_name,
                "type": r.hosp_type,
                "address": r.address,
                "tel": r.tel,
                "departments": r.departments,
            }
            for r in results
        ]
    }


@app.get("/api/search/hospitals-by-area")
async def search_hospitals_by_area(area: str, limit: int = 50):
    """依地區搜尋醫院（醫學中心＋區域醫院）"""
    from app.services.nhi_sync import NhiQueryService
    query = NhiQueryService()
    results = await query.search_hospitals_by_area(area, limit=limit)
    return {
        "count": len(results),
        "results": [
            {
                "hosp_id": r.hosp_id,
                "name": r.hosp_name,
                "type": r.hosp_type,
                "address": r.address,
                "tel": r.tel,
                "departments": (r.departments or "")[:100],
            }
            for r in results
        ],
    }


@app.get("/api/guide/which-department")
async def which_department(q: str, limit: int = 10):
    """查詢症狀/疾病對應的科別（供 LINE Bot 使用）"""
    from sqlalchemy import select, or_
    from app.models.database import async_session
    from app.models.department import DepartmentGuide

    keyword = q.strip()
    if not keyword:
        return {"results": []}

    async with async_session() as session:
        result = await session.execute(
            select(DepartmentGuide).where(
                or_(
                    DepartmentGuide.disease.contains(keyword),
                    DepartmentGuide.symptoms.contains(keyword),
                    DepartmentGuide.keywords.contains(keyword),
                    DepartmentGuide.department.contains(keyword),
                )
            ).limit(limit)
        )
        guides = result.scalars().all()

    return {
        "query": keyword,
        "count": len(guides),
        "results": [
            {
                "department": g.department,
                "category": g.category,
                "disease": g.disease,
                "symptoms": g.symptoms,
            }
            for g in guides
        ],
    }


@app.get("/api/search/pharmacy")
async def search_pharmacy(area: str, limit: int = 5):
    """搜尋附近藥局"""
    from app.services.nhi_sync import NhiQueryService
    query = NhiQueryService()
    results = await query.search_pharmacies_near(area, limit)
    return {
        "results": [
            {
                "hosp_id": r.hosp_id,
                "name": r.hosp_name,
                "address": r.address,
                "tel": r.tel,
                "schedule": r.schedule,
            }
            for r in results
        ]
    }
