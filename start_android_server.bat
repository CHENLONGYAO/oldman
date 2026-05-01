@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"
set "PORT=8501"
set "PYTHON_EXE="
set "PYTHON_ARGS="

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
echo   SmartRehab Android Server
echo ========================================
echo.
echo On your Android phone, enter one of these URLs in the app:
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | ForEach-Object { '  http://' + $_.IPAddress + ':%PORT%' }"
echo.
echo Keep this window open while using the Android app.
echo If Windows Firewall asks, allow access on Private networks.
echo.

call "%PYTHON_EXE%" %PYTHON_ARGS% -m streamlit run app.py ^
    --server.address 0.0.0.0 ^
    --server.port %PORT% ^
    --server.headless true ^
    --server.runOnSave false ^
    --server.enableCORS false ^
    --server.enableXsrfProtection false ^
    --browser.gatherUsageStats false ^
    --client.toolbarMode minimal

pause
