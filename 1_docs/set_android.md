# Android App 上架完整教學(從零開始)

> 給「完全沒做過 App」的人看的手冊。從註冊帳號到上架成功,所有步驟都在這裡。
>
> 目標:把叮咚到號上架到 Google Play Store。
>
> 預估時間:**第一次做大約 1-2 週**(比 iOS 簡單,但 Google 的規則比較雜)。
>
> **好消息:** Android 上架比 iOS 簡單,可以在 Mac / Windows / Linux 任何電腦做。

---

## 📋 全程地圖

```
Phase 0  觀念入門            理解這些東西在做什麼
   ↓
Phase 1  Google Play 帳號    確認 Developer Console 帳號
   ↓
Phase 2  安裝工具            Android Studio + JDK + Node.js + Capacitor
   ↓
Phase 3  Application ID      App 的「身分證」(類似 Bundle ID)
   ↓
Phase 4  Firebase + FCM      建 Firebase 專案、產 google-services.json
   ↓
Phase 5  Capacitor 包殼      把 PWA 包成 Android App
   ↓
Phase 6  Android Studio 設定 ApplicationId / Permissions / SHA-1
   ↓
Phase 7  第一次跑模擬器       在 Android Studio 跑虛擬裝置
   ↓
Phase 8  實機測試            在自己 Android 手機跑
   ↓
Phase 9  Keystore 簽章       產生 App 的「永久身分證」(這個丟了 = App 死)
   ↓
Phase 10 Google Play Console 建立 App 紀錄、填資料
   ↓
Phase 11 隱私政策 + 截圖     準備上架素材
   ↓
Phase 12 上傳 build (.aab)   Build → Generate Signed Bundle → 上傳
   ↓
Phase 13 Internal Testing   先在內部測試(必須步驟)
   ↓
Phase 14 提交審核(Production) 填好表單送出
   ↓
Phase 15 等待 + 處理退件     通常會被退 1-2 次,改完再送
   ↓
Phase 16 通過!上架成功 🎉
```

**新手最容易卡住的:Phase 9 (Keystore 千萬不能丟)** 和 **Phase 4 (Firebase 設定)**。

---

## Phase 0:觀念入門 — 你必須先懂這些

### 0.1 什麼是 Google Play Store?

Google 的 Android 軟體市集。用戶大部分(全世界 70%+)Android 手機都用 Play Store 下載 App。

但 Android 跟 iOS 不一樣:
- **iOS:只能透過 App Store 下載**(被 Apple 完全控制)
- **Android:可以裝 Play Store 以外的 App**(.apk 檔可以直接傳給朋友裝)

但你還是要上架 Play Store,因為:
1. Play Store 是用戶找 App 的主要管道
2. 自動更新
3. 信任度(用戶願意裝)
4. 收費機制(Google Play Billing)

### 0.2 幾個會一直出現的名詞

| 名詞 | 中文 | 大概是 |
|------|------|--------|
| **Google Account** | Google 帳號 | 你的 Gmail 那個 |
| **Google Play Console** | Play 開發者後台 | 上架、看下載數的地方 |
| **Application ID** | App 唯一 ID | 像 `com.dindon.queue`,**全世界唯一** |
| **APK** | Android Package | 老格式的 App 安裝檔(以前用) |
| **AAB** | Android App Bundle | 新格式(2021 年起 Play Store **強制**) |
| **Keystore (.jks/.keystore)** | 簽章金鑰 | App 的「永久身分證」,**千萬不能丟** |
| **FCM** | Firebase Cloud Messaging | Google 的推播服務,等於 Android 版 APNs |
| **google-services.json** | Firebase 設定檔 | 連接 App 跟 Firebase 用 |
| **Android Studio** | Google 的 IDE | 寫 / build / 上傳 App 的軟體 |
| **adb** | Android Debug Bridge | 命令列工具,跟 Android 裝置通訊 |
| **Internal Testing** | 內部測試 | 上架前先給少數人測 |
| **SHA-1 Fingerprint** | 簽章指紋 | Firebase / Google 服務認證用 |

### 0.3 流程是什麼?

```
你的網頁(public/index.html)
       ↓ Capacitor 包殼
  Android 專案(mobile/android/)
       ↓ Android Studio 開啟、設定 App ID
  簽名(用 keystore)+ Build AAB
       ↓ 上傳 Google Play Console
  Google Review (1-7 天,通常很快)
       ↓ 通過
  Play Store 上架 → 用戶可以下載
```

### 0.4 你必須有什麼?

| 必備 | 說明 |
|------|------|
| **電腦** | mac / Windows / Linux 都行(不像 iOS 只能用 mac) |
| **8GB+ RAM** | Android Studio 吃記憶體,4GB 會很慘 |
| **Google 帳號** | 你已經有了 |
| **信用卡** | 付 $25 開發者費(一次性,不是每年) |
| **Android 手機 (Android 8+)** | 實機測試用,模擬器也行但實機更準 |
| **Google Play Developer 帳號** | 你說已經有了 ✅ |

---

## Phase 1:確認 Google Play Developer 帳號

### 1.1 登入 Google Play Console

打開 https://play.google.com/console

用你的 Google 帳號登入。

### 1.2 確認你看到這些

- 左邊有 **所有應用程式**
- 上面有「**建立應用程式**」按鈕
- 沒看到「升級為開發者」這種訊息(代表你已經升級)

### 1.3 確認付款狀態

**設定 → 開發者帳戶 → 帳戶詳細資料**

應該顯示:
- ✅ 註冊費已繳($25 USD)
- ✅ 帳戶狀態:有效

> ⚠ **如果還在「審核中」**:等通過。Google 現在審 1-3 天(以前快多了)。

---

## Phase 2:安裝工具

### 2.1 安裝 Android Studio

**Android Studio 是 Google 官方 IDE,寫 Android App 的必備工具。**

下載: https://developer.android.com/studio

裝完打開,第一次會跑 setup wizard:
1. **Type of setup**: Standard
2. **JDK**: 用內建的(不要選 system JDK,會出問題)
3. **Android SDK**: 全部下載(SDK Platform / Build-Tools / Emulator)
4. 點 **Next** → **Finish**

第一次會下載 **3-5 GB**(SDK + emulator + system images),花 30 分鐘到 2 小時。

### 2.2 確認 Android Studio + SDK 裝好

打開 Terminal:

```bash
# Android SDK 路徑(macOS 預設)
echo $ANDROID_HOME
# 如果空的,加到 ~/.zshrc:
echo 'export ANDROID_HOME=$HOME/Library/Android/sdk' >> ~/.zshrc
echo 'export PATH=$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/tools' >> ~/.zshrc
source ~/.zshrc

# 確認 adb (Android Debug Bridge)
adb version
# 應該顯示 Android Debug Bridge version 1.0.41 或更新
```

### 2.3 安裝 Java JDK 17(Capacitor 7+ 需要)

Android Studio 內建有 JDK,但 Capacitor 命令列要另一個。

```bash
# macOS
brew install openjdk@17

# 加到 PATH
echo 'export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# 確認
java -version    # 應該顯示 17.x
javac -version   # 應該顯示 17.x
```

### 2.4 安裝 Node.js(如果還沒裝)

```bash
node --version    # ≥ 18
npm --version     # ≥ 9
```

沒裝的話 `brew install node`。

### 2.5 工具清單檢查

```bash
echo "Android Studio: $(ls /Applications/Android\ Studio.app 2>/dev/null && echo 'OK' || echo 'NOT FOUND')"
echo "ANDROID_HOME: $ANDROID_HOME"
echo "adb: $(adb version 2>/dev/null | head -1)"
echo "Java: $(java -version 2>&1 | head -1)"
echo "Node: $(node --version)"
```

---

## Phase 3:Application ID(註冊 App 身分證)

跟 iOS 的 Bundle ID 概念一樣,**全世界唯一**,一旦上架就**不能改**。

### 3.1 命名規則

```
com.公司名.App名
```

**強烈建議跟 iOS 用一樣的:**

```
com.dindon.queue
```

兩邊用一樣有什麼好處:
- Firebase 設定可以共用
- Deep link 可以共用
- 後端不用區分 iOS / Android user

### 3.2 不需要事先註冊

跟 iOS 不一樣 — Android 的 Application ID **不需要事先在 Google 註冊**。
你直接在 Phase 5 設好,Phase 12 上傳時 Google 才會檢查。

但要注意:**第一次上傳到 Play Console 之後就鎖死了,改不了**。

---

## Phase 4:Firebase + FCM(推播)

**這一步是 Android 最容易卡的地方。**FCM (Firebase Cloud Messaging) 是 Google 的推播服務,等於 Android 版 APNs。

### 4.1 為什麼需要 Firebase?

```
你的 server          Firebase 伺服器        用戶 Android 手機
    │                      │                       │
    │  「幫我發通知給 X 用戶」                       │
    │ ──FCM HTTP v1───►    │                       │
    │ (用 service account)  │ ──────推播──────►      │
    │                      │                       │ 🔔 叮咚!
```

跟 iOS 不一樣:Android 推播必須走 Firebase,不能直接打 Google。

### 4.2 建 Firebase 專案

1. 開 https://console.firebase.google.com
2. 點 **新增專案**
3. 填:
   - **專案名稱**: `叮咚到號`(自由命名)
   - **Project ID**: 自動生成(可以改成 `dindon-queue`)
4. **Google Analytics**: 可以選不啟用(我們現在不需要分析)
5. 點 **建立專案**,等 1 分鐘

### 4.3 在 Firebase 加 Android App

1. 在 Firebase 專案首頁,點 **Android 圖示**(或「新增應用程式 → Android」)
2. 填:
   - **Android package name**: `com.dindon.queue`(必須跟 Phase 3 一致)
   - **App nickname**: `叮咚到號 Android`
   - **Debug signing certificate SHA-1**: 先不填,Phase 9 之後再回來填
3. 點 **註冊應用程式**
4. **下載 google-services.json** ← 這個檔案很重要!
5. **暫時存到 `~/Documents/keys/google-services.json`**(Phase 5 會用)
6. 後面的「新增 Firebase SDK」步驟先跳過(Capacitor 會處理)

### 4.4 啟用 FCM HTTP v1 API

**重要,沒做這步推播不會動。**

1. 開 https://console.cloud.google.com
2. 選你剛剛建的 Firebase 專案
3. 左邊選單 **APIs & Services → Library**
4. 搜尋 `Firebase Cloud Messaging API`
5. 點進去 → **Enable**(如果已啟用就不用做)

### 4.5 產生 Service Account Key(後端用)

**這是你後端發推播時用的密碼。**

1. 開 https://console.firebase.google.com → 你的專案
2. **設定齒輪 → 專案設定 → 服務帳戶**
3. 選 **Firebase Admin SDK**
4. 點 **Generate new private key**
5. **下載 .json 檔**(會叫 `dindon-queue-firebase-adminsdk-XXX.json`)
6. **存到 `~/Documents/keys/firebase-admin-sdk.json`**(後端 Phase 4 會用)

> ⚠ **千萬不要 commit 這兩個檔到 git!**
> 加到 `.gitignore`:
> ```
> google-services.json
> firebase-admin-sdk.json
> *.keystore
> *.jks
> ```

### 4.6 寫下要用到的值(預備)

```bash
# 之後 Phase 4 後端推播要用
FCM_PROJECT_ID=dindon-queue                              # Firebase 專案 ID
FCM_CREDENTIALS_JSON_PATH=/app/secrets/firebase-admin-sdk.json
ANDROID_PACKAGE_NAME=com.dindon.queue
```

---

## Phase 5:Capacitor 包殼(把 PWA 變 Android App)

如果你已經做過 [`set_iOS.md`](./set_iOS.md) 的 Phase 5,Capacitor 已經初始化完了,**這 Phase 大部分可以跳過**,只要加 Android 平台。

### 5.1(如果還沒做過 iOS Phase 5)初始化 Capacitor

```bash
cd /Users/macpro-david/Library/CloudStorage/Dropbox/84-WebCode/01-mac/5-ajz/api-dindon

mkdir -p mobile
cd mobile

npm init -y
npm install @capacitor/core @capacitor/cli

npx cap init "叮咚到號" "com.dindon.queue" --web-dir="../public"
```

### 5.2 安裝 Android 平台

```bash
npm install @capacitor/android
npx cap add android
```

這會在 `mobile/android/` 建立完整的 Android Studio 專案。

### 5.3 安裝 Capacitor plugins(如果還沒裝)

```bash
npm install \
  @capacitor/push-notifications \
  @capacitor/app \
  @capacitor/preferences \
  @capacitor/network
```

> 註:Google 登入用 `@codetrix-studio/capacitor-google-auth`,在 Phase 6 設定。

### 5.4 把 google-services.json 放進 Android 專案

```bash
cp ~/Documents/keys/google-services.json mobile/android/app/google-services.json
```

> ⚠ **路徑很重要!** 必須在 `mobile/android/app/` 內,不是 `mobile/android/`。

### 5.5 同步到 Android 專案

```bash
npx cap sync android
```

`sync` 做兩件事:
1. 複製 `../public/` 內容
2. 安裝 plugin 的 native code

### 5.6 用 Android Studio 開啟專案

```bash
npx cap open android
```

第一次會跑 **Gradle sync**(下載 Android dependencies),要 5-15 分鐘。

> ⚠ **Gradle sync 失敗常見原因**:
> - 網路慢/被擋:設定 proxy 或換網路
> - JDK 版本不對:Android Studio → Settings → Build → Build Tools → Gradle → Gradle JDK 設為 17
> - 第一次跑要超久,**有耐心**

---

## Phase 6:Android Studio 設定

### 6.1 確認 Application ID

1. 左邊樹狀展開 **app/build.gradle**(注意:選 module-level 那個,不是 project-level)
2. 找這幾行:

```gradle
defaultConfig {
    applicationId "com.dindon.queue"      // ← 確認跟 Phase 3 一致
    minSdkVersion 22
    targetSdkVersion 34
    versionCode 1                          // ← 內部版號,每次上傳要 +1
    versionName "1.0.0"                    // ← 顯示給用戶看的版號
}
```

如果不對就改。

### 6.2 加 google-services 插件(如果 Capacitor 沒自動加)

`mobile/android/build.gradle` (project-level) 加:

```gradle
buildscript {
    dependencies {
        classpath 'com.google.gms:google-services:4.4.2'
    }
}
```

`mobile/android/app/build.gradle` (module-level) **底部** 加:

```gradle
apply plugin: 'com.google.gms.google-services'
```

> Capacitor 7 應該會自動處理,但如果 build 出錯說 `google-services.json missing` 就手動加。

### 6.3 加 Permissions

`mobile/android/app/src/main/AndroidManifest.xml` 內 `<manifest>` 標籤內(在 `<application>` 之前)加:

```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
<uses-permission android:name="android.permission.WAKE_LOCK"/>
<uses-permission android:name="android.permission.VIBRATE"/>
```

`POST_NOTIFICATIONS` 是 Android 13+ 必須的(用戶要主動同意)。

### 6.4 改 App 名稱(顯示在 home screen 上)

`mobile/android/app/src/main/res/values/strings.xml`:

```xml
<resources>
    <string name="app_name">叮咚到號</string>
    <string name="title_activity_main">叮咚到號</string>
    <string name="package_name">com.dindon.queue</string>
    <string name="custom_url_scheme">com.dindon.queue</string>
</resources>
```

---

## Phase 7:第一次跑模擬器

### 7.1 建虛擬裝置 (AVD)

1. Android Studio → 上方 **Device Manager** 圖示(手機 + 盒子)
2. 右上 **Create Device**
3. 選 **Phone** → **Pixel 7**(或任何 Pixel)
4. 點 **Next**
5. **System Image**:選 **API 34 (Android 14)**(沒下載過會顯示 Download,點下載)
6. **Next** → **Finish**

### 7.2 啟動模擬器

Device Manager 列表內,點剛建的 Pixel 7 旁邊的 ▶。

第一次啟動 1-3 分鐘。

### 7.3 跑 App

Android Studio 上方:

```
[app] [Pixel 7 API 34] ▶ Run
       ↑
       選你剛建的虛擬裝置
```

按 ▶ Run。第一次 build 5-10 分鐘。完成後:

- 模擬器內出現叮咚到號 icon
- 自動開啟,顯示對話介面
- 跟 Chrome 看到的一樣,但現在是「原生 App」

### 7.4 測試

- 點數字按鈕
- 試試選台大醫院 → 0 返回
- 看 Logcat(下方)有沒有 error

> ⚠ **模擬器空白 / crash**:看 Logcat 紅字。最常見問題:
> - `google-services.json` 沒放對位置
> - Gradle sync 沒跑完
> - 網路問題(模擬器內沒連到 dd.dl-app.com)

---

## Phase 8:實機測試(在你 Android 手機跑)

### 8.1 啟用「開發人員模式」

Android 手機上:

1. **設定 → 關於手機**
2. 找 **版本號碼**(每家廠牌位置不同,可能在「軟體資訊」)
3. 連點 **7 次** → 跳出「您現在是開發者!」
4. 回到 **設定 → 系統 → 開發人員選項**(或直接在主設定列表)
5. 開啟 **USB 偵錯**

### 8.2 把手機接到電腦

USB 線連 mac。手機上會跳「**允許 USB 偵錯?**」→ 勾「總是允許」→ **允許**。

確認連上:

```bash
adb devices
# 應該列出你的手機,例如:
# 1A2B3C4D    device
```

### 8.3 在 Android Studio 選你的手機

```
[app] [Samsung SM-S911U] ▶ Run
       ↑
       下拉應該看到實機(會顯示型號)
```

按 ▶ Run。第一次會在手機上裝 App,要等 30 秒-2 分鐘。

### 8.4 測試 Web Push(注意:只在 Phase 4 完成後才有真正的 native push)

現階段只能測 PWA Web Push(因為 Phase 4 推播路由還沒做):

```bash
# 假設你用 LIFF 註冊過
curl -X POST https://dd.dl-app.com/api/push/test \
  -H 'Content-Type: application/json' \
  -d '{"line_user_id":"YOUR_LINE_USER_ID","title":"叮咚","body":"測試"}'
```

> Phase 4 完成後才走 FCM,那時測試方式會不同。

---

## Phase 9:Keystore 簽章(這一步搞錯 = App 死)

**這是 Android 上架最重要的一個檔案。**

### 9.1 為什麼需要 Keystore?

Android 用 keystore 簽名你的 App。**Keystore 等於 App 的永久身分證。**

**如果 keystore 弄丟了:**
- ❌ 你不能再更新這個 App
- ❌ 用戶必須重灌新的 App(失去所有資料)
- ❌ 你的 App 在 Play Store 等於死了
- ❌ Google 不會幫你恢復

**所以 keystore 千萬要備份!備份!備份!**

### 9.2 產生 Keystore

```bash
# cd 到你想存的位置(不要進 git!)
cd ~/Documents/keys

# 產生 keystore
keytool -genkeypair -v \
  -keystore dindon-queue-release.jks \
  -alias dindon-queue \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000

# 會問你一堆問題:
# Enter keystore password: 設一個強密碼,記下來!
# Re-enter new password: 再輸入一次
# What is your first and last name? 你的名字
# What is the name of your organizational unit? 部門(自由填,例如 Engineering)
# What is the name of your organization? 組織(填公司名或自己名)
# What is the name of your City or Locality? Taipei
# What is the name of your State or Province? Taiwan
# What is the two-letter country code for this unit? TW
# Is CN=..., OU=..., O=..., L=Taipei, ST=Taiwan, C=TW correct? yes
# Enter key password for <dindon-queue>: 跟 keystore 密碼一樣即可(空白 enter)
```

完成後有個 `dindon-queue-release.jks` 檔案。

### 9.3 立刻備份這個檔案!!!!

**3 個地方備份:**
1. iCloud / Google Drive(雲端)
2. 外接硬碟
3. 1Password / Bitwarden 等密碼管理器(可以存檔案)

**然後把以下資訊也記到密碼管理器:**

```
keystore 路徑:    ~/Documents/keys/dindon-queue-release.jks
keystore 密碼:    <你剛設的>
key alias:       dindon-queue
key 密碼:        <你剛設的,通常跟 keystore 一樣>
```

**真的真的真的不要弄丟。**

### 9.4 設定 Android Studio 用這個 keystore

`mobile/android/app/build.gradle` 加:

```gradle
android {
    // ... 其他設定 ...

    signingConfigs {
        release {
            storeFile file(System.getenv("DINDON_KEYSTORE_PATH") ?: "../../../keys/dindon-queue-release.jks")
            storePassword System.getenv("DINDON_KEYSTORE_PASSWORD") ?: ""
            keyAlias "dindon-queue"
            keyPassword System.getenv("DINDON_KEY_PASSWORD") ?: ""
        }
    }

    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled false
        }
    }
}
```

**用 environment variable 代替直接寫密碼**(否則 commit 會洩露):

```bash
# 加到 ~/.zshrc(本機開發用)
export DINDON_KEYSTORE_PATH="$HOME/Documents/keys/dindon-queue-release.jks"
export DINDON_KEYSTORE_PASSWORD="你的密碼"
export DINDON_KEY_PASSWORD="你的密碼"
```

### 9.5 取得 Release SHA-1(填回 Firebase)

```bash
keytool -list -v \
  -keystore ~/Documents/keys/dindon-queue-release.jks \
  -alias dindon-queue
# 輸入 keystore 密碼
```

輸出會有:

```
Certificate fingerprints:
  MD5:  ...
  SHA1: AB:CD:EF:12:34:56:78:90:...   ← 把這串複製
  SHA256: ...
```

### 9.6 把 SHA-1 加到 Firebase

回到 Phase 4.3 跳過的 SHA-1:

1. 開 https://console.firebase.google.com → 你的專案
2. **設定齒輪 → 專案設定**
3. **你的應用程式 → Android App**
4. 點 **新增指紋**
5. 貼 SHA-1
6. 儲存

**也順便加 Debug SHA-1**(讓開發時也能用 Firebase):

```bash
keytool -list -v \
  -keystore ~/.android/debug.keystore \
  -alias androiddebugkey \
  -storepass android \
  -keypass android | grep SHA1
```

加進 Firebase 的「指紋」清單。

### 9.7 重新下載 google-services.json

**改 SHA-1 後 google-services.json 會更新**,要重新下載:

1. Firebase Console → 專案設定 → Android App
2. **下載 google-services.json**
3. 蓋掉舊的:
   ```bash
   cp ~/Downloads/google-services.json mobile/android/app/google-services.json
   ```

---

## Phase 10:Google Play Console 建立 App

### 10.1 開啟 Google Play Console

https://play.google.com/console → **建立應用程式**

### 10.2 填表單

| 欄位 | 填什麼 |
|------|-------|
| **應用程式名稱** | `叮咚到號` |
| **預設語言** | 繁體中文(台灣) |
| **應用程式或遊戲** | 應用程式 |
| **免費或付費** | 免費(之後改不了!) |

底下勾選:
- ✅ 我同意《開發人員計畫政策》
- ✅ 我接受 US export laws

點 **建立應用程式**。

### 10.3 設定「應用程式內容」(必填一堆東西)

進入應用程式後,左邊有一堆要填的:

1. **隱私政策** → 填你的 URL(`https://dd.dl-app.com/privacy`)
2. **應用程式存取權限** → 「所有功能無需特殊存取權即可使用」(或如果有 demo 帳號就提供)
3. **廣告** → 「沒有廣告」
4. **內容分級問卷** → 填問卷,大概都是「否」(沒有暴力、成人、賭博等)
5. **目標對象與內容** → 選 18+(避免兒童相關額外法規)
6. **新聞應用程式** → 否
7. **COVID-19 接觸追蹤與狀態** → 否
8. **資料安全** → 詳填(很重要,Google 會擋)

**資料安全表格詳填:**

| 收集的資料 | 用途 | 是否分享 |
|----------|------|---------|
| **使用者 ID**(LINE user id) | 帳號管理 / 推播 | 否 |
| **裝置或其他 ID**(push token) | 推播功能 | 否 |
| **App 互動記錄** | 分析 | 否 |

### 10.4 設定「商店資訊」

左邊 **主要商店資訊**:

| 欄位 | 內容 |
|------|------|
| **應用程式名稱** | 叮咚到號 |
| **簡短說明**(80 字內) | `即時掌握醫院看診進度,叫號通知不錯過` |
| **完整說明**(4000 字內) | (用 set_iOS.md Phase 10.6 那段) |
| **應用程式圖示** | 512×512 PNG |
| **特色圖片** | 1024×500 PNG(會顯示在 Play Store 頂部) |
| **手機螢幕截圖** | 至少 2 張,16:9 或 9:16 |

---

## Phase 11:準備上架素材

### 11.1 App icon(512 × 512)

跟 iOS 那 1024×1024 同一個設計,只是縮成 512。可以用同一個源檔。

要求:
- **512 × 512 PNG**
- **32-bit (含 alpha channel)**
- **沒有圓角**(Google 自動加 adaptive)

### 11.2 特色圖片(1024 × 500)

Play Store 頂部顯示用的 banner。

可以放:
- App 名稱「叮咚到號」
- Slogan「即時看診進度通知」
- 配 icon

### 11.3 手機截圖(至少 2 張,最多 8 張)

- **解析度**:任何尺寸都可,16:9 或 9:16 最佳
- **建議用模擬器**:Android Studio 模擬器 → Pixel 7 → Cmd + S 截圖
- **建議內容**:
  1. 主畫面對話介面
  2. 醫院列表
  3. 追蹤中畫面
  4. 設定/通知範例

### 11.4 隱私政策

跟 iOS 用同一個 `https://dd.dl-app.com/privacy`。

### 11.5 服務條款(可選但建議)

`https://dd.dl-app.com/terms`

---

## Phase 12:上傳 build (.aab)

### 12.1 在 Android Studio 產生 Signed Bundle

1. 上方選單 **Build → Generate Signed Bundle / APK**
2. 選 **Android App Bundle**(**不是 APK!** Play Store 強制要 .aab)
3. 點 **Next**
4. **Key store path**: 選 `~/Documents/keys/dindon-queue-release.jks`
5. **Key store password**: 你 Phase 9 設的
6. **Key alias**: `dindon-queue`
7. **Key password**: 你 Phase 9 設的
8. 點 **Next**
9. **Destination Folder**: 預設(`mobile/android/app/release`)
10. **Build Variants**: `release`
11. 點 **Finish**

跑 5-10 分鐘。完成後右下角通知:

```
app-release.aab generated successfully
```

檔案在 `mobile/android/app/release/app-release.aab`。

### 12.2 上傳到 Play Console

回到 Play Console:

1. 左邊 **發布 → 應用程式版本**
2. 選 **測試 → 內部測試**(先做這個,**不要直接上 Production!**)
3. 點 **建立新版本**
4. **App Signing by Google Play**: 建議選 **使用 Google Play 簽署金鑰**(讓 Google 幫你管 keystore,你的 keystore 變成「上傳金鑰」)
5. **AAB 上傳**:把 `app-release.aab` 拖進去
6. **版本名稱**: `1.0.0`
7. **版本資訊**: `首次發布`
8. 點 **儲存** → **檢查版本**

### 12.3 選擇測試人員(內部測試)

1. 左邊 **內部測試 → 測試人員** 分頁
2. **建立電子郵件清單**
3. 加你自己的 Gmail + 朋友的 Gmail(2-5 人)
4. 儲存

### 12.4 開始發布

點 **開始發布到內部測試**。

通常 **5-30 分鐘** 就會處理好(比 iOS 快很多)。

### 12.5 內部測試人員下載 App

收到 email 後:
1. 點 email 內的連結 → 接受測試邀請
2. 點 **在 Google Play 上下載**
3. 在 Play Store 內安裝(會顯示 [Internal test] 標記)

> 內部測試版只給你選的 Gmail 用戶下載,陌生人看不到。這是「上正式版前的最後保險」。

---

## Phase 13:Internal Testing(內部測試)

### 13.1 自己測試所有功能

至少 1-2 天,完整測試:
- 對話介面所有流程
- 推播通知有沒有收到(Phase 4 完成後)
- App 不會 crash
- 記憶體用量正常

### 13.2 修任何發現的 bug

每次修完:
1. 改 `mobile/android/app/build.gradle` 內的 `versionCode +1`
2. 重新 Build → Generate Signed Bundle
3. 上傳新的 .aab 到內部測試
4. 等審查(通常 < 1 小時)

> ⚠ **每次上傳 versionCode 必須比上次大!** 否則會被拒。

### 13.3 通過內部測試後 → 升級到 Production

確認沒問題後,在 Play Console:

1. 左邊 **發布 → 應用程式版本**
2. 選 **正式版**
3. 點 **建立新版本**
4. 從內部測試版本「升級」過來(會自動帶入)
5. 填寫**新版本說明**
6. 儲存 → 檢查 → 開始發布

---

## Phase 14:提交審核(Production)

### 14.1 確認所有「待辦事項」都已完成

Play Console 左邊側欄,所有東西都要綠勾:

- ✅ 商店資訊
- ✅ 主要商店資訊
- ✅ 應用程式內容(全部小項目)
- ✅ 應用程式版本(已建立 production 版本)
- ✅ 國家/地區
- ✅ 應用程式類別
- ✅ 聯絡詳細資料
- ✅ 商店設定
- ✅ 隱私政策

如果有黃色驚嘆號 → 點進去看缺什麼,補完。

### 14.2 點「開始發布到正式版」

在「應用程式版本」頁面,點正式版的 **開始發布**。

跳出確認 → **確認**。

### 14.3 等審查

通常 **數小時 ~ 7 天**。第一次發布的 App 比較久(Google 會額外多看幾眼)。

---

## Phase 15:等待 + 處理退件

### 15.1 你會收到 email

通過或被退,Google 都會發 email。

### 15.2 常見退件原因

| 退件原因 | 對策 |
|---------|------|
| **資料安全宣告與實際行為不符** | 重填資料安全表格,如實寫所有收集的資料 |
| **應用程式損壞 / 無法啟動** | crash → 看 Play Console 內 crash log,修了再上 |
| **隱私政策不夠清楚** | 重寫隱私政策,**列出所有收集的資料** |
| **缺少核心功能** | 截圖跟描述不符 → 改截圖或改描述 |
| **POST_NOTIFICATIONS permission 沒解釋** | App 描述提到「會推送通知」 |
| **欺騙性行為** | 通常是 icon 跟內容不符 → 改 icon |
| **目標 SDK 太舊** | targetSdkVersion 必須夠新(2025 年要 ≥ 34) |

### 15.3 被退之後怎麼辦

1. 進 Play Console → **政策狀態** 看詳細退件理由
2. 修問題 → versionCode +1 → 重 build → 上傳新 .aab → 重新發布
3. 第二次通常很快

---

## Phase 16:上架成功 🎉

### 16.1 你的 App 出現在 Play Store

任何人在 Play Store 搜尋「叮咚到號」都能下載。
URL: `https://play.google.com/store/apps/details?id=com.dindon.queue`

### 16.2 一定要做的事

**馬上**:
1. 自己用「另一支 Android」搜尋 + 下載確認
2. 分享給朋友 5-10 人試用

**第一週**:
3. 在 Play Console 看下載數 + crash rate(目標 < 1%)
4. **回覆用戶評論**(很重要,Google 會看你的回覆率)
5. 修任何 critical bug

**長期**:
6. **每年至少更新一次**(否則 Google 會把你的 App 標為「過時」)
7. **追蹤 targetSdkVersion 政策**:每年 11 月 Google 會要求最低 targetSdkVersion +1
8. Google 不像 Apple 收年費,但有 Android 政策變更(例如 2024 要求新 App 必須支援 Android 14)

---

## 🆘 常見問題 / 坑

### Q1: 「Application ID 已被使用」
A: 換一個。`com.dindon.queue` 被佔了就用 `tw.dindon.queue` 或 `com.dindongtw.queue`。

### Q2: 「Gradle sync 失敗」
A: 99% 是網路或 JDK 問題:
- 確認 Android Studio Settings → Build → Gradle → JDK = 17
- 換網路或設 proxy
- 刪掉 `mobile/android/.gradle/` 重新 sync

### Q3: 「Build 成功但 install 到實機失敗」
A: 通常是 versionCode 沒比舊版高,或 keystore 不對。確認你 build 用的是 release config。

### Q4: 「我的 keystore 不見了」
A: **完蛋。** 你的 App 等於死了,只能新建一個 application id 上架(失去所有用戶 + 評論 + 排名)。
**這就是為什麼 Phase 9 要備份 3 個地方。**

### Q5: 「上傳 .aab 說 versionCode 已存在」
A: 在 build.gradle 把 versionCode +1。每次上傳必須大於 Play Store 上的最高版本。

### Q6: 「Internal Test 朋友收不到測試 email」
A: 朋友 Gmail 拼錯,或 Play Store 帳號跟 Gmail 不一致。讓朋友先打開 Play Store 確認登入的是哪個帳號。

### Q7: 「Production review 被退,但說『需要收集更多資料』」
A: 通常是「資料安全」表格漏勾。把 LINE user ID、push token、分析資料都如實勾選。

### Q8: 「FCM 推播收不到」
A: 順序檢查:
1. 手機設定 → 通知 → 叮咚到號 → 允許通知 是不是開
2. App 內 `Notification.permission` 是不是 `granted`
3. google-services.json 是不是最新版(改 SHA-1 後要重新下載)
4. Firebase Console → Cloud Messaging 試發測試訊息
5. 後端 service account JSON 對不對

### Q9: 「App 在 Android 13+ 推播沒跳 prompt」
A: Android 13+ 必須**主動 request POST_NOTIFICATIONS permission**:

```js
import { PushNotifications } from '@capacitor/push-notifications';
const result = await PushNotifications.requestPermissions();
if (result.receive === 'granted') {
    await PushNotifications.register();
}
```

### Q10: 「我可以同時開發 iOS 和 Android 嗎?」
A: 可以。Capacitor 設計就是兩平台同一份 code。
- `npx cap sync` → 同步到所有平台
- `npx cap open ios` / `npx cap open android` → 各自打開
- 同一個 git repo

---

## 📚 延伸閱讀

| 主題 | 連結 |
|------|------|
| Capacitor Android 文件 | https://capacitorjs.com/docs/android |
| Android Developers 官方 | https://developer.android.com/docs |
| Play Console 說明 | https://support.google.com/googleplay/android-developer |
| Firebase Cloud Messaging | https://firebase.google.com/docs/cloud-messaging |
| Material Design Guidelines | https://m3.material.io/ |

---

## 一頁速查 Cheat Sheet

```
工具
├── 任何電腦 (mac / Win / Linux)
├── Android Studio
├── JDK 17
├── Node 18+
└── 你的 Android 手機 (Android 8+)

帳號
├── Google Account
└── Google Play Developer ($25 一次性)

關鍵 ID(全記下來)
├── Application ID:    com.dindon.queue
├── Firebase Project:  dindon-queue
└── versionCode:       每次上傳 +1

關鍵檔案(備份 3 個地方!!)
├── google-services.json              Firebase 設定
├── firebase-admin-sdk.json           後端推播 service account
├── dindon-queue-release.jks ⚠⚠⚠      Keystore!弄丟 = App 死!
└── 三個密碼:keystore / key alias / key password

關鍵指令
├── npx cap sync android              同步 PWA 到 Android 專案
├── npx cap open android              用 Android Studio 開啟
├── adb devices                       看實機是否連上
└── Build → Generate Signed Bundle    產 .aab

關鍵 URL
├── https://play.google.com/console
├── https://console.firebase.google.com
└── https://dd.dl-app.com/privacy

每年的事
├── targetSdkVersion 升一級(每年 8-11 月)
└── 確認 App 不是「過時」
```

---

## 🆚 跟 iOS 的差別速查

| 項目 | iOS | Android |
|------|-----|---------|
| 開發者費用 | $99 / 年 | $25 一次性 |
| 必須的電腦 | mac only | mac / Win / Linux |
| IDE | Xcode | Android Studio |
| 包格式 | .ipa | .aab |
| 唯一 ID | Bundle ID | Application ID |
| 推播服務 | APNs | FCM (Firebase) |
| 推播金鑰 | .p8 file | google-services.json + service account JSON |
| 簽章 | Provisioning Profile + Cert | Keystore (.jks) |
| 審核時間 | 24-48 小時 | 數小時 - 7 天 |
| 退件機率 | 高(~80% 第一次) | 中(~40% 第一次) |
| 後台 | App Store Connect | Google Play Console |
| 內部測試 | TestFlight | Internal Testing |
| 開發者計畫年費 | 每年要續 | 一次性,沒續費問題 |
| 上傳工具 | Xcode Organizer | Play Console 直接上傳 |

---

**STATUS:** 看完這份就能從零做到 Android App 上架。卡住任何 Phase 來問我。

建議跟 [`set_iOS.md`](./set_iOS.md) 平行做,因為 Capacitor 兩邊共用一份 code,大部分工作不用做兩次。
