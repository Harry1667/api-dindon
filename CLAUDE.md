## 專案速覽

**叮咚到號** — 台灣醫院候診進度追蹤(LINE bot + LIFF + /simple 老人版)

- Production: https://dd.dl-app.com(aapanel /www/wwwroot/dd.dl-app.com)
- 29 家醫院爬蟲(`app/scrapers/registry.py`),前端三軍拆 3 院區 = 31 卡
- Stack: FastAPI + Celery + Redis + MySQL(外部 host.docker.internal)
- 設計性休爬:每天 22:00-07:00 / 週日 / TW 國定假日
- 監控腳本:`.gstack/qa-reports/system-check.sh`(gitignore,本機 only)

## /simple 老人版關鍵設計

- localStorage 鍵:`dd_tracks`(追蹤陣列)、`dd_guest_id`、`dd_tier`(free=1 / paid=3 追蹤上限)
- sessionStorage 鍵:`simple_setup`(流程暫存)
- 過號叫號是正常現象(順號→過號→順號)— 號碼會跳 31→5→32,不是 bug
- tracking 頁面 30 秒輪詢:過號 5 分鐘 / 連續 3 次無 match → autoEnd
- 14:00/17:00 時段切換有 ~5 分鐘過渡期(待下一輪 scrape 才清乾淨)

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
