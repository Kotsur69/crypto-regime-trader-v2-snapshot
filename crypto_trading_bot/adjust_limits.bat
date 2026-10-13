@echo off
chcp 65001 >nul 2>&1
echo.
echo ============================================================
echo ADJUST LIMITS
echo ============================================================
echo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe adjust_limits.py
) else (
    python adjust_limits.py
)
echo.
pause
