@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"
set "PORT=8501"
set "ADB_EXE="
set "PYTHON_EXE="
set "PYTHON_ARGS="

for /f "delims=" %%A in ('where adb 2^> nul') do (
    if not defined ADB_EXE set "ADB_EXE=%%A"
)

if not defined ADB_EXE if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
    set "ADB_EXE=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
)

if not defined ADB_EXE if exist "%ANDROID_HOME%\platform-tools\adb.exe" (
    set "ADB_EXE=%ANDROID_HOME%\platform-tools\adb.exe"
)

if not defined ADB_EXE (
    echo adb was not found.
    echo Install Android Studio or Android Platform Tools, then enable USB debugging on the phone.
    pause
    exit /b 1
)

if exist ".venv311\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv311\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
) else (
    for /f "delims=" %%P in ('where py 2^> nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
        set "PYTHON_ARGS=-3.11"
    )
)

if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python 2^> nul') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
    )
)

if not defined PYTHON_EXE (
    echo Python was not found. Install Python 3.11 or create .venv311 first.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   SmartRehab Android USB Server
echo ========================================
echo.
echo Connected Android devices:
call "%ADB_EXE%" devices
echo.
echo Creating adb reverse tunnel...
call "%ADB_EXE%" reverse tcp:%PORT% tcp:%PORT%
if errorlevel 1 (
    echo adb reverse failed. Check USB debugging authorization on the phone.
    pause
    exit /b 1
)

echo.
echo In the Android app, enter:
echo   http://127.0.0.1:%PORT%
echo.
echo Keep this window open while using the Android app.
echo.

call "%PYTHON_EXE%" %PYTHON_ARGS% -m streamlit run app.py ^
    --server.address 127.0.0.1 ^
    --server.port %PORT% ^
    --server.headless true ^
    --server.runOnSave false ^
    --server.enableCORS false ^
    --server.enableXsrfProtection false ^
    --browser.gatherUsageStats false ^
    --client.toolbarMode minimal

pause
