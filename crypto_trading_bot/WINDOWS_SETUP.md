# Przewodnik instalacji na Windows

Ten przewodnik przeprowadzi Cię przez proces instalacji i uruchomienia bota na systemie Windows.

---

## Wymagania

### Python 3.10+
Sprawdź wersję Python:
```powershell
python --version
```

Jeśli Python nie jest zainstalowany:
1. Pobierz z https://www.python.org/downloads/
2. **WAŻNE**: Podczas instalacji zaznacz opcję "Add Python to PATH"

### pip (Package Manager)
Sprawdź czy pip jest zainstalowany:
```powershell
pip --version
```

### Git (opcjonalnie)
```powershell
git --version
```

---

## Instalacja krok po kroku

### Krok 1: Otwórz PowerShell jako Administrator

1. Naciśnij `Win + X`
2. Wybierz "Windows PowerShell (Administrator)" lub "Terminal (Administrator)"

### Krok 2: Ustaw Execution Policy (jeśli potrzeba)

Jeśli widzisz błąd dotyczący execution policy:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Potwierdź wpisując `Y` i `Enter`.

### Krok 3: Przejdź do folderu projektu

```powershell
cd C:\Users\TwojaNazwa\Downloads\crypto_trading_bot
```

### Krok 4: Stwórz virtual environment

```powershell
python -m venv venv
```

### Krok 5: Aktywuj venv

**PowerShell:**
```powershell
.\venv\Scripts\Activate.ps1
```

**CMD (Command Prompt):**
```cmd
venv\Scripts\activate.bat
```

Po aktywacji zobaczysz `(venv)` na początku wiersza poleceń.

### Krok 6: Zainstaluj zależności

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

### Krok 7: Skonfiguruj bota (testnet)

```powershell
python setup_testnet.py
```

### Krok 8: Uruchom bota

```powershell
python main.py --config config_testnet.yaml
```

---

## Visual Studio Code Setup

### Otwórz projekt w VS Code

1. Otwórz VS Code
2. `File` → `Open Folder` → wybierz folder `crypto_trading_bot`
3. Lub z terminala: `code .`

### Wybierz Python Interpreter (venv)

1. Naciśnij `Ctrl + Shift + P`
2. Wpisz "Python: Select Interpreter"
3. Wybierz interpreter z venv: `./venv/Scripts/python.exe`

### Uruchom terminal w VS Code

1. `View` → `Terminal` lub `Ctrl + `` `
2. Terminal automatycznie aktywuje venv (jeśli skonfigurowałeś interpreter)

### Uruchom bota z VS Code

1. Otwórz terminal w VS Code
2. Upewnij się, że venv jest aktywne (widzisz `(venv)`)
3. Uruchom:
   ```powershell
   python main.py --config config_testnet.yaml
   ```

---

## Encoding i logi (rozwiązane)

### Problem z emoji w logach

**Wcześniejszy błąd na Windows:**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u274c'
```

**Przyczyna:**
Windows Console używa encoding cp1250 (Europa Środkowa), który nie obsługuje emoji.

**Rozwiązanie (zastosowane):**
WSZYSTKIE emoji zostały zamienione na ASCII equivalents:
- `[OK]` zamiast emoji sukcesu
- `[ERROR]` zamiast emoji błędu  
- `[WARNING]` zamiast emoji ostrzeżenia
- `[INFO]` zamiast emoji informacji
- `[LEVEL]` zamiast 📐
- `[SHIELD]` zamiast 🛡️
- `[PIN]` zamiast 📍
- `[NEWS]` zamiast 📰
- `[WHALE]` zamiast 🐋
- I wiele innych...

### Sprawdzanie emoji w kodzie

Użyj narzędzia `check_emoji.py` do weryfikacji:
```powershell
python check_emoji.py
```

Wynik powinien być:
```
[OK] No emoji found! Code is Windows-compatible.
```

### Test automatyczny

Testy sprawdzają czy nie ma emoji:
```powershell
python -m pytest tests/test_no_emoji.py -v
```

### Jeśli chcesz przywrócić emoji

Dodaj na początku `main.py`:
```python
import sys
import io

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
```

I uruchom terminal z UTF-8:
```powershell
chcp 65001
python main.py --config config_testnet.yaml
```

---

## Troubleshooting

### Execution Policy Error

**Błąd:**
```
File .\venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled
```

**Rozwiązanie:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Python not found

**Błąd:**
```
'python' is not recognized as an internal or external command
```

**Rozwiązanie:**
1. Reinstaluj Python z zaznaczoną opcją "Add Python to PATH"
2. Lub dodaj Python ręcznie do PATH:
   - Wyszukaj "Environment Variables" w Windows
   - Edytuj `Path` i dodaj ścieżkę do Python (np. `C:\Users\TwojaNazwa\AppData\Local\Programs\Python\Python311`)

### pip not found

**Błąd:**
```
'pip' is not recognized...
```

**Rozwiązanie:**
```powershell
python -m pip install --upgrade pip
# Używaj pip jako:
python -m pip install -r requirements.txt
```

### Module not found errors

**Błąd:**
```
ModuleNotFoundError: No module named 'pandas'
```

**Rozwiązanie:**
1. Upewnij się, że venv jest aktywne (widzisz `(venv)` w terminalu)
2. Reinstaluj zależności:
   ```powershell
   pip install -r requirements.txt
   ```

### Permission denied errors

**Rozwiązanie:**
1. Uruchom PowerShell jako Administrator
2. Lub zmień lokalizację projektu na folder bez restrykcji (np. `C:\Projects\`)

### source: The term 'source' is not recognized

**Błąd:**
```
source : The term 'source' is not recognized...
```

**Wyjaśnienie:** `source` to komenda Linux/Mac. W Windows użyj:

**PowerShell:**
```powershell
.\venv\Scripts\Activate.ps1
```

**CMD:**
```cmd
venv\Scripts\activate.bat
```

---

## Szybki start - pliki .bat

Projekt zawiera pliki .bat dla wygody:

| Plik | Opis |
|------|------|
| `setup_windows.bat` | Automatyczny setup (tworzy venv, instaluje zależności) |
| `activate.bat` | Aktywuje venv i otwiera terminal |
| `run_bot.bat` | Aktywuje venv i uruchamia bota |

### Użycie:

Kliknij dwukrotnie na plik .bat lub uruchom z terminala:

```cmd
setup_windows.bat
```

---

## FAQ

**P: Czy mogę używać CMD zamiast PowerShell?**
O: Tak, pliki .bat działają w obu. Aktywacja venv w CMD: `venv\Scripts\activate.bat`

**P: Dlaczego widzę ostrzeżenia przy instalacji pip?**
O: To normalne. Dopóki instalacja się zakończy, wszystko jest OK.

**P: Jak sprawdzić czy venv jest aktywne?**
O: Szukaj `(venv)` na początku wiersza w terminalu.

**P: Jak dezaktywować venv?**
O: Wpisz `deactivate`

---

## Przydatne komendy

```powershell
# Sprawdź status bota
python main.py --status

# Uruchom backtest
python main.py --backtest

# Uruchom dashboard (web UI)
python main.py --dashboard

# Sprawdź pomoc
python main.py --help
```
