# LINE@ 串接 Messaging API — 步驟指引

> 你已經建好 LINE@ 官方帳號「叮咚到號」，現在要把它串接到 LINE Developers 的 Messaging API，才能讓程式收發訊息。

---

## 步驟一：登入 LINE Developers

1. 打開 https://developers.line.biz/console/
2. 用你「建立 LINE@ 的那個 LINE 帳號」登入
3. 登入後會看到 **Console 首頁**

---

## 步驟二：建立 Provider

1. 點左上角的「**Create a new provider**」
2. Provider 名稱填：`叮咚到號`（或任意名稱，這是開發者名稱，用戶看不到）
3. 點「Create」

---

## 步驟三：把 LINE@ 連結到 Provider（關鍵步驟）

你有兩條路：

### 路線 A：從 LINE Official Account Manager 啟用 Messaging API（推薦）

1. 打開 LINE Official Account Manager：https://manager.line.biz/
2. 選擇你的「叮咚到號」帳號
3. 點右上角 **設定**（齒輪圖示）
4. 左側選單找到 **Messaging API**
5. 點「**啟用 Messaging API**」
6. 選擇你剛建立的 Provider（`叮咚到號`）
7. 完成！這會自動在 LINE Developers 建立一個 Messaging API Channel

### 路線 B：從 LINE Developers 建立新 Channel

1. 在 LINE Developers Console 進入你的 Provider
2. 點「**Create a Messaging API channel**」
3. 填寫：
   - Channel name：`叮咚到號`
   - Channel description：`醫院看診進度即時查詢，掛號快到自動通知你`
   - Category：`健康`
   - Subcategory：`健康管理`
4. 勾選同意條款 → Create

> ⚠️ 如果你的 LINE@ 帳號已經存在，建議走 **路線 A**，這樣會自動連結你已建好的 LINE@ 帳號。

---

## 步驟四：取得兩個金鑰

在 LINE Developers Console → 你的 Provider → 你的 Channel：

### 1. Channel Secret

- 點「**Basic settings**」tab
- 找到 **Channel secret**
- 點旁邊的複製按鈕
- 📝 **記下來，等下填到 .env 的 `LINE_CHANNEL_SECRET`**

### 2. Channel Access Token

- 點「**Messaging API**」tab
- 往下滾到 **Channel access token (long-lived)**
- 點「**Issue**」按鈕產生 token
- 點旁邊的複製按鈕
- 📝 **記下來，等下填到 .env 的 `LINE_CHANNEL_ACCESS_TOKEN`**

---

## 步驟五：設定 Webhook（部署完成後再做）

在「**Messaging API**」tab 中：

1. **Webhook URL**：填 `https://你的域名/webhook`
2. 開啟「**Use webhook**」開關
3. 點「**Verify**」測試（需要程式已部署且 Nginx 設好）

---

## 步驟六：關閉自動回覆

在「**Messaging API**」tab 中：

1. 找到「**Auto-reply messages**」，點旁邊的連結進入 LINE Official Account Manager
2. 把「**自動回應訊息**」關閉（設為「停用」）
3. 這樣用戶的訊息才會送到你的程式，而不是被 LINE 內建的自動回覆攔截

---

## 完成後你應該有：

| 項目 | 值 |
|------|-----|
| Channel Secret | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| Channel Access Token | `很長一串 token...` |

把這兩個值填到 VPS 上的 `.env` 檔案中：

```bash
cd /www/wwwroot/medical-queue-notify/
nano .env
```

```
LINE_CHANNEL_SECRET=你的Channel Secret
LINE_CHANNEL_ACCESS_TOKEN=你的Channel Access Token
```

然後就可以進行部署了！
