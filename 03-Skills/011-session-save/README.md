# session-save

**指令：** `/session-save`（或直接說 `save` / `bye` / `結束`）

## 是什麼

工作階段結束時，把這次對話的內容整理成結構化文件存起來。
下次開新對話時，AI 讀一下 `SESSION_NOTES.md` 就能快速接上進度。

## 怎麼用

工作告一段落時，說以下任何一句都會觸發：

```
save
bye
結束
/session-save
```

AI 會自動整理並寫入 `SESSION_NOTES.md`，包含：
- ✅ 本次完成的事
- 🔄 未完成 / 進行中的事
- 💡 重要決策和發現
- 🚀 下次的起點（具體到哪個檔案、哪個步驟）
- 📁 這次動到的相關檔案

## 存到哪裡

- 有明確專案 → 存到該專案根目錄的 `SESSION_NOTES.md`
- 跨專案 / skills 工作 → 存到 `03-Skills/SESSION_NOTES.md`

## 下次怎麼用

開新對話時說：「讀一下 SESSION_NOTES.md，從上次的進度繼續」
