"""測試所有醫院爬蟲 — 獨立執行，不需要 Docker/Redis/MySQL"""

import asyncio
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")

from app.scrapers.registry import AdapterRegistry

TW_TZ = timezone(timedelta(hours=8))


async def test_one_adapter(adapter) -> dict:
    code = adapter.hospital_code
    name = adapter.hospital_name
    start = time.time()

    try:
        results = await adapter.fetch_all_progress()
        elapsed = time.time() - start

        depts = set()
        doctors = set()
        for r in results:
            depts.add(r.department)
            doctors.add(r.doctor_name)

        samples = []
        for r in results[:3]:
            samples.append(
                f"    {r.department} | {r.doctor_name} | {r.clinic_room} | "
                f"目前:{r.current_number} 下一:{r.next_number}"
            )

        return {
            "code": code, "name": name,
            "status": "OK" if results else "EMPTY",
            "count": len(results), "depts": len(depts), "doctors": len(doctors),
            "elapsed": elapsed, "samples": samples, "error": None,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "code": code, "name": name, "status": "ERROR",
            "count": 0, "depts": 0, "doctors": 0,
            "elapsed": elapsed, "samples": [], "error": str(e),
        }


async def main():
    all_adapters = list(AdapterRegistry.get_all().values())
    now = datetime.now(TW_TZ)
    print(f"{'='*70}")
    print(f"  叮咚到號 — 全醫院爬蟲測試")
    print(f"  時間: {now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")
    print(f"  星期: {['一','二','三','四','五','六','日'][now.weekday()]}")
    print(f"  共 {len(all_adapters)} 個 adapter")
    print(f"{'='*70}\n")

    results = []
    for adapter in all_adapters:
        print(f"  測試中: {adapter.hospital_name} ({adapter.hospital_code})...", end=" ", flush=True)
        result = await test_one_adapter(adapter)

        if result["status"] == "OK":
            print(f"OK  {result['count']} 診間, {result['depts']} 科, {result['doctors']} 醫師 ({result['elapsed']:.1f}s)")
        elif result["status"] == "EMPTY":
            print(f"EMPTY  0 筆資料 ({result['elapsed']:.1f}s)")
        else:
            print(f"ERROR  {result['error'][:60]} ({result['elapsed']:.1f}s)")

        results.append(result)
        await asyncio.sleep(0.3)

    print(f"\n{'='*70}")
    print(f"  測試結果總覽")
    print(f"{'='*70}\n")

    ok_list = [r for r in results if r["status"] == "OK"]
    empty_list = [r for r in results if r["status"] == "EMPTY"]
    error_list = [r for r in results if r["status"] == "ERROR"]

    print(f"  OK:    {len(ok_list)}/{len(results)}")
    print(f"  EMPTY: {len(empty_list)}/{len(results)}")
    print(f"  ERROR: {len(error_list)}/{len(results)}")

    if ok_list:
        print(f"\n  --- 有資料 ---")
        total = 0
        for r in ok_list:
            print(f"  {r['name']:20s} ({r['code']:25s}) | {r['count']:4d} 診間 | {r['depts']:3d} 科 | {r['doctors']:3d} 醫師 | {r['elapsed']:.1f}s")
            total += r["count"]
            for s in r["samples"]:
                print(s)
        print(f"\n  總計: {total} 個診間")

    if empty_list:
        print(f"\n  --- 無資料 ---")
        for r in empty_list:
            print(f"  {r['name']:20s} ({r['code']:25s}) | {r['elapsed']:.1f}s")

    if error_list:
        print(f"\n  --- 錯誤 ---")
        for r in error_list:
            print(f"  {r['name']:20s} ({r['code']:25s}) | {r['error'][:60]}")

    print(f"\n{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
