@echo off
chcp 65001 >nul 2>&1
echo.
echo ============================================================
echo CHECKING BOT STATUS...
echo ============================================================
echo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe check_status.py
) else (
    python check_status.py
)
echo.
echo ============================================================
echo Press any key to close...
pause >nul
