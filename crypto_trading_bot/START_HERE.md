# 🚀 START HERE - Jak uruchomić bota

## ⚠️ WAŻNE: NIE UŻYWAJ Visual Studio!

**Visual Studio (VS Code) służy tylko do EDYCJI kodu.**

**Do uruchamiania bota używaj plików .bat (kliknij dwukrotnie).**

---

## 📋 SZYBKI START (3 kroki)

### KROK 1: Sprawdź status

Kliknij dwukrotnie:
```
check_status.bat
```

Zobaczysz:
- ✅ Jaki tryb jest aktywny (learning/optimization/production)
- ✅ Czy bot jest uruchomiony
- ✅ Otwarte pozycje
- ✅ Emergency stop status
- ✅ Statystyki

### KROK 2: Uruchom bota

Kliknij dwukrotnie:
```
run_bot.bat
```

Zobaczysz okno z logami bota w czasie rzeczywistym.

**Żeby zatrzymać:**
- Naciśnij `Ctrl + C`
- Lub zamknij okno

### KROK 3: Monitoruj (opcjonalnie)

Podczas gdy bot działa, możesz:
- Sprawdzić status: `check_status.bat` (w nowym oknie)
- Sprawdzić postęp: `check_learning_progress.bat`
- Otworzyć dashboard: http://localhost:5000

---

## 🎯 AKTUALNY TRYB

Jeśli klikniesz `check_status.bat`, zobaczysz na górze:

```
1. AKTUALNY TRYB
----------------------------------------------------------------------
  [LEARN] Tryb: LEARNING
  [INFO] Faza uczenia się - bardzo luźne limity
  [INFO] Cel: Zbieranie danych (50-100 tradów)
```

**To oznacza że bot jest w trybie LEARNING** - to jest OK!

---

## 🔄 JAK ZMIENIĆ TRYB?

Kliknij dwukrotnie:
```
switch_phase.bat
```

Zobaczysz menu:
```
Wybierz fazę:
  1. Learning (7-14 dni, bardzo luźne limity)
  2. Optimization (7 dni, średnie limity)
  3. Production (na zawsze, ścisłe limity)
```

Wybierz numer i naciśnij Enter.

---

## 📁 WSZYSTKIE PLIKI .BAT

| Plik | Co robi |
|------|---------|
| `check_status.bat` | Sprawdź wszystko (tryb, bot, pozycje, etc) |
| `run_bot.bat` | Uruchom bota |
| `switch_phase.bat` | Zmień tryb (learning/optimization/production) |
| `check_learning_progress.bat` | Postęp uczenia się |
| `close_position.bat` | Zamknij konkretną pozycję |
| `close_all_positions.bat` | Zamknij wszystkie pozycje |
| `resume_trading.bat` | Wznów trading (reset emergency stop) |
| `adjust_limits.bat` | Zmień limity ryzyka |

**Wszystkie pliki .bat - po prostu kliknij dwukrotnie!**

---

## ❓ FAQ

### Q: Jaki tryb jest aktualnie aktywny?
**A:** Kliknij `check_status.bat` - zobaczysz na górze.

### Q: Czy bot jest uruchomiony?
**A:** Kliknij `check_status.bat` - zobaczysz "Bot Status".

### Q: Jak uruchomić bota?
**A:** Kliknij `run_bot.bat`.

### Q: Jak zatrzymać bota?
**A:** Naciśnij `Ctrl + C` w oknie bota, lub zamknij okno.

### Q: Czy mogę używać Visual Studio?
**A:** TAK, ale tylko do EDYCJI kodu. NIE do uruchamiania bota.

### Q: Dlaczego nie Visual Studio?
**A:** Bo:
- Trudniej zatrzymać bota
- Trudniej zobaczyć logi
- Trudniej debugować
- Pliki .bat są prostsze!

### Q: Co jeśli bot się zatrzymał (emergency stop)?
**A:** Kliknij `resume_trading.bat`.

### Q: Jak zamknąć pozycję?
**A:** Kliknij `close_position.bat` i wpisz parę (np. SOLUSDT).

### Q: Gdzie są logi?
**A:** W folderze `logs/bot.log`.

---

## 🎓 LEARNING PHASE (aktualny tryb)

Jeśli jesteś w trybie LEARNING:

**Co to znaczy:**
- Bot zbiera dane (50-100 tradów)
- Bardzo luźne limity (20% daily loss)
- Cel: Nauczyć się rynku
- Czas: 7-14 dni

**Co robić:**
1. Uruchom bota: `run_bot.bat`
2. Zostaw na 7-14 dni
3. Sprawdzaj postęp: `check_learning_progress.bat` (co 2-3 dni)
4. Po 7-14 dniach przełącz na Optimization: `switch_phase.bat`

**Nie martw się stratami!**
- To jest testnet (fake money)
- Bot się uczy
- Straty -5% do -15% są normalne
- Po 21 dniach (learning + optimization + production) bot będzie rentowny!

---

## 🆘 POMOC

Jeśli coś nie działa:

1. **Sprawdź status:**
   ```
   check_status.bat
   ```

2. **Sprawdź logi:**
   ```
   Otwórz: logs/bot.log
   ```

3. **Zrestartuj bota:**
   ```
   Ctrl + C (zatrzymaj)
   run_bot.bat (uruchom ponownie)
   ```

4. **Sprawdź czy Python działa:**
   ```
   python --version
   ```
   Powinno pokazać: Python 3.8 lub nowszy

---

## 📊 DASHBOARD

Bot ma dashboard (strona web):

```
http://localhost:5000
```

Otwórz w przeglądarce żeby zobaczyć:
- Wykresy
- Statystyki
- Pozycje
- Historia tradów

**UWAGA:** Dashboard działa tylko gdy bot jest uruchomiony!

---

## ✅ CHECKLIST

Przed pierwszym uruchomieniem:

- [ ] Python zainstalowany (3.8+)
- [ ] Zależności zainstalowane (`pip install -r requirements.txt`)
- [ ] Binance Testnet API keys w `config_testnet.yaml`
- [ ] Tryb ustawiony (sprawdź: `check_status.bat`)

Gotowy? Kliknij `run_bot.bat`! 🚀

---

## 🔧 VISUAL STUDIO VS COMMAND LINE

### Visual Studio (VS Code):
- To IDE (edytor kodu)
- Służy do EDYCJI kodu
- Można w nim uruchamiać skrypty Python (F5 lub Run)
- Ale NIE jest to najlepszy sposób dla botów
- Trudniej zatrzymać (trzeba kliknąć Stop)
- Trudniej zobaczyć logi

### Pliki .bat (kliknij dwukrotnie):
- Automatyzują uruchamianie
- Łatwiejsze logowanie (widać wszystko)
- Łatwiejsze zatrzymywanie (Ctrl+C)
- Profesjonalny sposób
- **ZALECANE!**

---

## 📞 KONTAKT

Jeśli masz pytania:
1. Sprawdź ten plik (START_HERE.md)
2. Sprawdź QUICK_START.txt
3. Sprawdź logi: logs/bot.log
4. Sprawdź status: check_status.bat
