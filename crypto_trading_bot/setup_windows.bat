@echo off
REM ============================================
REM CRYPTO TRADING BOT - Windows Setup Script
REM ============================================
REM Ten skrypt automatycznie konfiguruje srodowisko
REM dla bota tradingowego na Windows.
REM ============================================

echo.
echo ========================================
echo   CRYPTO TRADING BOT - Windows Setup
echo ========================================
echo.

REM Sprawdz czy Python jest zainstalowany
echo [1/5] Sprawdzanie Pythona...
python --version >nul 2>&1
if errorlevel 1 (
    echo BLAD: Python nie jest zainstalowany lub nie jest w PATH!
    echo Pobierz Python z: https://www.python.org/downloads/
    echo WAZNE: Zaznacz "Add Python to PATH" podczas instalacji!
    pause
    exit /b 1
)
python --version
echo.

REM Sprawdz czy venv juz istnieje
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment juz istnieje.
    set /p RECREATE="Czy chcesz go odtworzyc? (t/n): "
    if /i "%RECREATE%"=="t" (
        echo Usuwanie starego venv...
        rmdir /s /q venv
    ) else (
        goto INSTALL_DEPS
    )
)

REM Stworz virtual environment
echo [2/5] Tworzenie virtual environment...
python -m venv venv
if errorlevel 1 (
    echo BLAD: Nie udalo sie stworzyc virtual environment!
    pause
    exit /b 1
)
echo Virtual environment utworzone!
echo.

:INSTALL_DEPS
REM Aktywuj venv
echo [3/5] Aktywowanie virtual environment...
call venv\Scripts\activate.bat
echo.

REM Upgrade pip
echo [4/5] Aktualizacja pip...
python -m pip install --upgrade pip
echo.

REM Instaluj zaleznosci
echo [5/5] Instalowanie zaleznosci...
echo To moze zajac kilka minut...
pip install -r requirements.txt
if errorlevel 1 (
    echo OSTRZEZENIE: Niektore pakiety mogly sie nie zainstalowac.
    echo Sprawdz logi powyzej.
)
echo.

echo ========================================
echo   SETUP ZAKONCZONY POMYSLNIE!
echo ========================================
echo.
echo Nastepne kroki:
echo 1. Aktywuj venv:   activate.bat
echo 2. Skonfiguruj:    python setup_testnet.py
echo 3. Uruchom bota:   python main.py --config config_testnet.yaml
echo.
echo Lub uzyj: run_bot.bat
echo.

pause
