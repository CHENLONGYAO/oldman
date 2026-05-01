@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_android_app.ps1"
if errorlevel 1 (
    echo.
    echo Android build failed.
    pause
    exit /b 1
)

echo.
pause
