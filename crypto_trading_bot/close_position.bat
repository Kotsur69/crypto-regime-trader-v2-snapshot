@echo off
chcp 65001 >nul 2>&1
echo.
echo ============================================================
echo CLOSE POSITION
echo ============================================================
echo.
set /p pair="Enter pair (e.g., SOLUSDT): "
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe close_position.py %pair%
) else (
    python close_position.py %pair%
)
echo.
pause
