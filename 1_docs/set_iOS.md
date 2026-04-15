# iOS App 上架完整教學(從零開始)

> 給「完全沒做過 App」的人看的手冊。從註冊帳號到上架成功,所有步驟都在這裡。
>
> 目標:把叮咚到號上架到 Apple App Store。
>
> 預估時間:**第一次做大約 2-3 週**(含學流程、被退件、修正)。寫 code 本身可能只佔 1/3。

---

## 📋 全程地圖

```
Phase 0  觀念入門         你需要先理解這些東西在做什麼
   ↓
Phase 1  Apple 帳號       註冊 Apple Developer Program ($99/年)
   ↓
Phase 2  安裝工具         macOS + Xcode + Node.js + Capacitor
   ↓
Phase 3  Bundle ID        在 Apple 後台註冊 App 的「身分證」
   ↓
Phase 4  APNs Key         產生推播用的金鑰(.p8 檔)
   ↓
Phase 5  Capacitor 包殼   把 PWA 包成 iOS app
   ↓
Phase 6  Xcode 設定       Bundle ID / Capabilities / Signing
   ↓
Phase 7  第一次跑模擬器    在 mac 跑起來看
   ↓
Phase 8  實機測試         在自己的 iPhone 跑
   ↓
Phase 9  App Store Connect 建立 App 紀錄、填資料
   ↓
Phase 10 隱私政策 + 截圖   準備上架素材
   ↓
Phase 11 上傳 build       Archive → 上傳到 App Store Connect
   ↓
Phase 12 提交審核         填好表單送出
   ↓
Phase 13 等待 + 處理退件   通常會被退 1-2 次,改完再送
   ↓
Phase 14 通過!            上架成功 🎉
```

**前 8 個 Phase 是「能在自己手機跑起來」**,後 6 個是「能讓陌生人下載」。
新手最容易卡住的是 **Phase 4 (APNs)** 和 **Phase 13 (被退件)**。

---

## Phase 0:觀念入門 — 你必須先懂這些

寫 code 之前,先弄懂幾個專有名詞,不然後面看 Apple 文件會像看天書。

### 0.1 什麼是「上架到 App Store」?

App Store 是 Apple 控制的軟體市集。**只有 Apple 同意的 App 才能被 iPhone 用戶下載。**

要讓 Apple 同意,你必須:
1. 加入 **Apple Developer Program**(每年 $99 美金,約 NT$3,200)
2. 用 Apple 認可的工具(Xcode)做出 App
3. 用「憑證」(Certificate)簽名你的 App,證明是你做的
4. 上傳到「App Store Connect」(Apple 的後台)
5. 填一堆資料 + 提交審核
6. 通過審核後 → 上架

### 0.2 幾個會一直出現的名詞

| 名詞 | 中文意思 | 大概是 |
|------|---------|--------|
| **Apple ID** | Apple 帳號 | 你的 iCloud 那個帳號 |
| **Apple Developer Account** | Apple 開發者帳號 | 升級成「可以做 App」的 Apple ID |
| **Apple Developer Program** | Apple 開發者計畫 | 每年 $99 的會員資格 |
| **App Store Connect** | App 上架後台 | 上傳 App、填資料、看下載數的地方 |
| **Bundle ID** | App 唯一 ID | 像網域,例如 `com.dindon.queue`,**全世界唯一** |
| **Provisioning Profile** | 配置描述檔 | 告訴 iPhone「這個 App 是誰做的、可以做什麼」 |
| **Certificate** | 簽章憑證 | 證明 App 是你做的,不是別人偽造的 |
| **APNs** | Apple Push Notification service | Apple 的推播伺服器,要發通知必須走它 |
| **APNs Key (.p8)** | 推播金鑰 | 讓你的 server 跟 APNs 講話用的密碼 |
| **TestFlight** | Beta 測試平台 | 上架前先給朋友 / 客戶試用的地方 |
| **Xcode** | Apple 的 IDE | 在 mac 上寫 / build / 上傳 App 的軟體 |
| **Capacitor** | 包殼工具 | 把網頁包成 native app 的工具(我們專案用的) |

### 0.3 流程是什麼?

```
你的網頁(public/index.html)
       ↓ Capacitor 包殼
  iOS 專案(mobile/ios/)
       ↓ Xcode 開啟、設定 Bundle ID
  簽名 + Archive
       ↓ 上傳 App Store Connect
  Apple Review (1-7 天)
       ↓ 通過
  App Store 上架 → 用戶可以下載
```

### 0.4 你必須有什麼?

| 必備 | 說明 |
|------|------|
| **mac 電腦** | iOS App **只能在 mac 上 build**(這是 Apple 規定)。Windows 不行 |
| **macOS 14+** | Xcode 16 需要 |
| **Apple ID** | 你已經有了(就是 iCloud 那個) |
| **信用卡** | 付 $99 開發者費用 |
| **iPhone(iOS 16.4+)** | 實機測試用,iOS 16.4 以下沒 Web Push |
| **Apple Developer 帳號** | 你說你已經有了 ✅ |

---

## Phase 1:確認 Apple Developer 帳號

你說你已經有了,但確認一下:

### 1.1 登入 Apple Developer 後台

打開 https://developer.apple.com/account

用你的 Apple ID 登入。

### 1.2 確認你看到這些東西

- 左邊有 **Certificates, Identifiers & Profiles**
- 左邊有 **Membership**(裡面寫 Active,有效期還沒過)
- 上方有「Join Apple Developer Program」**沒有出現**(出現代表你還沒升級成開發者)

### 1.3 確認你也能登入 App Store Connect

打開 https://appstoreconnect.apple.com

用同一個 Apple ID 登入。能看到「我的 App」頁面就 OK。

> ⚠ **如果看到「您尚未獲准存取此頁面」**:你的開發者帳號還在審核中(初次申請通常 24-48 小時)。等通過再做下一步。

---

## Phase 2:安裝工具

### 2.1 安裝 Xcode

**Xcode 是寫 iOS App 的必備軟體,只有 Mac App Store 能下載。**

1. 打開 mac 上的 **App Store**(內建的)
2. 搜尋 **Xcode**
3. 點「取得」→「安裝」
4. 大約 **15GB**,下載 30 分鐘 ~ 2 小時(看網速)
5. 裝完後打開一次,點「Agree」同意條款,等它跑完 component 安裝(再 10-20 分鐘)

> 💡 **常見問題:Mac App Store 下載很慢?**
> 用 https://developer.apple.com/download/applications/ 下載 .xip 檔(要先登入開發者帳號),解壓後拖到 /Applications/。

### 2.2 確認 Xcode 裝好了

打開 Terminal,執行:

```bash
xcode-select --install   # 如果跳出視窗,點 Install。已裝會說 already installed
xcodebuild -version      # 應該顯示 Xcode 16.x
```

### 2.3 安裝 CocoaPods

iOS 用 **CocoaPods** 管理 native 套件(像 npm)。Capacitor 需要它。

```bash
sudo gem install cocoapods
pod --version            # 應該顯示 1.15+
```

> ⚠ macOS 14+ 系統 Ruby 可能裝不動。改用 Homebrew:
> ```bash
> brew install cocoapods
> ```

### 2.4 安裝 Node.js(如果還沒裝)

```bash
node --version           # 應該 ≥ 18
npm --version            # 應該 ≥ 9
```

沒裝的話:

```bash
brew install node
# 或從 https://nodejs.org 下載安裝包
```

### 2.5 工具清單檢查

跑這個確認全部都裝好:

```bash
echo "macOS:    $(sw_vers -productVersion)"
echo "Xcode:    $(xcodebuild -version | head -1)"
echo "CocoaPods: $(pod --version)"
echo "Node:     $(node --version)"
echo "npm:      $(npm --version)"
```

預期輸出:
```
macOS:    14.5 或更新
Xcode:    Xcode 16.x
CocoaPods: 1.15+
Node:     v20.x
npm:      10.x
```

---

## Phase 3:Bundle ID(註冊 App 身分證)

**Bundle ID 是 App 在全世界唯一的識別碼**,像域名一樣不能跟別人撞。一旦註冊就不能改。

### 3.1 命名規則

格式:**反向網域名**

```
com.公司名.App名
```

範例:
- `com.dindon.queue` ← 我建議叮咚到號用這個
- `com.facebook.Messenger`
- `com.openai.chat`

### 3.2 在 Apple Developer 註冊

1. 開 https://developer.apple.com/account/resources/identifiers/list
2. 點右上 **+**(藍色加號)
3. 選 **App IDs** → **Continue**
4. 選 **App** → **Continue**
5. 填表單:

| 欄位 | 填什麼 |
|------|-------|
| **Description** | `叮咚到號 Queue Notification`(自由命名,會在後台顯示) |
| **Bundle ID** | 選 **Explicit**,輸入 `com.dindon.queue` |
| **Capabilities** | 勾選下面幾個 ↓ |

**Capabilities(很重要,漏勾後面會卡)**:

- ✅ **Push Notifications**(推播必勾)
- ✅ **Sign In with Apple**(我們要做 Apple 登入)
- ✅ **Associated Domains**(LINE deep link 綁定用)

點 **Continue → Register**。

### 3.3 確認 Bundle ID 註冊好了

回到 Identifiers 列表,應該看到:

```
NAME                      IDENTIFIER          CAPABILITIES
叮咚到號 Queue Notif...    com.dindon.queue   Push, Sign In Apple, Assoc Domains
```

### 3.4 把 Bundle ID 寫下來

之後 Xcode 和 capacitor.config 都要用到:

```
Bundle ID: com.dindon.queue
```

---

## Phase 4:APNs Key(推播金鑰)

**這一步是新手最容易卡的地方。**APNs Key 是你的 server 用來「叫 Apple 發推播」的密碼。

### 4.1 為什麼需要 APNs Key?

```
你的 server          Apple 的伺服器          用戶 iPhone
    │                      │                       │
    │  「幫我發通知給 X 用戶」                       │
    │ ────APNs Key──────►   │                       │
    │                      │ ──────推播──────►      │
    │                      │                       │ 🔔 叮咚!
```

沒 APNs Key,你的 server 對 Apple 「無口」。

### 4.2 兩種 key 格式:`.p8` vs `.p12`

| 格式 | 優點 | 缺點 |
|------|------|------|
| **`.p8` (Token-based)** | **永不過期**、一個 key 給多個 App 用、簡單 | (沒缺點) |
| `.p12` (Cert-based) | (沒優點) | 每年都會過期、要重新產生、很煩 |

**👉 一定用 `.p8`,別碰 .p12。**

### 4.3 產生 .p8 Key

1. 開 https://developer.apple.com/account/resources/authkeys/list
2. 點右上 **+**
3. 填:
   - **Key Name**: `叮咚到號 APNs`(自由命名)
   - 勾選 **Apple Push Notifications service (APNs)**
4. 點 **Continue → Register**
5. **這個畫面非常重要!**
   - 點 **Download** → 下載 `AuthKey_XXXXXXXXXX.p8`
   - **這個檔案只能下載一次!下載完不見就要重新產生!**
   - 把它存到一個你不會弄丟的地方(例如 `~/Documents/keys/AuthKey_XXX.p8`)
6. 記下這 3 個東西(後端設定要用):

```
Key ID:      ABCD123456              ← 在這個畫面顯示
Team ID:     1A2B3C4D5E              ← 在右上角你的名字旁邊
Bundle ID:   com.dindon.queue        ← 上一 Phase 註冊的
.p8 file:    AuthKey_ABCD123456.p8   ← 剛下載的檔案
```

### 4.4 把這些值寫進 .env(本地 + server 端)

之後 Phase 4 推播路由器要用。**現在先記下來不用設定**,我們在 Phase 4 一起做。

```bash
# 之後會加進 .env(現在只是預備)
APNS_KEY_ID=ABCD123456
APNS_TEAM_ID=1A2B3C4D5E
APNS_BUNDLE_ID=com.dindon.queue
APNS_AUTH_KEY_PATH=/app/secrets/AuthKey_ABCD123456.p8
```

> ⚠ **千萬不要把 .p8 檔 commit 到 git!** 加到 `.gitignore`:
> ```
> *.p8
> secrets/
> ```

---

## Phase 5:Capacitor 包殼(把 PWA 變 iOS App)

現在叮咚到號的 `public/index.html` 已經是 PWA。Capacitor 會把它包成原生 iOS App。

### 5.1 在專案根目錄初始化 Capacitor

```bash
cd /Users/macpro-david/Library/CloudStorage/Dropbox/84-WebCode/01-mac/5-ajz/api-dindon

# 建一個 mobile/ 子目錄,iOS 和 Android 專案會放在這
mkdir -p mobile
cd mobile

# 初始化 npm 專案
npm init -y

# 安裝 Capacitor
npm install @capacitor/core @capacitor/cli

# 初始化 Capacitor 設定(會問問題)
npx cap init "叮咚到號" "com.dindon.queue" --web-dir="../public"
```

詢問時的回答:
- **App name**: `叮咚到號`
- **App ID**: `com.dindon.queue`(和 Bundle ID 一致)
- **Web directory**: `../public`(相對路徑指向我們的 PWA)

### 5.2 安裝 iOS 平台

```bash
npm install @capacitor/ios
npx cap add ios
```

這會在 `mobile/ios/` 建立一個完整的 Xcode 專案。

### 5.3 安裝必要的 Capacitor plugins

```bash
npm install \
  @capacitor/push-notifications \
  @capacitor/app \
  @capacitor/preferences \
  @capacitor/network \
  @capacitor-community/apple-sign-in
```

### 5.4 同步到 iOS 專案

每次改 `public/` 內容或裝新 plugin,都要跑這個:

```bash
npx cap sync ios
```

`sync` 做兩件事:
1. 把 `../public/` 內容複製到 iOS 專案
2. 把 plugin 註冊到 native code

### 5.5 用 Xcode 開啟專案

```bash
npx cap open ios
```

這會自動用 Xcode 開啟 `mobile/ios/App/App.xcworkspace`。

> ⚠ **一定要打開 `.xcworkspace`,不是 `.xcodeproj`!** 沒打對 CocoaPods 會壞掉。

---

## Phase 6:Xcode 設定

第一次開 Xcode 會花 1-2 分鐘 indexing。等它跑完。

### 6.1 設定 Bundle ID

1. 左邊樹狀選 **App**(最頂層那個藍色 icon)
2. 中間區選 **TARGETS → App**
3. 上面分頁選 **Signing & Capabilities**
4. **Bundle Identifier** 改成 `com.dindon.queue`(必須跟 Phase 3 註冊的一樣)

### 6.2 設定 Team

同一個畫面:

1. **Team** 下拉 → 選你的開發者帳號名稱
2. 如果沒看到,點 **Add an Account...** → 用 Apple ID 登入

### 6.3 加 Capabilities

1. 點 **+ Capability**(畫面左上)
2. 雙擊 **Push Notifications** 加入
3. 再點 **+ Capability** → **Sign In with Apple**

加完應該看到:

```
┌─────────────────────────────────┐
│ Push Notifications              │
└─────────────────────────────────┘
┌─────────────────────────────────┐
│ Sign In with Apple              │
└─────────────────────────────────┘
```

### 6.4 改 App 名稱(顯示在 home screen 上的)

1. 左邊樹狀選 **App → Info.plist**
2. 找 `Bundle display name`(沒有就加一個)
3. 值填 `叮咚到號`

或更直接:展開 Info.plist 找 `CFBundleDisplayName`,改成 `叮咚到號`。

---

## Phase 7:第一次跑模擬器

### 7.1 選模擬器

Xcode 上方:

```
[App] [iPhone 15 Pro] ▶
       ↑
       這個下拉選 iPhone 15 / 14 / 13(任何 iOS 16.4+ 的)
```

### 7.2 按 ▶ Run

第一次會花 2-5 分鐘 build。完成後:

- 模擬器自動開啟
- 你看到叮咚到號的對話介面跑在裡面
- 跟你在 Safari 看到的一樣,但它現在是「原生 App」

### 7.3 測試

- 點數字按鈕,看互動有沒有反應
- 試試選台大醫院 → 0 返回
- **網路請求**會打到 https://dd.dl-app.com(因為我們的 PWA 內 JS 用絕對 URL)

> ⚠ **如果模擬器是空白的**:看 Xcode 左下 console。最常見問題是 web_dir 路徑錯,或 `npx cap sync` 沒跑。

---

## Phase 8:實機測試(在你自己 iPhone 跑)

### 8.1 把 iPhone 接到 mac

用 USB 線。第一次連會問「信任這台電腦?」→ 信任。

### 8.2 在 iPhone 啟用「開發者模式」(iOS 16+)

iPhone 上:**設定 → 隱私權與安全性 → 開發者模式 → 開啟 → 重開機**。

### 8.3 在 Xcode 選你的 iPhone

```
[App] [張三的 iPhone] ▶
       ↑
       下拉選你的實機(會顯示你 iPhone 的名稱)
```

### 8.4 按 ▶ Run

第一次會說「Untrusted Developer」。在 iPhone 上:

**設定 → 一般 → VPN 與裝置管理 → Developer App → 信任**。

再按 ▶ 一次就會跑起來。

### 8.5 測試 Web Push(實際收推播)

**這是最重要的測試**:

1. 在 iPhone 上開 App
2. 系統會跳「叮咚到號想要傳送通知」 → **允許**
3. 在 mac 上跑(用你 LIFF 註冊的 line_user_id):

```bash
curl -X POST https://dd.dl-app.com/api/push/test \
  -H 'Content-Type: application/json' \
  -d '{"line_user_id":"YOUR_LINE_USER_ID","title":"叮咚到號","body":"實機測試成功!"}'
```

> ⚠ **這一步現在還收不到 native push**,因為 Phase 4 (APNs 整合)還沒做。
> 你能收到的是 PWA 的 Web Push(只在 Safari / 加到主畫面的版本有用)。
> Phase 3 + 4 完成後才會走 APNs。

---

## Phase 9:App Store Connect 建立 App 紀錄

你的 App 能在自己手機跑了,接下來要讓別人下載 → 必須上架。

### 9.1 開啟 App Store Connect

https://appstoreconnect.apple.com → **我的 App** → **+** → **新增 App**

### 9.2 填表單

| 欄位 | 填什麼 |
|------|-------|
| **平台** | iOS |
| **名稱** | `叮咚到號`(會顯示在 App Store) |
| **主要語言** | 繁體中文 |
| **Bundle ID** | 下拉選 `com.dindon.queue`(Phase 3 註冊的會出現在這) |
| **SKU** | `dindon-ios-001`(自由命名,內部識別,通常用 bundle id 變體) |
| **使用者存取權** | 完整存取權 |

點 **建立**。

### 9.3 接下來會看到一堆要填的東西

不用一次填完。先把這幾個必填先填一下,後面其他 Phase 會回來補:

- **App 資訊** → **類別**:選「醫療」或「健康與健身」
- **價格與供應狀況** → 「免費」 + 「所有地區」(或只台灣)
- **App 隱私權** → 之後要填(Phase 10 會做)

---

## Phase 10:準備上架素材

App Store 審核員會看這些東西。**少一樣會被退**。

### 10.1 App icon(1024 × 1024)

**真正的上架 icon,不是 placeholder。**

Phase 1 PWA 用的是 placeholder 綠圓 + 「叮咚」字。上架前要換成真正設計的:

選擇:
- **A) 找設計師畫一個**(推薦,Fiverr / 接案網約 NT$1000-3000)
- B) 自己用 Figma 畫
- C) 用 AI 工具(Midjourney / DALL-E)生一個再優化

要求:
- **1024 × 1024 px**
- **PNG**,沒有 alpha channel(透明背景)
- **不要圓角**(Apple 自動加)
- **不要 Apple logo**、不要 emoji 當主視覺
- **不要文字太多**(在 home screen 上很小看不清楚)

### 10.2 螢幕截圖

Apple 要求**至少 2 種尺寸**的截圖,各 2-10 張:

| 設備 | 解析度 | 必須? |
|------|--------|-------|
| **iPhone 6.7"** (15 Pro Max) | 1290 × 2796 | ✅ 必須 |
| **iPhone 6.5"** (XS Max) | 1242 × 2688 | ✅ 必須 |
| iPhone 5.5" (8 Plus) | 1242 × 2208 | 選擇 |
| iPad 12.9" | 2048 × 2732 | 只有 iPad app 才要 |

**怎麼截圖?**

用 Xcode 模擬器:
1. 選對應 iPhone(模擬器選 iPhone 15 Pro Max → 6.7")
2. 跑 App
3. 進入要截的畫面
4. **Cmd + S**(模擬器內)→ 截圖存到桌面

每張截圖要展示一個賣點,例如:
1. 主畫面對話介面
2. 醫院列表
3. 追蹤中畫面(看診號碼顯示)
4. 推播通知範例(可以用合成圖)
5. Live Activity 鎖屏(Phase 3.5 後)

### 10.3 隱私政策(必須有 URL)

**Apple 強制要求**。沒有 = 直接退件。

你需要一個公開可訪問的 URL,內容要說明:

- 收集什麼資料(LINE user ID、push token、追蹤的醫院/醫生)
- 用來做什麼(推播通知、改善服務)
- 跟誰分享(沒有第三方,或列出來)
- 用戶怎麼刪除資料(提供 email 聯絡)
- 安全措施

**最簡做法**:寫一個 `public/privacy.html`,部署後 URL 是 `https://dd.dl-app.com/privacy`。

範本:

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><title>叮咚到號隱私政策</title></head>
<body>
<h1>隱私政策</h1>
<p>更新日期:2026-04-11</p>

<h2>1. 收集的資料</h2>
<ul>
  <li>LINE 用戶 ID(用於識別您的帳號)</li>
  <li>推播 token(用於發送通知)</li>
  <li>您追蹤的醫院、科別、醫生資訊</li>
  <li>裝置型號、作業系統版本(用於除錯)</li>
</ul>

<h2>2. 資料用途</h2>
<p>所有資料僅用於提供看診進度通知服務,不會用於廣告或行銷。</p>

<h2>3. 資料分享</h2>
<p>本服務不會將您的個人資料分享給任何第三方,除非法律強制要求。</p>

<h2>4. 資料刪除</h2>
<p>如需刪除您的所有資料,請來信:admin@dl-app.com</p>

<h2>5. 聯絡方式</h2>
<p>Email: admin@dl-app.com</p>
</body>
</html>
```

### 10.4 服務條款 / Terms(可選但建議)

`public/terms.html` — 同樣的概念。Apple 沒強制但 Google 強制,順便寫好。

### 10.5 Demo 帳號(審核員測試用)

Apple 審核員會親自測你的 App。如果需要登入,你必須給:

- 一個測試用的 Apple ID + 密碼(在 App Store Connect 後台填)
- 或:LINE 測試帳號的 line_user_id(寫在「審核資訊」備註裡)

**沒給 demo 帳號 = 一定被退**。

### 10.6 App 描述文案

範本:

**App 名稱**: 叮咚到號

**副標題**(30 字內): 即時掌握醫院看診進度

**描述**(4000 字內):
```
叮咚到號是台灣最即時的醫院看診進度追蹤 App。

✓ 涵蓋全台 29 家主要醫院
✓ 看診號碼快到時自動推播,不錯過叫號
✓ 鎖屏持續顯示目前號碼(Live Activity)
✓ 支援多位醫師同時追蹤
✓ 完全免費

支援醫院:
台大醫院、台北榮總、三軍總醫院、台北長庚、林口長庚、高雄長庚、馬偕醫院、新光醫院、亞東醫院、台中榮總...等 29 家

【免費版】1 位醫師追蹤
【訂閱版】3 位醫師追蹤 + 即時推播 + 鎖屏顯示

關於我們:
本服務由獨立開發者維護,不隸屬任何醫療機構。
```

**關鍵字**(100 字內,半形逗號分隔):
```
叮咚,看診,叫號,醫院,掛號,排隊,通知,健保,看醫生,等號
```

**聯絡 Email**: 你的 email(會公開顯示)

---

## Phase 11:上傳 build 到 App Store Connect

### 11.1 在 Xcode 選 「Any iOS Device」

```
[App] [Any iOS Device (arm64)] ▶
       ↑
       不要選模擬器,要選這個
```

### 11.2 Archive

選單列:**Product → Archive**

跑 5-10 分鐘。完成後 Xcode 會自動跳出 **Organizer** 視窗。

### 11.3 在 Organizer 上傳

1. 選剛 archive 的版本(列表第一個)
2. 點右邊 **Distribute App**
3. 選 **App Store Connect** → **Next**
4. 選 **Upload** → **Next**
5. 一直 Next(預設值都對)
6. 最後點 **Upload**
7. 等 5-15 分鐘上傳完成

> ⚠ 中途如果說「missing compliance」之類:回去 App Store Connect,在 App 設定的 **加密 export 合規性**勾「不使用加密」(我們沒用 custom encryption,只用 HTTPS)。

### 11.4 等 Apple 處理 build

上傳完不是立刻就能用。Apple 要先 **process** build(15 分鐘 ~ 1 小時)。

去 https://appstoreconnect.apple.com → 你的 App → **TestFlight** 分頁。

等到 build 從 **Processing** 變成可選狀態。

---

## Phase 12:提交審核

回到 App Store Connect,你的 App 頁面。

### 12.1 在側邊「iOS App」下選「準備送審」版本

填這些:

- **此版本內容** (What's New): 寫第一版的話可以填 `首次發布`
- **此版本可用內容** → **建置版本** → 選你剛剛上傳的 build

### 12.2 確認所有資料都填完

左邊側邊應該全綠勾:

- ✅ App 資訊
- ✅ 價格與供應狀況
- ✅ 1.0 準備送審
- ✅ App 隱私權

### 12.3 點右上「加入以供審核」 → 「送出以供審核」

填審核資訊:

- **聯絡資訊**: 你的姓名 / phone / email
- **示範帳號**: LINE user ID 或 demo 帳號
- **備註**: 寫給審核員的話,例如:

```
此 App 會抓取台灣各醫院公開的看診進度資料,並透過推播通知用戶。
若需要 LINE 帳號測試,可使用以下測試帳號:
  Line ID: testdindon01
  
測試流程:
1. 開啟 App
2. 主畫面選「4 台大醫院」
3. 選任一科別 → 選任一醫師 → 輸入號碼 999(僅追蹤模式)
4. 系統會 polling 看診進度

若有任何問題,請聯絡:admin@dl-app.com
```

點 **Submit**。

---

## Phase 13:等待 + 處理退件

### 13.1 審核時間

通常 **24-48 小時**。週末或節日會慢。

### 13.2 你會收到 email:通過 或 Rejected

**通過(Approved)**:
- 你會收到「您的 App 已準備好出售」的 email
- 點 App Store Connect 後台 → 確認上架日期 → 自動上架

**被退(Rejected)**:
- 不要慌,**80% 的 App 第一次都會被退**
- email 會說明原因(很模糊)
- 點 **Resolution Center** 看詳細

### 13.3 常見退件原因 + 對策

| 退件原因 | 對策 |
|---------|------|
| **2.1 (Performance — Crashes)** | App 在審核員裝置 crash → 看 crash log,修了再 build 上傳 |
| **2.3.10 (Inaccurate Metadata)** | 截圖跟實際 App 不符 → 重截 |
| **4.0 (Design — Spam)** | 「就是個網頁包殼,沒提供原生價值」→ 寫一段說明強調你有 native push / Live Activity / Sign in with Apple |
| **5.1.1 (Privacy)** | 隱私政策不夠清楚 → 重寫 |
| **5.1.2 (Sign in with Apple required)** | 你有 Google / LINE 登入,沒提供 Apple → 加 Sign in with Apple |
| **2.3.3 (Screenshots)** | 截圖品質不夠 / 不對應 device size → 重截 |
| **Missing demo account** | 沒給測試帳號 → 補 |

### 13.4 被退之後怎麼辦

1. 進 App Store Connect → Resolution Center
2. 看詳細退件理由
3. **回覆 Apple**(可以申訴,但通常沒用,直接修)
4. 修問題 → 重新 archive → 重新上傳 → 重新送審
5. 通常第二次會比第一次快(2 小時 ~ 24 小時)

---

## Phase 14:上架成功 🎉

### 14.1 你的 App 出現在 App Store

任何人在 App Store 搜尋「叮咚到號」都能下載。

### 14.2 一定要做的事

**馬上做**:
1. 自己用「另一支手機 / 另一個 Apple ID」搜尋並下載一次,確認真的能裝
2. 把 App Store URL 分享給朋友 5-10 人請他們下載 + 給意見

**第一週**:
3. 在 App Store Connect 看每天下載數 + crash 率
4. 看 crash log,修任何 critical bug
5. 收集用戶 review,回覆(有 review 顯示你在乎用戶,排名會升)

**長期**:
6. 每次更新 App 都要重新 build → archive → 上傳 → 送審(但通常 < 24 小時)
7. 每年要付 $99 續費,沒續費 App 會下架!

---

## 🆘 常見問題 / 坑

### Q1: 「Bundle ID 已被使用」
A: 換一個。`com.dindon.queue` 被佔了就用 `com.dingdong.queue` 或 `tw.dindon.queue`。

### Q2: 「No signing certificate found」
A: Xcode → Settings → Accounts → 你的 Apple ID → Manage Certificates → + → Apple Development。

### Q3: 「Xcode 跑很慢 / build 一次要 30 分鐘」
A: Mac 規格不夠。M1 以上會快很多。或把 Xcode 的 Derived Data 清掉:
```bash
rm -rf ~/Library/Developer/Xcode/DerivedData
```

### Q4: 「Archive 時 build 成功但 archive 失敗」
A: 通常是 Bundle ID / certificate 不對。確認:
- Bundle ID 跟 Apple Developer 註冊的一致
- Signing 用「Automatically manage signing」
- Team 選對了

### Q5: 「上傳到 App Store Connect 卡住」
A: 用 mac 內建的 **Transporter** App(從 Mac App Store 下載)。從 Xcode export ipa 後用 Transporter 上傳更穩定。

### Q6: 「審核員說 App 不能用」
A: 99% 是審核員所在地區無法連到 dd.dl-app.com,或沒給 demo 帳號。在「審核資訊備註」寫清楚怎麼測。

### Q7: 「推播收不到」
A: 順序檢查:
1. iPhone 設定 → 通知 → 叮咚到號 → **允許通知** 是不是開
2. App 內 `Notification.permission` 是不是 `granted`
3. 後端有沒有正確存到 device token
4. APNs key 對不對,Bundle ID 跟 .p8 是不是同一個
5. APNs payload 格式對不對(看 Apple 文件)

### Q8: 「Test 用 Sandbox 還是 Production?」
A: Xcode build & run 走 **sandbox APNs**。Archive + TestFlight + App Store 走 **production APNs**。
你的後端要能切換,看用戶 device token 來源決定走哪個。

---

## 📚 延伸閱讀

| 主題 | 連結 |
|------|------|
| Apple Developer 官方文件 | https://developer.apple.com/documentation/ |
| Capacitor 官方文件 | https://capacitorjs.com/docs/ios |
| App Store Review Guidelines | https://developer.apple.com/app-store/review/guidelines/ |
| Human Interface Guidelines | https://developer.apple.com/design/human-interface-guidelines/ |
| TestFlight 教學 | https://developer.apple.com/testflight/ |

---

## 一頁速查 Cheat Sheet

```
工具
├── mac (macOS 14+)
├── Xcode 16+
├── CocoaPods
├── Node 18+
└── 你的 iPhone (iOS 16.4+)

帳號
├── Apple ID
└── Apple Developer Program ($99/年)

關鍵 ID(全記下來)
├── Bundle ID:    com.dindon.queue
├── Team ID:      <在開發者帳號右上角>
├── APNs Key ID:  <產生 .p8 時顯示>
└── App Store Connect SKU: dindon-ios-001

關鍵檔案(備份好)
├── AuthKey_XXX.p8       APNs 推播 key,丟了就要重新產
└── 開發者帳號的 password 跟 2FA  千萬不要弄丟

關鍵指令
├── npx cap sync ios     同步 PWA 到 iOS 專案
├── npx cap open ios     用 Xcode 開啟
├── Cmd + R              在 Xcode 跑模擬器
└── Product → Archive    準備上傳

關鍵 URL
├── https://developer.apple.com/account
├── https://appstoreconnect.apple.com
└── https://dd.dl-app.com/privacy(隱私政策必須上線)
```

---

**STATUS:** 看完這份就能從零做到 iOS App 上架。卡住任何 Phase 來問我。

下一步應該配合 [`set_android.md`](./set_android.md) 同時準備 Android 上架(可以平行做)。
