# daily-standup

**指令：** `/daily-standup`

## 是什麼

自動從 git log 整理今天做了什麼，輸出 standup 格式的工作摘要。
不用手動回想，跑一下就能知道今天改了哪些 repo、做了哪些事。

## 怎麼用

在 Claude Code 輸入 `/daily-standup`，不需要帶任何參數。

Skill 會自動：
1. 掃描 `~/Documents` 下所有有 `.git` 的資料夾
2. 找出今日的 commit 紀錄
3. 整理成 **Done / In Progress / Blockers / Next** 四欄輸出

輸出範例：
```
## 今日完成 (Done)
- [mentora] feat: 新增課程進度追蹤功能
- [mathbox] fix: 修正公式渲染在 Safari 的問題

## 進行中 (In Progress)
- survivalwallet：資料同步邏輯尚未 commit

## 明日計畫 (Next)
- 繼續 mathbox API 整合
```
