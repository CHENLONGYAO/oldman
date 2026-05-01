# SmartRehab 智慧居家復健評估系統

SmartRehab 是以 Streamlit 執行的居家復健評估工具，包含姿態分析、復健計畫、健康日記、疼痛地圖、生命跡象、藥物與預約追蹤。Android 版本是手機 WebView App，連到電腦或伺服器正在執行的 Streamlit 後端。

## 電腦端啟動

```bat
start_android_server.bat
```

手機與電腦連同一個 Wi-Fi 後，在 Android App 內輸入腳本顯示的網址，例如：

```text
http://192.168.1.23:8501
```

## 建置 Android APK

安裝 Android Studio 後，直接執行：

```bat
build_android_app.bat
```

APK 會輸出到：

```text
android\app\build\outputs\apk\debug\app-debug.apk
```

建置腳本會自動尋找：

- Android Studio 內建 JBR/JDK
- Android SDK
- Android Studio 已下載的 Gradle

注意：Red Hat OpenJDK 8 太舊，不能建這個 Android 專案。腳本會自動避開它，優先使用 Android Studio 的 JBR。

## 安裝到手機

手機開啟 USB debugging 並連上電腦後，執行：

```bat
install_android_app.bat
```

腳本會安裝 debug APK 並啟動 SmartRehab。

## 常用檔案

- `app.py`：Streamlit 入口
- `views.py`：主要 UI 頁面
- `history.py`：使用者資料、訓練紀錄、XP、徽章
- `android/`：Android WebView App
- `start_android_server.bat`：Wi-Fi 手機連線用 Streamlit 伺服器
- `start_android_usb_server.bat`：USB reverse 測試用伺服器
- `build_android_app.bat`：建置 APK
- `install_android_app.bat`：安裝 APK 到 USB 手機
"# oldman"  
