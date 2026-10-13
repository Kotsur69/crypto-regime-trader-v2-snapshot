@echo off
chcp 65001 >nul 2>&1
echo.
echo ============================================================
echo LEARNING PROGRESS
echo ============================================================
echo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe check_learning_progress.py
) else (
    python check_learning_progress.py
)
echo.
pause
