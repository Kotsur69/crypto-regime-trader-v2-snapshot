# 🤖 Crypto Trading Bot v3.0

Zaawansowany bot do tradingu kryptowalutowego z modularną architekturą, analizą techniczną, zarządzaniem ryzykiem, Kelly Criterion, Scale Out i modułem uczenia się.

> **🆕 Wersja 3.0** - Nowe funkcje: Kelly Criterion Position Sizing, Scale Out (Partial Profit Taking), Smart Order Execution, 8 par tradingowych, Helper Scripts. [Zobacz szczegóły →](ADVANCED_FEATURES.md)

---

## 🚀 Quick Start (5 minut)

### Wymagania
- Python 3.9+
- Konto GitHub (dla Binance Testnet)

### 1. Instalacja

```bash
cd /home/ubuntu/crypto_trading_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Uzyskaj API Keys (Testnet)

1. Idź na https://testnet.binance.vision/
2. Zaloguj się przez GitHub
3. Kliknij "Generate HMAC_SHA256 Key"
4. Zapisz API Key i Secret Key

### 3. Konfiguracja (interaktywna)

```bash
python setup_testnet.py
```

### 4. Uruchom bota

```bash
python main.py --config config_testnet.yaml --dashboard
```

### 5. Otwórz Dashboard

```
http://localhost:5000
```

**📚 Szczegółowa instrukcja: [SETUP_GUIDE.md](SETUP_GUIDE.md)**

**🛡️ Przed live trading: [SAFETY_CHECKLIST.md](SAFETY_CHECKLIST.md)**

---

## 🔄 Testnet vs Mainnet

**Testnet (testing):**
- Pary: BTCUSDT, ETHUSDT, etc. (**USDT**)
- Kapital: Fake money (testowanie)
- API: https://testnet.binance.vision
- Bezpiecznie testuj strategie bez ryzyka

**Mainnet (produkcja):**
- Pary: BTCUSDC, ETHUSDC, etc. (**USDC**)
- Kapital: Real money (prawdziwe)
- API: https://api.binance.com
- USDC ma lepsze fees i regulacje

### Sprawdz dostepne pary

```bash
# Testnet (USDT):
python check_testnet_pairs.py

# Mainnet (USDC):
python check_mainnet_pairs.py
```

**Pelna dokumentacja: [TESTNET_VS_MAINNET.md](TESTNET_VS_MAINNET.md)**

---

## 🪟 Instalacja na Windows

> **Pełna instrukcja Windows: [WINDOWS_SETUP.md](WINDOWS_SETUP.md)**

### Quick Start (Windows)

**Opcja 1: Automatyczna (zalecana)**
```cmd
setup_windows.bat
```

**Opcja 2: Ręczna (PowerShell)**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python setup_testnet.py
python main.py --config config_testnet.yaml
```

### Pliki pomocnicze (Windows)

| Plik | Opis |
|------|------|
| `setup_windows.bat` | Automatyczny setup (venv + dependencies) |
| `activate.bat` | Aktywuje venv i otwiera terminal |
| `run_bot.bat` | Uruchamia bota (testnet) |

### Różnice Windows vs Linux/Mac

| Akcja | Linux/Mac | Windows (PowerShell) |
|-------|-----------|---------------------|
| Aktywacja venv | `source venv/bin/activate` | `.\venv\Scripts\Activate.ps1` |
| Aktywacja venv | `source venv/bin/activate` | `venv\Scripts\activate.bat` (CMD) |
| Ścieżki | `/home/user/...` | `C:\Users\User\...` |
| Separator | `/` | `\` |

---

## 📋 Spis treści

- [Funkcjonalności](#-funkcjonalności)
- [Architektura](#-architektura)
- [Instalacja](#-instalacja)
- [Konfiguracja](#-konfiguracja)
- [Uzyskanie API Keys](#-uzyskanie-api-keys-binance-testnet)
- [Uruchomienie](#-uruchomienie)
- [Moduły](#-moduły)
- [Strategie tradingowe](#-strategie-tradingowe)
- [Zarządzanie ryzykiem](#-zarządzanie-ryzykiem)
- [Backtesting](#-backtesting)
- [Bezpieczeństwo](#-bezpieczeństwo)
- [Przyszłe ulepszenia](#-przyszłe-ulepszenia)

## ✨ Funkcjonalności

### Trading
- 📊 **Multi-pair trading**: 8 par (BTC, ETH, SOL, ADA, AVAX, MATIC, XRP, DOGE)
- ⏰ **Multi-timeframe analysis**: 15m (główny) + 1h (trend)
- 💰 **Paper trading**: Wirtualny kapitał 5,000 USDC na parę (40,000 total)
- 🎯 **Kelly Criterion**: Dynamiczne position sizing
- 📈 **Scale Out**: Partial profit taking (TP1, TP2, TP3)
- 📈 **Wskaźniki techniczne**: EMA (9/21/50/100), RSI, Stochastic RSI, MACD, Volume
- 🎯 **Pattern recognition**: Pullback do EMA, Momentum shift, RSI reversal, Volume breakout

### Zarządzanie ryzykiem
- ⚠️ **R:R minimum**: 1:1.5
- 🛑 **Stop Loss/Take Profit**: Automatyczne ustawianie i zarządzanie
- 📉 **Max drawdown**: 5% dziennie
- 🔢 **Limity trade'ów**: 5 na parę / 15 łącznie dziennie
- 🚨 **Emergency stop**: Automatyczne zatrzymanie przy anomaliach

### Uczenie się
- 📝 **Tracking patternów**: Zapisuje każdy trade
- 📊 **Analiza skuteczności**: Automatycznie wyłącza nieskuteczne strategie
- 📈 **Raporty**: Szczegółowe statystyki performance

## 🏗 Architektura

```
crypto_trading_bot/
├── main.py              # Główna pętla bota
├── config.yaml          # Konfiguracja
├── requirements.txt     # Zależności
├── README.md            # Dokumentacja podstawowa
├── ADVANCED_FEATURES.md # Dokumentacja zaawansowanych funkcji
│
│ # MODUŁY PODSTAWOWE
├── data_fetcher.py      # Pobieranie danych z Binance
├── indicators.py        # Obliczanie wskaźników technicznych
├── pattern_analyzer.py  # Wykrywanie patternów
├── decision_engine.py   # Logika decyzyjna
├── risk_manager.py      # Zarządzanie ryzykiem + trailing stop
├── learning_module.py   # Uczenie się i tracking
├── execution_layer.py   # Wykonywanie zleceń
├── backtester.py        # Backtesting strategii
│
│ # MODUŁY ZAAWANSOWANE (v2.0)
├── discord_notifier.py  # Powiadomienia Discord
├── dashboard.py         # Web Dashboard (Flask)
├── technical_levels.py  # Fibonacci & Support/Resistance
├── market_regime.py     # Wykrywanie stanu rynku
├── orderbook_analyzer.py # Analiza order book
├── portfolio_manager.py # Rebalancing portfolio
├── ml_optimizer.py      # ML optymalizacja parametrów
│
├── templates/           # Szablony HTML dla dashboardu
│
├── data/                # Dane (generowane)
│   ├── learning/        # Historia trade'ów
│   ├── execution/       # Stan pozycji
│   ├── ml/              # Wyniki ML optimization
│   └── risk_state.json  # Stan risk managera
│
├── logs/                # Logi (generowane)
└── reports/             # Raporty backtestów
```

## 🚀 Instalacja

### 1. Klonowanie/Pobieranie

```bash
cd /home/ubuntu
# Jeśli już masz projekt:
cd crypto_trading_bot
```

### 2. Tworzenie środowiska wirtualnego (zalecane)

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# lub
.\venv\Scripts\activate   # Windows
```

### 3. Instalacja zależności

```bash
pip install -r requirements.txt
```

### 4. Konfiguracja

```bash
# Skopiuj przykładowy config
cp config.yaml config_local.yaml

# Edytuj i dodaj swoje klucze API
nano config_local.yaml
```

## ⚙️ Konfiguracja

### config.yaml - Główne parametry

```yaml
# Binance API
binance:
  api_key: "YOUR_TESTNET_API_KEY"
  api_secret: "YOUR_TESTNET_API_SECRET"
  testnet: true  # ZAWSZE true dla bezpieczeństwa

# Pary do handlu
trading:
  pairs:
    - "BTCUSDC"
    - "ETHUSDC"
    - "XRPUSDC"
    - "DOGEUSDC"
  primary_timeframe: "15m"
  trend_timeframe: "1h"
  initial_capital_per_pair: 10000

# Zarządzanie ryzykiem
risk:
  min_risk_reward: 1.5
  max_risk_per_trade_pct: 2
  max_daily_drawdown_pct: 5
  max_daily_trades_per_pair: 5

# Paper trading
paper_trading:
  enabled: true
  simulated_fee_pct: 0.1
```

## 🔑 Uzyskanie API Keys (Binance Testnet)

1. **Wejdź na Binance Testnet**: https://testnet.binance.vision/

2. **Zaloguj się przez GitHub**:
   - Kliknij "Log In with GitHub"
   - Autoryzuj dostęp

3. **Wygeneruj klucze API**:
   - Kliknij "Generate HMAC_SHA256 Key"
   - Skopiuj **API Key** i **Secret Key**
   - ⚠️ Secret Key jest pokazany tylko raz!

4. **Dodaj do konfiguracji**:
   ```yaml
   binance:
     api_key: "wygenerowany_api_key"
     api_secret: "wygenerowany_secret_key"
     testnet: true
   ```

5. **Uzyskaj testowe środki**:
   - Na Testnet Spot możesz generować darmowe środki
   - Kliknij "Get BTC" / "Get USDT" etc.

## 🎮 Uruchomienie

### Paper Trading (domyślny tryb)

```bash
python main.py
```

### Backtest

```bash
# Backtest BTCUSDC, 30 dni
python main.py --backtest

# Backtest z parametrami
python main.py --backtest --symbol ETHUSDC --days 60
```

### Status

```bash
python main.py --status
```

### Graceful Shutdown

Naciśnij `CTRL+C` - bot zamknie wszystkie pozycje i zapisze stan.

## 📦 Moduły

### data_fetcher.py
- Połączenie z Binance API (Testnet)
- Pobieranie danych OHLCV
- Cache i reconnect przy utracie połączenia

### indicators.py
- EMA (9, 21, 50, 100)
- RSI i Stochastic RSI
- MACD z histogramem
- Wskaźniki wolumenowe
- ATR (Average True Range)

### pattern_analyzer.py
- **EMA Pullback**: Cofnięcie do EMA w trendzie
- **Momentum Shift**: Zmiana kierunku MACD histogram
- **RSI Reversal**: Odwrócenie z oversold/overbought W KONTEKŚCIE TRENDU
- **Volume Breakout**: Wybicie z wysokim wolumenem
- **Trend Continuation**: Kontynuacja silnego trendu

### decision_engine.py
- Ocena sygnałów z ważonym scoringiem
- Multi-timeframe confirmation
- Walidacja warunków aktywacji/unieważnienia
- Rekomendacja: TRADE / NO TRADE / WAIT

### risk_manager.py
- Kalkulacja wielkości pozycji
- Stop Loss / Take Profit / Trailing Stop
- Dzienny drawdown limit
- Emergency stop przy anomaliach

### learning_module.py
- Zapis każdego trade'a
- Tracking skuteczności patternów
- Automatyczne wyłączanie nieskutecznych strategii
- Generowanie raportów

### execution_layer.py
- Paper trading (domyślnie)
- Market/Limit/Stop orders
- Zarządzanie otwartymi pozycjami

### backtester.py
- Testowanie na danych historycznych
- Metryki: Win rate, Profit factor, Sharpe ratio, Max drawdown
- Generowanie raportów i wykresów

## 📈 Strategie tradingowe

### Filozofia
- **NO TRADE** jest zawsze opcją
- Każdy pattern ma warunek aktywacji i unieważnienia
- RSI oversold/overbought to WARUNEK, nie sygnał
- Volume potwierdza lub osłabia ruch

### Przykładowe setupy

#### 1. EMA Pullback (Bullish)
```
✅ Warunki:
- EMA stack bullish (9 > 21 > 50 > 100)
- Cena cofnęła się do EMA 9/21
- Świeca pokazuje odrzucenie (lower wick)
- Volume powyżej średniej

❌ Unieważnienie:
- Cena zamknie poniżej stop loss
- EMA stack zmieni się na bearish
```

#### 2. Momentum Shift
```
✅ Warunki:
- MACD histogram zmienia kierunek
- W kierunku większego trendu (HTF)
- Volume potwierdza

❌ Unieważnienie:
- MACD histogram wróci do poprzedniego kierunku
```

## ⚠️ Zarządzanie ryzykiem

| Parametr | Wartość | Opis |
|----------|---------|------|
| Min R:R | 1.5 | Minimalny stosunek Risk:Reward |
| Max risk/trade | 2% | Maksymalne ryzyko na jeden trade |
| Max drawdown | 5% | Maksymalny dzienny drawdown |
| Max trades/pair | 5 | Maksymalna liczba trade'ów na parę dziennie |
| Max trades/total | 15 | Maksymalna liczba trade'ów łącznie |
| Trailing stop | 1% | Odległość trailing stop po aktywacji |

## 🔬 Backtesting

```bash
# Uruchom backtest
python main.py --backtest --symbol BTCUSDC --days 30

# Wyniki w:
# - reports/backtest_BTCUSDC_*.txt  (raport tekstowy)
# - reports/backtest_BTCUSDC_*.json (pełne dane)
# - reports/equity_BTCUSDC_*.png    (wykres)
```

### Metryki backtestingu
- Total PnL / PnL %
- Win rate
- Profit factor
- Expectancy
- Max drawdown
- Sharpe ratio
- Breakdown per pattern

## 🔒 Bezpieczeństwo

1. **Tylko Testnet**: `force_testnet_only: true` w config
2. **Limity pozycji**: Max 20% kapitału na pozycję
3. **Max wartość zlecenia**: 2000 USDC
4. **Emergency stop**: Automatyczny przy:
   - Dziennej stracie > 10%
   - 5+ stratach z rzędu
   - Anomalii cenowej > 10% w 5 min

⚠️ **NIGDY nie używaj tego bota z prawdziwymi środkami bez dokładnego testowania!**

## 🔮 Przyszłe ulepszenia

### Priorytet wysoki
- [ ] WebSocket dla real-time data
- [ ] Telegram/Discord notyfikacje
- [ ] Dashboard webowy (Flask/Streamlit)
- [ ] Więcej patternów (divergence, head & shoulders)

### Priorytet średni
- [ ] Machine Learning do optymalizacji parametrów
- [ ] Sentiment analysis (Twitter, Reddit)
- [ ] Portfolio correlation analysis
- [ ] Automatyczna optymalizacja parametrów

### Priorytet niski
- [ ] Support dla futures/margin
- [ ] Multi-exchange support
- [ ] Mobile app
- [ ] Cloud deployment (AWS/GCP)

## 📊 Struktura danych

### Trade Record
```json
{
  "trade_id": "BTCUSDC_20240115120000",
  "symbol": "BTCUSDC",
  "direction": "LONG",
  "pattern_type": "ema_pullback_bullish",
  "entry_price": 42000.00,
  "exit_price": 43500.00,
  "stop_loss": 41000.00,
  "take_profit": 44000.00,
  "quantity": 0.01,
  "pnl": 15.00,
  "pnl_pct": 3.57,
  "exit_reason": "TAKE_PROFIT",
  "confidence": 75.0
}
```

## 🐛 Troubleshooting

### Problem: "Brak połączenia z API"
```bash
# Sprawdź połączenie
ping testnet.binance.vision

# Sprawdź klucze API w config
grep api_key config.yaml
```

### Problem: "Brak danych"
```bash
# Sprawdź czy para istnieje na testnet
# Niektóre pary mogą nie być dostępne
```

### Problem: "Module not found"
```bash
# Upewnij się, że aktywowałeś venv
source venv/bin/activate
pip install -r requirements.txt
```

## 📝 Licencja

MIT License - używaj na własną odpowiedzialność.

## ⚠️ Disclaimer

**Ten bot jest przeznaczony wyłącznie do celów edukacyjnych i testowych.**

Trading kryptowalutami wiąże się z wysokim ryzykiem utraty kapitału. Autor nie ponosi odpowiedzialności za jakiekolwiek straty finansowe wynikające z używania tego oprogramowania.

**NIGDY nie handluj prawdziwymi środkami bez dokładnego zrozumienia ryzyka i przetestowania strategii.**
