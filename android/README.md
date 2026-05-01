# SmartRehab Android App

這個 Android 專案是 SmartRehab 的手機殼層 App。它會在手機上開啟一個全螢幕 WebView，連到電腦或伺服器正在執行的 Streamlit 服務。

## 使用方式

1. 在電腦上執行專案根目錄的 `start_android_server.bat`。
2. 確認手機與電腦在同一個 Wi-Fi。
3. 打開 Android App，輸入腳本顯示的網址，例如 `http://192.168.1.23:8501`。
4. 若 Windows 防火牆詢問，允許 Python 或 Streamlit 存取私人網路。

## 即時鏡頭測試

Streamlit 的影片上傳模式可直接透過 Wi-Fi 使用。若要測試 `streamlit-webrtc` 即時鏡頭，Android WebView 可能會要求安全來源；可以改用 USB 偵錯：

1. 手機開啟 USB debugging 並連上電腦。
2. 電腦安裝 Android Studio 或 Android Platform Tools。
3. 執行 `start_android_usb_server.bat`。
4. App 內輸入 `http://127.0.0.1:8501`。

## 建置 APK

最簡單的方式是在專案根目錄執行：

```bat
build_android_app.bat
```

APK 會輸出到：

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

這個腳本會自動使用 Android Studio 內建 JBR/JDK、Android SDK 與 Gradle cache。若電腦同時裝了 OpenJDK 8，腳本會避開它，因為 Android Gradle Plugin 需要 JDK 17 以上。

也可以用 Android Studio：

1. 安裝 Android Studio。
2. 用 Android Studio 開啟本資料夾 `android`。
3. 等待 Gradle Sync 完成。
4. 選擇 `Build > Build Bundle(s) / APK(s) > Build APK(s)`。
5. APK 會輸出到 `android/app/build/outputs/apk/debug/app-debug.apk`。

## 安裝 APK

手機開啟 USB debugging 並連上電腦後，在專案根目錄執行：

```bat
install_android_app.bat
```

若只想手動安裝，可以把 `android/app/build/outputs/apk/debug/app-debug.apk` 傳到手機再點開安裝。

## 架構說明

目前的 Python 套件包含 Streamlit、MediaPipe、OpenCV、PyTorch 與本機 TTS，這些依賴不適合直接完整塞進 Android APK。這個版本保留現有 Python 分析核心在電腦或伺服器上執行，Android App 負責手機端操作、相機權限、檔案選擇與 WebView 顯示。

如果要做成完全離線、不需要電腦的 Android App，需要另外把分析流程改寫成 Android/Kotlin 或把模型轉成 TFLite/MediaPipe Android 管線。
