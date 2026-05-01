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
    )
    if defined PYTHON_EXE set "PYTHON_ARGS=-3.11"
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
echo   SmartRehab
echo ========================================
echo.
echo Starting Streamlit on http://localhost:%PORT%
echo Using: %PYTHON_EXE% %PYTHON_ARGS%
echo.

call "%PYTHON_EXE%" %PYTHON_ARGS% -m streamlit run app.py ^
    --server.port %PORT% ^
    --server.runOnSave false ^
    --browser.gatherUsageStats false

pause
