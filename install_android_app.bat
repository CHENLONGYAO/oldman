@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_android_app.ps1"
if errorlevel 1 (
    echo.
    echo Install failed.
    pause
    exit /b 1
)

echo.
pause
