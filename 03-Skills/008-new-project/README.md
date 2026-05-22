# new-project

**指令：** `/new-project`

## 是什麼

新專案從零建立的完整 SOP。
包含建資料夾結構、初始化 git、`.gitignore`、`.env.example`、設定 `package.json`、建 GitHub repo 並推上去。

支援四種專案類型：
- Next.js
- React SPA + Node backend（Vite + Express）
- 純前端 SPA（Vite）
- Node.js 純後端

## 怎麼用

在 Claude Code 輸入 `/new-project`，告訴 AI 專案名稱和類型。

Skill 會帶你完成：
1. 建立對應的資料夾結構
2. 產生 `.gitignore`（含敏感檔案規則）
3. 產生 `.env.example` 範本
4. `git init` + 第一次 commit
5. GitHub repo 建立並推上去
6. 安全確認（`.env` 沒被追蹤）
