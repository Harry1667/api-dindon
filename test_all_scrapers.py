"""測試所有醫院爬蟲 — 獨立執行，不需要 Docker/Redis/MySQL"""

import asyncio
import sys
import time
from datetime import datetime, timezone, timedelta

# 確保 import path 正確
sys.path.insert(0, ".")

from app.schemas.clinic import ClinicProgressData
from app.scrapers.wanfang import WanfangAdapter
from app.scrapers.newtaipei_united import banqiao_adapter, sanchong_adapter
from app.scrapers.kaohsiung_united import KaohsiungUnitedAdapter
from app.scrapers.changgung import taipei_changgung, linkou_changgung, kaohsiung_changgung
from app.scrapers.ntuh import ntuh_main, ntuh_children
from app.scrapers.mackay import mackay_taipei, mackay_tamsui
from app.scrapers.tpvgh import TpvghAdapter
from app.scrapers.cathay import CathayAdapter
from app.scrapers.shinkong import ShinkongAdapter
from app.scrapers.tsgh import TsghAdapter

TW_TZ = timezone(timedelta(hours=8))

# 所有 adapter 實例
ALL_ADAPTERS = [
    WanfangAdapter(),
    ntuh_main,
    ntuh_children,
    TpvghAdapter(),
    taipei_changgung,
    linkou_changgung,
    kaohsiung_changgung,
    mackay_taipei,
    mackay_tamsui,
    CathayAdapter(),
    ShinkongAdapter(),
    TsghAdapter(),
    banqiao_adapter,
    sanchong_adapter,
    KaohsiungUnitedAdapter(),
]


async def test_one_adapter(adapter) -> dict:
    """測試單一 adapter，回傳結果摘要"""
    code = adapter.hospital_code
    name = adapter.hospital_name
    start = time.time()

    try:
        results = await adapter.fetch_all_progress()
        elapsed = time.time() - start

        # 統計
        depts = set()
        doctors = set()
        for r in results:
            depts.add(r.department)
            doctors.add(r.doctor_name)

        # 取前 3 筆 sample
        samples = []
        for r in results[:3]:
            samples.append(
                f"    {r.department} | {r.doctor_name} | {r.clinic_room} | "
                f"目前:{r.current_number} 下一:{r.next_number}"
            )

        return {
            "code": code,
            "name": name,
            "status": "OK" if results else "EMPTY",
            "count": len(results),
            "depts": len(depts),
            "doctors": len(doctors),
            "elapsed": elapsed,
            "samples": samples,
            "error": None,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "code": code,
            "name": name,
            "status": "ERROR",
            "count": 0,
            "depts": 0,
            "doctors": 0,
            "elapsed": elapsed,
            "samples": [],
            "error": str(e),
        }


async def main():
    now = datetime.now(TW_TZ)
    print(f"{'='*70}")
    print(f"  叮咚到號 — 全醫院爬蟲測試")
    print(f"  時間: {now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")
    print(f"  星期: {['一','二','三','四','五','六','日'][now.weekday()]}")
    print(f"  共 {len(ALL_ADAPTERS)} 個 adapter")
    print(f"{'='*70}\n")

    # 逐一測試（避免同時大量請求被擋）
    results = []
    for adapter in ALL_ADAPTERS:
        print(f"  測試中: {adapter.hospital_name} ({adapter.hospital_code})...", end=" ", flush=True)
        result = await test_one_adapter(adapter)

        if result["status"] == "OK":
            print(f"OK  {result['count']} 診間, {result['depts']} 科, {result['doctors']} 醫師 ({result['elapsed']:.1f}s)")
        elif result["status"] == "EMPTY":
            print(f"EMPTY  0 筆資料 ({result['elapsed']:.1f}s)")
        else:
            print(f"ERROR  {result['error'][:60]} ({result['elapsed']:.1f}s)")

        results.append(result)
        # 間隔 0.5 秒避免被擋
        await asyncio.sleep(0.5)

    # === 總結報告 ===
    print(f"\n{'='*70}")
    print(f"  測試結果總覽")
    print(f"{'='*70}\n")

    ok_list = [r for r in results if r["status"] == "OK"]
    empty_list = [r for r in results if r["status"] == "EMPTY"]
    error_list = [r for r in results if r["status"] == "ERROR"]

    print(f"  OK:    {len(ok_list)}/{len(results)} 家醫院有即時資料")
    print(f"  EMPTY: {len(empty_list)}/{len(results)} 家醫院無資料（可能非看診時間）")
    print(f"  ERROR: {len(error_list)}/{len(results)} 家醫院爬蟲錯誤")

    # 有資料的醫院
    if ok_list:
        print(f"\n  --- 有資料的醫院 ---")
        total_clinics = 0
        for r in ok_list:
            print(f"  {r['name']:20s} ({r['code']:25s}) | {r['count']:4d} 診間 | {r['depts']:3d} 科 | {r['doctors']:3d} 醫師 | {r['elapsed']:.1f}s")
            total_clinics += r["count"]
            for s in r["samples"]:
                print(s)
        print(f"\n  總計: {total_clinics} 個診間即時資料")

    # 無資料的
    if empty_list:
        print(f"\n  --- 無資料（可能週末/非看診時段）---")
        for r in empty_list:
            print(f"  {r['name']:20s} ({r['code']:25s}) | {r['elapsed']:.1f}s")

    # 有錯誤的
    if error_list:
        print(f"\n  --- 爬蟲錯誤 ---")
        for r in error_list:
            print(f"  {r['name']:20s} ({r['code']:25s}) | {r['error']}")

    print(f"\n{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
