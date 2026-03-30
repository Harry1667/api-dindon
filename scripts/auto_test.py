#!/usr/bin/env python3
"""叮咚到號 — 自動化測試腳本

在真實看診時段執行，用假用戶模擬真實使用和亂按，
收集對話記錄後用 AI 分析邏輯問題。

用法：
  python3 scripts/auto_test.py              # 執行全部測試
  python3 scripts/auto_test.py --plan1      # 只跑正常使用
  python3 scripts/auto_test.py --plan2      # 只跑亂按測試
  python3 scripts/auto_test.py --analyze    # 只分析最近的報告
"""

import asyncio
import json
import sys
import os
import time
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 加入專案根目錄到 path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("REDIS_URL", "redis://localhost:6380/0")  # 測試環境 Redis
from dotenv import load_dotenv
load_dotenv(ROOT / ".env.dev")

TW_TZ = timezone(timedelta(hours=8))
REPORT_DIR = ROOT / "logs" / "test_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Plan 1: 正常使用流程（模擬帶小孩的媽媽）
# ============================================================

PLAN1_SCENARIOS = [
    {
        "name": "新用戶完整流程：查詢→追蹤→到號",
        "persona": "帶小孩的媽媽，第一次使用",
        "steps": [
            ("你好", "打招呼看回應"),
            ("說明", "查看功能說明"),
            ("台大醫院", "查詢大醫院"),
            ("1", "選第一個選項"),
            ("1", "再選"),
            ("@", "回主選單"),
        ],
    },
    {
        "name": "別名查詢：用簡稱找醫院",
        "persona": "老人家，用口語化名稱",
        "steps": [
            ("長庚", "用簡稱"),
            ("1", "選第一個"),
            ("@", "回主選單"),
            ("馬偕", "另一個簡稱"),
            ("1", "選"),
            ("@", "回主選單"),
            ("榮總", "再試"),
            ("@", "回主選單"),
        ],
    },
    {
        "name": "快速追蹤流程",
        "persona": "趕時間的上班族",
        "steps": [
            ("00", "查看支援的醫院"),
            ("台大醫院", "選醫院"),
            ("1", "選科別"),
            ("1", "選醫師"),
            ("@", "回主選單"),
        ],
    },
    {
        "name": "查詢不存在的醫院",
        "persona": "打錯名字的用戶",
        "steps": [
            ("台大", "簡稱查詢"),
            ("@", "回主選單"),
            ("某某診所", "不存在的名字"),
            ("啊啊啊", "亂打"),
            ("@", "回主選單"),
        ],
    },
    {
        "name": "追蹤管理流程",
        "persona": "已有追蹤的用戶",
        "steps": [
            ("t", "查看追蹤"),
            ("h", "查看說明"),
            ("@", "回主選單"),
        ],
    },
    {
        "name": "預約追蹤流程",
        "persona": "提前設定的用戶",
        "steps": [
            ("p", "預約追蹤"),
            ("取消", "取消預約"),
            ("@", "回主選單"),
        ],
    },
]


# ============================================================
# Plan 2: 亂按測試（壓力+邊界）
# ============================================================

PLAN2_CHAOS_INPUTS = [
    # 特殊字元
    "", " ", "   ", "\n", "\t",
    "!@#$%^&*()", "🤣🤣🤣", "❤️❤️❤️",
    # 超長訊息
    "A" * 100, "測試" * 50,
    # 數字邊界
    "0", "-1", "99999", "0.5",
    # 注入嘗試
    "<script>alert(1)</script>",
    "'; DROP TABLE users; --",
    # 快速切換
    "台大", "1", "2", "3", "c", "t", "p",
    "長庚", "取消", "台大", "取消",
    # 中途打斷
    "台大醫院", "馬偕", "1",
    # 重複操作
    "t", "t", "t",
    "c", "c", "c",
    "@", "@", "@",
    # 無意義
    "哈哈哈", "不知道", "幫幫我",
    "asdfjkl;", "qqqqq",
    # 醫院名+亂碼
    "台大醫院 asdf", "長庚 123",
    "馬偕醫院 !@#",
]


def _build_chaos_scenarios(count: int = 10) -> list[dict]:
    """產生亂按劇本"""
    scenarios = []
    for i in range(count):
        # 每個劇本隨機 5-15 步
        num_steps = random.randint(5, 15)
        steps = []
        for _ in range(num_steps):
            inp = random.choice(PLAN2_CHAOS_INPUTS)
            steps.append((inp, f"亂按第{len(steps)+1}步"))
        scenarios.append({
            "name": f"亂按測試 #{i+1}",
            "persona": "亂按的用戶",
            "steps": steps,
        })
    return scenarios


# ============================================================
# 執行引擎
# ============================================================

async def run_scenario(user_id: str, scenario: dict) -> dict:
    """執行單一劇本，記錄完整對話"""
    from demo_chat import handle_message, reset_conv

    reset_conv(user_id)
    conversations = []
    errors = []

    for user_input, description in scenario["steps"]:
        t0 = time.time()
        try:
            reply = await handle_message(user_input, user_id)
            elapsed = round(time.time() - t0, 3)
            conversations.append({
                "step": len(conversations) + 1,
                "input": user_input,
                "description": description,
                "reply": reply,
                "reply_length": len(reply),
                "elapsed_sec": elapsed,
                "error": None,
            })
        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            error_msg = f"{type(e).__name__}: {str(e)[:200]}"
            conversations.append({
                "step": len(conversations) + 1,
                "input": user_input,
                "description": description,
                "reply": None,
                "reply_length": 0,
                "elapsed_sec": elapsed,
                "error": error_msg,
            })
            errors.append(error_msg)

    reset_conv(user_id)

    return {
        "scenario": scenario["name"],
        "persona": scenario.get("persona", ""),
        "user_id": user_id,
        "total_steps": len(conversations),
        "errors": errors,
        "has_errors": len(errors) > 0,
        "conversations": conversations,
    }


async def run_plan(plan_name: str, scenarios: list[dict]) -> dict:
    """執行一組劇本"""
    now = datetime.now(TW_TZ)
    results = []

    for i, scenario in enumerate(scenarios):
        user_id = f"__autotest_{plan_name}_{i}_{int(time.time())}"
        print(f"  [{i+1}/{len(scenarios)}] {scenario['name']}...", end=" ", flush=True)
        result = await run_scenario(user_id, scenario)
        status = "ERROR" if result["has_errors"] else "OK"
        print(f"{status} ({result['total_steps']} steps)")
        results.append(result)
        # 每個劇本間隔 1 秒，避免太快
        await asyncio.sleep(1)

    return {
        "plan": plan_name,
        "timestamp": now.isoformat(),
        "session": _get_session_hint(now),
        "total_scenarios": len(results),
        "errors_count": sum(1 for r in results if r["has_errors"]),
        "results": results,
    }


def _get_session_hint(now) -> str:
    hour = now.hour
    if hour < 12:
        return "上午診"
    elif hour < 17:
        return "下午診"
    elif hour < 21:
        return "夜診"
    return "非看診時段"


# ============================================================
# AI 分析
# ============================================================

def generate_analysis_prompt(report: dict) -> str:
    """產生 AI 分析用的 prompt"""
    conversations_text = ""
    for result in report["results"]:
        conversations_text += f"\n### {result['scenario']} (角色: {result['persona']})\n"
        for conv in result["conversations"]:
            reply_preview = (conv["reply"] or "ERROR")[:300]
            conversations_text += f"  用戶: {conv['input']}\n"
            conversations_text += f"  系統: {reply_preview}\n"
            if conv["error"]:
                conversations_text += f"  ⚠️ 錯誤: {conv['error']}\n"
            conversations_text += f"  (耗時 {conv['elapsed_sec']}s)\n\n"

    return f"""你是一個 UX 分析師，正在分析一個醫院看診排隊 LINE Bot 的對話記錄。

測試時段: {report['session']}
測試計畫: {report['plan']}
劇本數: {report['total_scenarios']}
錯誤數: {report['errors_count']}

以下是所有對話記錄:
{conversations_text}

請分析以下問題:

1. **對話邏輯問題**: 系統回覆是否合理？有沒有答非所問的情況？
2. **用戶體驗問題**: 對於帶小孩的媽媽和老人家，哪些回覆會讓他們困惑？
3. **錯誤處理**: 用戶輸入奇怪的東西時，系統是否友善地引導回正軌？
4. **流程斷裂**: 有沒有用戶走到一半不知道下一步怎麼做的情況？
5. **效能問題**: 有沒有回覆特別慢的步驟？（超過 2 秒算慢）
6. **改善建議**: 按優先級列出 3-5 個最該改的問題

請用繁體中文回答，格式清楚。
"""


def save_report(report: dict, plan_name: str):
    """儲存報告到檔案"""
    now = datetime.now(TW_TZ)
    filename = f"{now.strftime('%Y%m%d_%H%M')}_{plan_name}.json"
    filepath = REPORT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  報告已存: {filepath}")

    # 同時存 AI 分析 prompt
    prompt = generate_analysis_prompt(report)
    prompt_file = REPORT_DIR / f"{now.strftime('%Y%m%d_%H%M')}_{plan_name}_analysis_prompt.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"  分析 prompt 已存: {prompt_file}")

    return filepath, prompt_file


# ============================================================
# 主程式
# ============================================================

async def main():
    args = sys.argv[1:]
    run_plan1 = "--plan1" in args or not args or "--all" in args
    run_plan2 = "--plan2" in args or not args or "--all" in args
    analyze_only = "--analyze" in args

    if analyze_only:
        # 找最近的報告
        reports = sorted(REPORT_DIR.glob("*.json"), reverse=True)
        if not reports:
            print("找不到報告")
            return
        print(f"最近的報告: {reports[0].name}")
        with open(reports[0]) as f:
            report = json.load(f)
        prompt = generate_analysis_prompt(report)
        print("\n" + "=" * 60)
        print("請將以下 prompt 貼到 AI 進行分析:")
        print("=" * 60)
        print(prompt)
        return

    now = datetime.now(TW_TZ)
    print(f"叮咚到號 自動化測試")
    print(f"時間: {now.strftime('%Y-%m-%d %H:%M')} ({_get_session_hint(now)})")
    print(f"=" * 50)

    if run_plan1:
        print(f"\n📋 Plan 1: 正常使用流程 ({len(PLAN1_SCENARIOS)} 個劇本)")
        print("-" * 40)
        report1 = await run_plan(plan_name="plan1_normal", scenarios=PLAN1_SCENARIOS)
        save_report(report1, "plan1_normal")

    if run_plan2:
        chaos = _build_chaos_scenarios(count=8)
        print(f"\n🎲 Plan 2: 亂按測試 ({len(chaos)} 個劇本)")
        print("-" * 40)
        report2 = await run_plan(plan_name="plan2_chaos", scenarios=chaos)
        save_report(report2, "plan2_chaos")

    print(f"\n{'=' * 50}")
    print("測試完成！報告在 logs/test_reports/")
    print("用 'python3 scripts/auto_test.py --analyze' 產生 AI 分析 prompt")


if __name__ == "__main__":
    asyncio.run(main())
