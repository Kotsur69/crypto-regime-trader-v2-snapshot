@echo off
REM ============================================
REM CRYPTO TRADING BOT - Aktywacja venv
REM ============================================
REM Ten skrypt aktywuje virtual environment
REM i otwiera terminal gotowy do pracy.
REM ============================================

echo.
echo ========================================
echo   CRYPTO TRADING BOT - Aktywacja venv
echo ========================================
echo.

REM Sprawdz czy venv istnieje
if not exist "venv\Scripts\activate.bat" (
    echo BLAD: Virtual environment nie istnieje!
    echo Uruchom najpierw: setup_windows.bat
    pause
    exit /b 1
)

REM Aktywuj venv
call venv\Scripts\activate.bat

echo Virtual environment aktywowane!
echo.
echo Dostepne komendy:
echo   python main.py --config config_testnet.yaml   (uruchom bota)
echo   python main.py --status                       (sprawdz status)
echo   python main.py --backtest                     (backtest)
echo   python main.py --dashboard                    (web dashboard)
echo   python setup_testnet.py                       (konfiguracja)
echo   deactivate                                    (dezaktywuj venv)
echo.

REM Otworz nowy terminal z aktywnym venv
cmd /k
