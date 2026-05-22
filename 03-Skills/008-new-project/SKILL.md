---
name: new-project
description: |
  新專案從零建立的完整 SOP。建資料夾結構、初始化 git、建 .gitignore / .env.example、
  設定 package.json、建立 GitHub repo 並推上去。
  Use when: "新專案", "開新專案", "project 初始化", "建 repo", "從零開始"
triggers:
  - 新專案
  - 開新專案
  - project 初始化
  - 從零開始
  - 專案模板
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - AskUserQuestion
---

# /new-project — 新專案初始化 SOP

先問使用者兩件事：

1. **專案名稱**（用英文，會成為資料夾名和 GitHub repo 名）
2. **專案類型**：
   - A. Next.js（前後端一體）
   - B. React SPA + Node backend（Vite + Express）
   - C. 純前端 SPA（Vite，打外部 API）
   - D. Node.js 純後端（API server）

---

## Step 1：建立資料夾結構

### 類型 A：Next.js

```bash
npx create-next-app@latest <專案名稱> --typescript --tailwind --app
cd <專案名稱>
```

### 類型 B：React SPA + Node backend

```bash
mkdir <專案名稱> && cd <專案名稱>
mkdir 01-server 02-web
cd 02-web && npm create vite@latest . -- --template react-ts && cd ..
cd 01-server && npm init -y && cd ..
```

### 類型 C：純前端 SPA

```bash
npm create vite@latest <專案名稱> -- --template react-ts
cd <專案名稱>
```

### 類型 D：Node.js 純後端

```bash
mkdir <專案名稱> && cd <專案名稱>
npm init -y
mkdir src
```

---

## Step 2：建立 .gitignore

```bash
cat > .gitignore << 'EOF'
# 環境變數（絕對不能上 git）
.env
.env.*
!.env.example

# 私鑰 / 憑證
*.key
*.pem
*.p12
id_rsa
id_ed25519

# 資料庫
*.sqlite
*.db
database/

# 個人筆記（含帳密）
0-run.md
01-dev/

# Build 產物
node_modules/
dist/
build/
.next/
out/

# macOS 垃圾
.DS_Store
._*
.AppleDouble

# 編輯器
.vscode/settings.json
.idea/
EOF
```

---

## Step 3：建立 .env.example

```bash
cat > .env.example << 'EOF'
# 複製這個檔案成 .env 並填入真實值
# cp .env.example .env

# App
PORT=3000
NODE_ENV=development

# 在這裡加你需要的 key（不要填真實值）
# OPENAI_API_KEY=
# DATABASE_URL=
EOF
```

```bash
# 建立真實 .env（不進 git）
cp .env.example .env
# 然後用編輯器填入真實值
```

---

## Step 4：初始化 git

```bash
git init
git add .
git commit -m "init: project setup"
```

---

## Step 5：建立 GitHub repo 並推上去

```bash
# 確認 gh 已登入
gh auth status

# 建立 private repo 並推上去
gh repo create <專案名稱> --private --source=. --remote=origin --push
```

推完後把 repo URL 給使用者確認。

---

## Step 6：安全確認

```bash
# 確認 .env 沒有被追蹤
git ls-files | grep "\.env$"
# 應該沒有輸出

# 確認 .gitignore 有效
git status --short | grep "\.env"
# 應該沒有輸出
```

---

## 完成 checklist

```
□ 資料夾結構建立完成
□ .gitignore 建立完成（含敏感檔案規則）
□ .env.example 建立完成
□ .env 建立完成（已填入真實值）
□ git init + 第一次 commit 完成
□ GitHub repo 建立完成
□ 確認 .env 沒有被 git 追蹤
```
