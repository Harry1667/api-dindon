"""2 小時長時間監控測試 — 每 5 分鐘跑一輪全醫院爬蟲

追蹤：
  1. 每個醫院的成功/失敗率
  2. 每個醫生的號碼變化（偵測跳號）
  3. 等很久的情況（掛號人數 > 30）
  4. 間歇性失敗（OK→EMPTY→OK）

輸出：
  .gstack/qa-reports/soak-test-{date}.md
"""

import asyncio
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")

from app.scrapers.registry import AdapterRegistry

TW_TZ = timezone(timedelta(hours=8))

# 設定
INTERVAL_SEC = 600  # 10 分鐘（省資源）
DURATION_SEC = 7200  # 2 小時
LONG_WAIT_THRESHOLD = 30  # 等待超過 30 人算「等很久」

# 跳過已知醫院端問題的 adapter（省 ~120s/輪）
SKIP_CODES = {
    "ntuh",           # 台大 AJAX 500
    "ntuh-children",  # 台大兒童 同上
    "tzuchi-taipei",  # 慈濟台北 37s 無資料
    "tzuchi-xindian", # 慈濟新店 42s 無資料
    "fjuh",           # 輔大 可能改版
    "kaohsiung-united",  # 高雄聯合 HIS 掛了
}


class SoakTestTracker:
    def __init__(self):
        self.rounds = 0
        self.hospital_stats = defaultdict(lambda: {"ok": 0, "empty": 0, "error": 0, "last_status": None})
        self.doctor_history = {}  # key: (hospital, dept, doctor) → list of (time, current, next)
        self.jump_events = []  # 跳號事件
        self.long_waits = []  # 等很久事件
        self.intermittent_failures = []  # OK→EMPTY 事件
        self.round_results = []  # 每輪摘要

    def record_round(self, round_num, results_by_hospital):
        self.rounds = round_num
        now = datetime.now(TW_TZ)
        ts = now.strftime("%H:%M")
        total_ok = 0
        total_empty = 0
        total_error = 0
        total_clinics = 0

        for code, result in results_by_hospital.items():
            stats = self.hospital_stats[code]
            status = result["status"]

            if status == "OK":
                stats["ok"] += 1
                total_ok += 1
                total_clinics += result["count"]
            elif status == "EMPTY":
                stats["empty"] += 1
                total_empty += 1
            else:
                stats["error"] += 1
                total_error += 1

            # 間歇性失敗偵測
            if stats["last_status"] == "OK" and status == "EMPTY":
                self.intermittent_failures.append({
                    "round": round_num, "time": ts,
                    "hospital": result["name"], "code": code,
                })
            stats["last_status"] = status

            # 追蹤每個醫生的號碼
            for prog in result.get("progress", []):
                key = (code, prog.department, prog.doctor_name)
                if key not in self.doctor_history:
                    self.doctor_history[key] = []

                history = self.doctor_history[key]
                cur = prog.current_number
                nxt = prog.next_number

                # 跳號偵測：號碼突然跳過 > 3
                if history:
                    prev_cur = history[-1]["current"]
                    if cur > prev_cur + 3 and prev_cur > 0:
                        self.jump_events.append({
                            "round": round_num, "time": ts,
                            "hospital": prog.hospital_name,
                            "dept": prog.department,
                            "doctor": prog.doctor_name,
                            "room": prog.clinic_room,
                            "prev": prev_cur, "current": cur,
                            "jumped": cur - prev_cur,
                        })

                history.append({"round": round_num, "time": ts, "current": cur, "next": nxt})

                # 等很久偵測
                waiting = nxt - cur if nxt > cur else 0
                if waiting > LONG_WAIT_THRESHOLD:
                    self.long_waits.append({
                        "round": round_num, "time": ts,
                        "hospital": prog.hospital_name,
                        "dept": prog.department,
                        "doctor": prog.doctor_name,
                        "room": prog.clinic_room,
                        "current": cur, "next": nxt,
                        "waiting": waiting,
                    })

        self.round_results.append({
            "round": round_num, "time": ts,
            "ok": total_ok, "empty": total_empty, "error": total_error,
            "clinics": total_clinics,
        })

    def generate_report(self) -> str:
        now = datetime.now(TW_TZ)
        lines = []
        lines.append(f"# Soak Test Report: 叮咚到號 2 小時長時間監控")
        lines.append(f"")
        lines.append(f"**日期:** {now.strftime('%Y-%m-%d')}")
        lines.append(f"**時段:** {self.round_results[0]['time'] if self.round_results else '?'} ~ {self.round_results[-1]['time'] if self.round_results else '?'}")
        lines.append(f"**輪數:** {self.rounds}")
        lines.append(f"**間隔:** 每 {INTERVAL_SEC // 60} 分鐘")
        lines.append(f"")

        # 每輪摘要
        lines.append(f"## 每輪摘要")
        lines.append(f"")
        lines.append(f"| 輪次 | 時間 | OK | EMPTY | ERROR | 診間數 |")
        lines.append(f"|------|------|-----|-------|-------|--------|")
        for r in self.round_results:
            lines.append(f"| {r['round']} | {r['time']} | {r['ok']} | {r['empty']} | {r['error']} | {r['clinics']} |")
        lines.append(f"")

        # 醫院穩定性
        lines.append(f"## 醫院穩定性")
        lines.append(f"")
        lines.append(f"| 醫院 | OK次數 | EMPTY次數 | ERROR次數 | 成功率 |")
        lines.append(f"|------|--------|-----------|-----------|--------|")
        for code, stats in sorted(self.hospital_stats.items(), key=lambda x: x[1]["ok"], reverse=True):
            total = stats["ok"] + stats["empty"] + stats["error"]
            rate = f"{stats['ok']/total*100:.0f}%" if total > 0 else "0%"
            adapter = AdapterRegistry.get(code)
            name = adapter.hospital_name if adapter else code
            lines.append(f"| {name} | {stats['ok']} | {stats['empty']} | {stats['error']} | {rate} |")
        lines.append(f"")

        # 間歇性失敗
        if self.intermittent_failures:
            lines.append(f"## 間歇性失敗 (OK→EMPTY)")
            lines.append(f"")
            lines.append(f"| 輪次 | 時間 | 醫院 |")
            lines.append(f"|------|------|------|")
            for f in self.intermittent_failures:
                lines.append(f"| {f['round']} | {f['time']} | {f['hospital']} |")
            lines.append(f"")
        else:
            lines.append(f"## 間歇性失敗: 無 (穩定)")
            lines.append(f"")

        # 跳號事件
        if self.jump_events:
            lines.append(f"## 跳號事件 (號碼跳過 > 3)")
            lines.append(f"")
            lines.append(f"共 {len(self.jump_events)} 次跳號")
            lines.append(f"")
            lines.append(f"| 輪次 | 時間 | 醫院 | 科別 | 醫生 | 前號→現號 | 跳了 |")
            lines.append(f"|------|------|------|------|------|-----------|------|")
            for j in self.jump_events[:50]:
                lines.append(f"| {j['round']} | {j['time']} | {j['hospital']} | {j['dept']} | {j['doctor']} | {j['prev']}→{j['current']} | {j['jumped']} |")
            if len(self.jump_events) > 50:
                lines.append(f"| ... | ... | 共 {len(self.jump_events)} 次，只顯示前 50 | ... | ... | ... | ... |")
            lines.append(f"")
        else:
            lines.append(f"## 跳號事件: 無")
            lines.append(f"")

        # 等很久
        if self.long_waits:
            # 去重，只保留每個醫生最嚴重的一次
            worst = {}
            for lw in self.long_waits:
                key = (lw["hospital"], lw["dept"], lw["doctor"])
                if key not in worst or lw["waiting"] > worst[key]["waiting"]:
                    worst[key] = lw

            sorted_waits = sorted(worst.values(), key=lambda x: x["waiting"], reverse=True)

            lines.append(f"## 等很久的診間 (等待 > {LONG_WAIT_THRESHOLD} 人)")
            lines.append(f"")
            lines.append(f"共 {len(sorted_waits)} 個醫生出現過等很久")
            lines.append(f"")
            lines.append(f"| 醫院 | 科別 | 醫生 | 目前號 | 最大掛號 | 等待人數 | 時間 |")
            lines.append(f"|------|------|------|--------|---------|---------|------|")
            for lw in sorted_waits[:30]:
                lines.append(f"| {lw['hospital']} | {lw['dept']} | {lw['doctor']} | {lw['current']} | {lw['next']} | {lw['waiting']} | {lw['time']} |")
            lines.append(f"")
        else:
            lines.append(f"## 等很久: 無")
            lines.append(f"")

        # 醫生號碼追蹤（取幾個有趣的例子）
        lines.append(f"## 號碼進度追蹤（取樣）")
        lines.append(f"")

        # 找變化最多的前 10 個醫生
        active_doctors = []
        for key, history in self.doctor_history.items():
            if len(history) >= 3:
                first = history[0]["current"]
                last = history[-1]["current"]
                change = last - first
                if change > 0:
                    active_doctors.append((key, history, change))

        active_doctors.sort(key=lambda x: x[2], reverse=True)

        for (code, dept, doctor), history, change in active_doctors[:10]:
            adapter = AdapterRegistry.get(code)
            hosp = adapter.hospital_name if adapter else code
            nums = " → ".join(f"{h['current']}" for h in history)
            lines.append(f"**{hosp} {dept} {doctor}:** {nums} (進度 +{change})")
            lines.append(f"")

        return "\n".join(lines)


async def run_one_round(adapters):
    """跑一輪全醫院測試"""
    results = {}
    for adapter in adapters:
        code = adapter.hospital_code
        start = time.time()
        try:
            progress = await adapter.fetch_all_progress()
            elapsed = time.time() - start
            results[code] = {
                "name": adapter.hospital_name,
                "status": "OK" if progress else "EMPTY",
                "count": len(progress),
                "elapsed": elapsed,
                "progress": progress,
                "error": None,
            }
        except Exception as e:
            elapsed = time.time() - start
            results[code] = {
                "name": adapter.hospital_name,
                "status": "ERROR",
                "count": 0,
                "elapsed": elapsed,
                "progress": [],
                "error": str(e),
            }
        # 輕微延遲避免過載
        await asyncio.sleep(0.2)
    return results


async def main():
    all_adapters_raw = list(AdapterRegistry.get_all().values())
    all_adapters = [a for a in all_adapters_raw if a.hospital_code not in SKIP_CODES]
    skipped = [a for a in all_adapters_raw if a.hospital_code in SKIP_CODES]
    now = datetime.now(TW_TZ)
    print(f"{'='*70}")
    print(f"  叮咚到號 — 2 小時 Soak Test (省資源版)")
    print(f"  開始: {now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")
    print(f"  測試 {len(all_adapters)} 個 adapter, 跳過 {len(skipped)} 個已知問題")
    print(f"  每 {INTERVAL_SEC//60} 分鐘一輪, 預計 {DURATION_SEC//INTERVAL_SEC} 輪")
    if skipped:
        print(f"  跳過: {', '.join(a.hospital_name for a in skipped)}")
    print(f"{'='*70}\n")

    tracker = SoakTestTracker()
    start_time = time.time()
    round_num = 0

    while time.time() - start_time < DURATION_SEC:
        round_num += 1
        round_start = time.time()
        now = datetime.now(TW_TZ)
        print(f"\n--- 第 {round_num} 輪 ({now.strftime('%H:%M:%S')}) ---")

        results = await run_one_round(all_adapters)

        ok = sum(1 for r in results.values() if r["status"] == "OK")
        empty = sum(1 for r in results.values() if r["status"] == "EMPTY")
        error = sum(1 for r in results.values() if r["status"] == "ERROR")
        clinics = sum(r["count"] for r in results.values())
        elapsed = time.time() - round_start

        print(f"  OK={ok} EMPTY={empty} ERROR={error} 診間={clinics} ({elapsed:.0f}s)")

        # 顯示間歇性失敗
        for code, result in results.items():
            stats = tracker.hospital_stats[code]
            if stats["last_status"] == "OK" and result["status"] == "EMPTY":
                print(f"  ⚠️ {result['name']} 從 OK 變 EMPTY!")
            elif stats["last_status"] == "EMPTY" and result["status"] == "OK":
                print(f"  ✅ {result['name']} 恢復 OK")

        tracker.record_round(round_num, results)

        # 即時顯示跳號
        new_jumps = [j for j in tracker.jump_events if j["round"] == round_num]
        if new_jumps:
            print(f"  跳號 {len(new_jumps)} 次:")
            for j in new_jumps[:5]:
                print(f"    {j['hospital']} {j['dept']} {j['doctor']}: {j['prev']}→{j['current']} (跳 {j['jumped']})")

        # 釋放本輪資料減少記憶體（歷史已存在 tracker 裡）
        for r in results.values():
            r["progress"] = []
        import gc; gc.collect()

        # 等待到下一輪
        wait = INTERVAL_SEC - (time.time() - round_start)
        if wait > 0 and time.time() - start_time + wait < DURATION_SEC:
            print(f"  等待 {wait:.0f}s 到下一輪...")
            await asyncio.sleep(wait)

    # 產出報告
    print(f"\n{'='*70}")
    print(f"  測試完成，產出報告...")
    print(f"{'='*70}\n")

    report = tracker.generate_report()
    report_path = f".gstack/qa-reports/soak-test-{datetime.now(TW_TZ).strftime('%Y-%m-%d')}.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"報告已存: {report_path}")
    print(f"\n摘要:")
    print(f"  總輪數: {tracker.rounds}")
    print(f"  跳號事件: {len(tracker.jump_events)} 次")
    print(f"  間歇性失敗: {len(tracker.intermittent_failures)} 次")

    # 去重統計等很久
    worst_waits = {}
    for lw in tracker.long_waits:
        key = (lw["hospital"], lw["dept"], lw["doctor"])
        if key not in worst_waits or lw["waiting"] > worst_waits[key]["waiting"]:
            worst_waits[key] = lw
    print(f"  等很久的醫生: {len(worst_waits)} 位")


if __name__ == "__main__":
    asyncio.run(main())
