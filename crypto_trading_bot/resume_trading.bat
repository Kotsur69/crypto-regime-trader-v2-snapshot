@echo off
chcp 65001 >nul 2>&1
echo.
echo ============================================================
echo RESUME TRADING
echo ============================================================
echo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe resume_trading.py
) else (
    python resume_trading.py
)
echo.
pause
