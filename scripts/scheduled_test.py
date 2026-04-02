"""排程測試 — 上午/下午/夜間各跑一輪全醫院爬蟲，存報告

用法：
  # 透過 crontab 排程（週四週五 三個時段各跑一次）
  python3 scripts/scheduled_test.py

  # 手動跑
  python3 scripts/scheduled_test.py
"""

import asyncio
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")

from app.scrapers.registry import AdapterRegistry

TW_TZ = timezone(timedelta(hours=8))

# 跳過已知醫院端問題的 adapter
SKIP_CODES = {
    "ntuh", "ntuh-children",       # 台大 AJAX 500
    "tzuchi-taipei", "tzuchi-xindian",  # 慈濟超慢且無資料
    "fjuh",                        # 輔大可能改版
    "kaohsiung-united",            # 高雄聯合 HIS 掛了
}


async def test_one(adapter):
    code = adapter.hospital_code
    start = time.time()
    try:
        results = await adapter.fetch_all_progress()
        elapsed = time.time() - start
        depts = set(r.department for r in results)
        doctors = set(r.doctor_name for r in results)
        return {
            "code": code, "name": adapter.hospital_name,
            "status": "OK" if results else "EMPTY",
            "count": len(results), "depts": len(depts),
            "doctors": len(doctors), "elapsed": elapsed,
            "samples": results[:3], "error": None,
        }
    except Exception as e:
        return {
            "code": code, "name": adapter.hospital_name,
            "status": "ERROR", "count": 0, "depts": 0,
            "doctors": 0, "elapsed": time.time() - start,
            "samples": [], "error": str(e)[:200],
        }


async def run_test():
    now = datetime.now(TW_TZ)
    hour = now.hour
    if hour < 12:
        session_name = "上午診"
    elif hour < 17:
        session_name = "下午診"
    else:
        session_name = "夜診"

    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    weekday = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]

    all_adapters = [
        a for a in AdapterRegistry.get_all().values()
        if a.hospital_code not in SKIP_CODES
    ]

    print(f"[{date_str} {time_str} 週{weekday}] {session_name} 測試開始，{len(all_adapters)} 家醫院")

    results = []
    for adapter in all_adapters:
        r = await test_one(adapter)
        results.append(r)
        await asyncio.sleep(0.2)

    ok = [r for r in results if r["status"] == "OK"]
    empty = [r for r in results if r["status"] == "EMPTY"]
    error = [r for r in results if r["status"] == "ERROR"]
    total_clinics = sum(r["count"] for r in results)
    total_doctors = sum(r["doctors"] for r in results)

    # 等很久的
    long_waits = []
    for r in results:
        for s in r.get("samples", []):
            if hasattr(s, "next_number") and hasattr(s, "current_number"):
                gap = s.next_number - s.current_number
                if gap > 30:
                    long_waits.append(f"{r['name']} {s.department} {s.doctor_name}: cur={s.current_number} wait={gap}")

    # 寫報告
    report_path = f".gstack/qa-reports/daily-{date_str}-{session_name}.md"
    with open(report_path, "w") as f:
        f.write(f"# 每日測試: {date_str} 週{weekday} {session_name}\n\n")
        f.write(f"**時間:** {time_str}\n")
        f.write(f"**結果:** OK={len(ok)} EMPTY={len(empty)} ERROR={len(error)}\n")
        f.write(f"**診間:** {total_clinics} | **醫生:** {total_doctors}\n\n")

        f.write(f"## 醫院明細\n\n")
        f.write(f"| 醫院 | 狀態 | 診間 | 科 | 醫師 | 耗時 |\n")
        f.write(f"|------|------|------|-----|------|------|\n")
        for r in sorted(results, key=lambda x: x["status"]):
            f.write(f"| {r['name']} | {r['status']} | {r['count']} | {r['depts']} | {r['doctors']} | {r['elapsed']:.1f}s |\n")

        if error:
            f.write(f"\n## 錯誤\n\n")
            for r in error:
                f.write(f"- **{r['name']}:** {r['error']}\n")

        if long_waits:
            f.write(f"\n## 等很久 (>30人)\n\n")
            for lw in long_waits[:20]:
                f.write(f"- {lw}\n")

    # 終端摘要
    print(f"  OK={len(ok)}/{len(results)} 診間={total_clinics} 醫生={total_doctors}")
    if empty:
        print(f"  EMPTY: {', '.join(r['name'] for r in empty)}")
    if error:
        print(f"  ERROR: {', '.join(r['name'] for r in error)}")
    print(f"  報告: {report_path}")

    return len(error) == 0


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
