@echo off
REM ============================================
REM CRYPTO TRADING BOT - Quick Start
REM ============================================
REM Ten skrypt aktywuje venv i uruchamia bota
REM z domyslna konfiguracja testnet.
REM ============================================

echo.
echo ========================================
echo   CRYPTO TRADING BOT - Quick Start
echo ========================================
echo.

REM Sprawdz czy venv istnieje
if not exist "venv\Scripts\activate.bat" (
    echo BLAD: Virtual environment nie istnieje!
    echo Uruchom najpierw: setup_windows.bat
    pause
    exit /b 1
)

REM Sprawdz czy config istnieje
if not exist "config_testnet.yaml" (
    echo BLAD: Brak pliku config_testnet.yaml!
    echo Uruchom najpierw: python setup_testnet.py
    pause
    exit /b 1
)

REM Aktywuj venv
echo Aktywowanie virtual environment...
call venv\Scripts\activate.bat

REM Uruchom bota
echo.
echo Uruchamianie bota...
echo (Ctrl+C aby zatrzymac)
echo.
python main.py --config config_testnet.yaml

REM Pauza na koncu zeby zobaczyc output
echo.
echo Bot zatrzymany.
pause
