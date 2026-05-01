@echo off
chcp 65001 > nul
echo.
echo ========================================
echo   智慧居家復健評估系統
echo   Smart Rehabilitation System
echo ========================================
echo.
echo 正在啟動應用...（使用 Python 3.11）
echo.

cd /d "%~dp0"
call .\.venv311\Scripts\activate.bat
python -m streamlit run app.py --server.port 8501

pause
