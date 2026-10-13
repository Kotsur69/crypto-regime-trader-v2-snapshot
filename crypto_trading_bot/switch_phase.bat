@echo off
chcp 65001 >nul 2>&1
echo.
echo ============================================================
echo SWITCH LEARNING PHASE
echo ============================================================
echo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe switch_phase.py
) else (
    python switch_phase.py
)
echo.
pause
