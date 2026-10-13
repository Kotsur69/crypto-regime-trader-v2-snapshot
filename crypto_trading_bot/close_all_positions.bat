@echo off
chcp 65001 >nul 2>&1
echo.
echo ============================================================
echo CLOSE ALL POSITIONS
echo ============================================================
echo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe close_all_positions.py
) else (
    python close_all_positions.py
)
echo.
pause
