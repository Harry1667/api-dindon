# deploy-sop

**指令：** `/deploy-sop`

## 是什麼

把專案從本機推上 GitHub、部署到 looptw.com 伺服器的完整 SOP。
也包含伺服器基礎設施資料（IP、Port 分配、現有專案清單）。
原 `003-infra-memory` 的伺服器架構資料已合併至此。

## 怎麼用

在 Claude Code 輸入 `/deploy-sop`，說明你要做哪件事：

| 想做的事 | 說法 |
|---|---|
| 在 GitHub 建立新 repo | 「幫我在 GitHub 建 repo」 |
| 把專案推上 GitHub | 「git push 上去」 |
| 第一次部署到伺服器 | 「部署到 looptw.com」 |
| 更新已部署的專案 | 「更新線上版本」 |
| 查伺服器現有專案和 Port | 「伺服器現在有哪些專案」 |

**必搭配 `/git-safety`**：每次 push 或部署前都會先跑安全掃描。

## 來源文件

- `source-personal.md`：含實際路徑的個人版 SOP
- `source-public.md`：通用版 SOP
