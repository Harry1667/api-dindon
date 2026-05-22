# pr-review

**指令：** `/pr-review`

## 是什麼

Commit 或 PR 前的 code review checklist。
檢查程式碼品質：命名、安全性、效能、TypeScript 型別、死碼清理。

> 注意：這個 skill 負責**程式碼品質**，secret 掃描由 `/git-safety` 負責。
> `/pr-review` 執行時會先跑 git-safety 的安全掃描，再進行 code review。

## 怎麼用

在 Claude Code 輸入 `/pr-review`，不需要帶參數。

Skill 會自動：
1. 跑安全掃描（確認沒有 secret 洩漏）
2. 執行自動掃描指令（找 `console.log`、`TODO`、`any` 型別）
3. 提供完整 checklist（必過項 / 品質項 / 效能項）
4. 提醒 commit message 格式
5. 確認 TypeScript 編譯和 build 通過再推
