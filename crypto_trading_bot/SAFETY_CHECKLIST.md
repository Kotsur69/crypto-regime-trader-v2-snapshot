# 🛡️ SAFETY CHECKLIST - Crypto Trading Bot

Przed uruchomieniem bota na prawdziwym koncie (mainnet), upewnij się, że spełniasz WSZYSTKIE poniższe kryteria.

---

## 📋 Przed Live Trading

### ✅ Paper Trading (OBOWIĄZKOWE)

| Kryterium | Wymagane | Twoja wartość | Status |
|-----------|----------|---------------|--------|
| Czas paper tradingu | ≥ 30 dni | ___ dni | □ |
| Liczba trade'ów | ≥ 50 | ___ trade'ów | □ |
| Całkowity P&L | > $0 | $___ | □ |
| Win Rate | > 55% | ___% | □ |
| Sharpe Ratio | > 1.0 | ___ | □ |
| Max Drawdown | < 15% | ___% | □ |
| Profit Factor | > 1.2 | ___ | □ |

### ✅ System Tests

| Test | Status |
|------|--------|
| Wszystkie unit testy przechodzą (`pytest tests/`) | □ |
| Emergency stop działa prawidłowo | □ |
| Discord notifications działają | □ |
| Dashboard jest dostępny | □ |
| Logi zapisują się poprawnie | □ |
| Backup config.yaml istnieje | □ |

### ✅ Bezpieczeństwo API

| Zabezpieczenie | Status |
|----------------|--------|
| IP Whitelist włączony | □ |
| Withdrawals WYŁĄCZONE | □ |
| API Key ma tylko Spot permissions | □ |
| Klucze przechowywane bezpiecznie (nie w git) | □ |
| 2FA włączone na koncie Binance | □ |

### ✅ Kapitał i Ryzyko

| Kryterium | Zalecane | Twoja wartość | Status |
|-----------|----------|---------------|--------|
| Kapitał startowy | $100-500 | $___ | □ |
| Max % portfela w bocie | < 10% | ___% | □ |
| Max strata którą akceptujesz | $___ | $___ | □ |
| Czy możesz stracić ten kapitał? | TAK | ___ | □ |

---

## 🔴 STOP! Nie uruchamiaj jeśli:

- [ ] Paper trading trwał krócej niż 30 dni
- [ ] Paper trading był nieoprofitowy
- [ ] Nie rozumiesz jak działa bot
- [ ] Używasz pożyczonych pieniędzy
- [ ] Nie możesz pozwolić sobie na stratę tego kapitału
- [ ] Nie masz czasu na monitoring przez pierwsze 2 tygodnie
- [ ] Withdrawals są WŁĄCZONE w API
- [ ] Nie masz IP whitelist

---

## 📊 Metryki Wymagane dla Live Trading

### Minimum (OBOWIĄZKOWE)

```
Win Rate:       > 55%
Profit Factor:  > 1.2
Max Drawdown:   < 15%
Sharpe Ratio:   > 1.0
Trade Count:    > 50
Test Period:    > 30 dni
```

### Zalecane (SILNIE REKOMENDOWANE)

```
Win Rate:       > 60%
Profit Factor:  > 1.5
Max Drawdown:   < 10%
Sharpe Ratio:   > 1.5
Trade Count:    > 100
Test Period:    > 60 dni
```

---

## 🛠️ Emergency Procedures

### Jak zatrzymać bota natychmiast:

```bash
# Metoda 1: Signal
pkill -SIGTERM -f main.py

# Metoda 2: Force kill
pkill -9 -f main.py

# Metoda 3: Dashboard
# Kliknij "Emergency Stop" w dashboard

# Metoda 4: Config
# Ustaw w config.yaml:
safety:
  emergency_stop:
    manual_stop: true
```

### Kiedy zatrzymać bota:

- 🔴 Strata > 10% kapitału w ciągu dnia
- 🔴 3+ kolejne straty
- 🔴 Nietypowe zachowanie rynku
- 🔴 Problem z API/połączeniem
- 🔴 Błędy w logach
- 🔴 Cokolwiek wygląda podejrzanie

### Po zatrzymaniu:

1. Sprawdź otwarte pozycje na Binance
2. Zamknij je ręcznie jeśli potrzeba
3. Przejrzyj logi: `tail -200 logs/trading_bot.log`
4. Zidentyfikuj przyczynę
5. Napraw problem
6. Przetestuj na testnet
7. Dopiero potem wznow mainnet

---

## 📆 Harmonogram Monitoringu

### Tydzień 1 (KRYTYCZNY)

| Dzień | Częstotliwość | Co sprawdzić |
|-------|--------------|-------------|
| 1 | Co 2 godziny | Wszystko |
| 2-3 | Co 3-4 godziny | Pozycje, P&L, Logi |
| 4-7 | 3x dziennie | Dashboard, Discord |

### Tydzień 2-4

| Okres | Częstotliwość | Co sprawdzić |
|-------|--------------|-------------|
| Tydz 2 | 2x dziennie | Dashboard, Metryki |
| Tydz 3-4 | Rano + Wieczór | P&L, Warnings |

### Po pierwszym miesiącu

- Sprawdzaj minimum raz dziennie
- Weekly review metryk
- Monthly backtest na nowych danych

---

## 💰 Skalowanie Kapitału

### Zasada: POWOLI I OSTROŻNIE

```
Tydzień 1-2:   $100 per para  (testowanie)
Tydzień 3-4:   $250 per para  (jeśli profitable)
Miesiąc 2:     $500 per para  (jeśli stabilny)
Miesiąc 3+:    +25-50% max    (jeśli konsekwentnie profitable)
```

### NIE zwiększaj kapitału jeśli:

- Ostatni tydzień był stratny
- Win rate spadł poniżej 55%
- Max drawdown > 10%
- Masz wątpliwości

---

## ⚠️ Disclaimer

```
⚠️ OSTRZEŻENIE DOTYCZĄCE RYZYKA

Trading kryptowalut wiąże się z WYSOKIM RYZYKIEM.

Możesz STRACIĆ CAŁY kapitał zainwestowany w bota.

Ten bot jest narzędziem, NIE gwarancją zysku.

Historyczne wyniki NIE gwarantują przyszłych zysków.

NIGDY nie traduj pieniędzmi, których nie możesz stracić.

NIGDY nie traduj pożyczonymi pieniędzmi.

ZAWSZE zaczynaj od minimalnego kapitału.

Używasz tego bota NA WŁASNE RYZYKO.
```

---

## ✅ Podpis

Przed uruchomieniem live tradingu, podpisz poniżej:

```
Ja, ___________________, oświadczam, że:

1. Przeczytałem/am cały SAFETY_CHECKLIST.md
2. Spełniam WSZYSTKIE kryteria z tego dokumentu
3. Rozumiem ryzyko utraty kapitału
4. Kapitał który przeznaczam mogę stracić
5. Będę aktywnie monitorować bota

Data: _______________
Podpis: _____________
```

---

**Pamiętaj: Lepiej przegapić okazję niż stracić pieniądze. Zawsze bądź ostrożny.**
