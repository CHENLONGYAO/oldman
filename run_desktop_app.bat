@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

where node > nul 2> nul
if errorlevel 1 (
    echo Node.js is required to run the desktop app shell.
    echo Install Node.js 18 or newer, then run this file again.
    echo.
    pause
    exit /b 1
)

where npm > nul 2> nul
if errorlevel 1 (
    echo npm is required to run the desktop app shell.
    echo Install Node.js 18 or newer, then run this file again.
    echo.
    pause
    exit /b 1
)

if not exist ".venv311\Scripts\python.exe" (
    echo Python virtual environment .venv311 was not found.
    echo The app will try system Python instead.
    echo.
)

cd electron
if not exist "node_modules" (
    echo Installing desktop app dependencies...
    call npm install
    if errorlevel 1 (
        echo npm install failed.
        pause
        exit /b 1
    )
)

call npm start
