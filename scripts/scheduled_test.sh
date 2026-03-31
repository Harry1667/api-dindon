#!/bin/bash
# 叮咚到號 — 正式伺服器排程測試
# 每個看診時段自動測試，記錄完整對話供 AI 分析
#
# 排程（cron）：
#   30 8  * * 1-6  /opt/docker/ajz-dingdon/scripts/scheduled_test.sh morning
#   30 13 * * 1-5  /opt/docker/ajz-dingdon/scripts/scheduled_test.sh afternoon
#   30 18 * * 1-5  /opt/docker/ajz-dingdon/scripts/scheduled_test.sh evening
#   0  22 * * 1-5  /opt/docker/ajz-dingdon/scripts/scheduled_test.sh report

PROJECT_DIR="/opt/docker/ajz-dingdon"
LOG_DIR="$PROJECT_DIR/logs/test_reports"
CONTAINER="medqueue-app"

mkdir -p "$LOG_DIR"

SESSION=${1:-morning}
DATE=$(date +%Y%m%d)
TIME=$(date +%H%M)
LOG_FILE="$LOG_DIR/${DATE}_${TIME}_${SESSION}.log"

echo "===== 排程測試 [$SESSION] $(date) =====" >> "$LOG_FILE"

# 確認容器在跑
if ! docker ps --format '{{.Names}}' | grep -q "$CONTAINER"; then
    echo "ERROR: $CONTAINER 未啟動" >> "$LOG_FILE"
    exit 1
fi

# 健康檢查
HEALTH=$(docker exec "$CONTAINER" curl -s http://localhost:8000/health 2>/dev/null)
echo "Health: $HEALTH" >> "$LOG_FILE"

case $SESSION in
    morning)
        # 上午診 8:30 — 全面測試（醫院剛開診，資料最完整）
        echo "=== 上午診全面測試 ===" >> "$LOG_FILE"
        docker exec "$CONTAINER" python3 scripts/auto_test.py --all >> "$LOG_FILE" 2>&1
        # 額外：用內建 test harness 跑深度測試
        docker exec "$CONTAINER" python3 -c "
import asyncio, json, sys
sys.path.insert(0, '/app')
from app.api.test_harness import _get_hospitals_with_data, _build_scenarios, _build_random_scenarios, _build_deep_scenarios, _run_test

async def main():
    hospitals = await _get_hospitals_with_data()
    print(f'有資料的醫院: {len(hospitals)} 家')
    for h in hospitals:
        print(f'  {h[\"name\"]}: {h[\"total_rooms\"]} 診間, {len(h[\"depts\"])} 科')

    # 標準測試
    scenarios = _build_scenarios(hospitals)
    print(f'標準劇本: {len(scenarios)} 個')
    report = await _run_test(min(len(scenarios), 30), scenarios[:30])
    print(f'結果: {report[\"passed_steps\"]}/{report[\"total_steps\"]} 通過, 平均 {report[\"avg_step_time\"]}s')

    # 隨機測試
    random_s = _build_random_scenarios(hospitals, 15)
    if random_s:
        report2 = await _run_test(len(random_s), random_s)
        print(f'隨機: {report2[\"passed_steps\"]}/{report2[\"total_steps\"]} 通過')

    # 深度測試（每家醫院每個科別）
    deep_s = _build_deep_scenarios(hospitals)
    if deep_s:
        report3 = await _run_test(min(len(deep_s), 50), deep_s[:50])
        print(f'深度: {report3[\"passed_steps\"]}/{report3[\"total_steps\"]} 通過')

asyncio.run(main())
" >> "$LOG_FILE" 2>&1
        ;;

    afternoon)
        # 下午診 13:30 — 標準+隨機測試
        echo "=== 下午診測試 ===" >> "$LOG_FILE"
        docker exec "$CONTAINER" python3 scripts/auto_test.py --all >> "$LOG_FILE" 2>&1
        ;;

    evening)
        # 夜診 18:30 — 標準測試+效能基準
        echo "=== 夜診測試 ===" >> "$LOG_FILE"
        docker exec "$CONTAINER" python3 scripts/auto_test.py --plan1 >> "$LOG_FILE" 2>&1
        # 效能基準測試
        docker exec "$CONTAINER" python3 -c "
import asyncio, time, sys
sys.path.insert(0, '/app')
from demo_chat import handle_message

async def perf_test():
    tests = [
        ('台大', '別名查詢'),
        ('台北榮總', '大量科別'),
        ('長庚', '多家匹配'),
        ('t', '查追蹤'),
        ('00', '醫院列表'),
        ('某某醫院', '找不到'),
        ('h', '說明'),
    ]
    print('=== 效能基準 ===')
    for inp, desc in tests:
        uid = f'__perf_{int(time.time())}'
        t0 = time.time()
        r = await handle_message(inp, uid)
        elapsed = time.time() - t0
        flag = ' ⚠️ SLOW' if elapsed > 1.0 else ''
        print(f'  {desc:12} ({inp:10}): {elapsed:.3f}s  len={len(r):4}{flag}')

asyncio.run(perf_test())
" >> "$LOG_FILE" 2>&1
        ;;

    report)
        # 每日 22:00 — 產生當日彙總報告
        echo "=== 每日彙總報告 ===" >> "$LOG_FILE"
        docker exec "$CONTAINER" python3 -c "
import json, os, glob
from datetime import datetime

report_dir = '/app/logs/test_reports'
today = datetime.now().strftime('%Y%m%d')
files = sorted(glob.glob(f'{report_dir}/{today}_*.json'))

if not files:
    print('今日無測試報告')
else:
    total_scenarios = 0
    total_errors = 0
    slow_steps = 0
    long_replies = 0
    all_issues = []

    for f in files:
        with open(f) as fh:
            data = json.load(fh)
        total_scenarios += data.get('total_scenarios', 0)
        total_errors += data.get('errors_count', 0)

        for r in data.get('results', []):
            for c in r.get('conversations', []):
                if c.get('elapsed_sec', 0) > 1.0:
                    slow_steps += 1
                    all_issues.append(f'SLOW {c[\"elapsed_sec\"]:.1f}s: {r[\"scenario\"]} input={c[\"input\"]!r}')
                if len(c.get('reply', '') or '') > 600:
                    long_replies += 1
                    all_issues.append(f'LONG {len(c[\"reply\"])}c: {r[\"scenario\"]} input={c[\"input\"]!r}')
                if c.get('error'):
                    all_issues.append(f'ERROR: {r[\"scenario\"]} {c[\"error\"][:50]}')

    print(f'📊 {today} 測試日報')
    print(f'  報告數: {len(files)}')
    print(f'  劇本數: {total_scenarios}')
    print(f'  錯誤數: {total_errors}')
    print(f'  慢回應: {slow_steps}')
    print(f'  過長回覆: {long_replies}')
    if all_issues:
        print(f'  問題清單:')
        for issue in all_issues[:20]:
            print(f'    - {issue}')
    else:
        print(f'  ✅ CLEAN — 無問題')

    # 爬蟲資料統計
    from app.api.test_harness import _get_hospitals_with_data
    import asyncio
    hospitals = asyncio.run(_get_hospitals_with_data())
    total_rooms = sum(h['total_rooms'] for h in hospitals)
    print(f'  爬蟲: {len(hospitals)} 家醫院有資料, {total_rooms} 個診間')
" >> "$LOG_FILE" 2>&1
        ;;
esac

echo "===== 結束 $(date) =====" >> "$LOG_FILE"

# 清理 30 天前的報告
find "$LOG_DIR" -name "*.json" -mtime +30 -delete 2>/dev/null
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null
find "$LOG_DIR" -name "*.txt" -mtime +30 -delete 2>/dev/null
