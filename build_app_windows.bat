@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

where node > nul 2> nul
if errorlevel 1 (
    echo Node.js 18 or newer is required to build the Windows app.
    echo Download it from https://nodejs.org/
    echo.
    pause
    exit /b 1
)

where npm > nul 2> nul
if errorlevel 1 (
    echo npm was not found. Reinstall Node.js and include npm.
    echo.
    pause
    exit /b 1
)

if not exist ".venv311\Scripts\python.exe" (
    echo Warning: .venv311 was not found.
    echo The packaged app will require Python 3.11 on the target machine.
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

echo Building SmartRehab for Windows...
call npm run build-win
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Done. Check electron\dist for the installer and portable app.
pause
