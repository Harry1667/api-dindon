# git-safety

**指令：** `/git-safety`

## 是什麼

Git commit 前的安全掃描工具，防止把密碼、token、SSH key 推上 GitHub。
來自 2026-04-10 SurvivalWallet 事故：一個 `git add .` 差點把 GitHub PAT 和 aaPanel 帳密推上去。

## 怎麼用

在 Claude Code 輸入 `/git-safety`，選擇你要做的事：

| 情況 | 說法 |
|---|---|
| commit 前掃描有沒有漏掉的 secret | 「幫我掃一下」 |
| 建立新專案的 `.gitignore` | 「給我 gitignore 範本」 |
| 不小心 commit 了敏感資訊 | 「我 commit 了密碼，還沒 push」或「已經 push 了」 |
| 忘記某個 token pattern 長什麼樣 | 「GitHub PAT 怎麼認」 |

> **`/deploy-sop` 每次執行前都會自動呼叫此 skill 的安全掃描步驟。**
> 你也可以單獨呼叫，在任何 commit 前做檢查。

## 來源文件

`git-secrets-rules.md`
