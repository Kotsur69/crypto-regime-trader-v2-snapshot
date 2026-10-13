# Binance Testnet vs Mainnet - Roznice

## Podsumowanie

| Cecha | Testnet | Mainnet |
|-------|---------|--------|
| Stablecoin | USDT | USDC |
| Kapital | Fake money | Real money |
| API URL | testnet.binance.vision | api.binance.com |
| Ryzyko | Zero | Wysokie |
| Pary | BTCUSDT, ETHUSDT... | BTCUSDC, ETHUSDC... |

## Pary tradingowe

### Testnet (testing)

**Dostepne stablecoiny:**
- USDT (Tether) - DOSTEPNE
- BUSD (Binance USD) - DEPRECATED
- USDC - NIE DOSTEPNE

**Nasze pary (testnet):**
```
BTCUSDT, ETHUSDT, SOLUSDT, ADAUSDT
AVAXUSDT, MATICUSDT, XRPUSDT, DOGEUSDT
```

### Mainnet (produkcja)

**Dostepne stablecoiny:**
- USDT (Tether) - DOSTEPNE
- USDC (USD Coin) - DOSTEPNE
- BUSD (Binance USD) - DEPRECATED

**Nasze pary (mainnet - planowane):**
```
BTCUSDC, ETHUSDC, SOLUSDC, ADAUSDC
AVAXUSDC, MATICUSDC, XRPUSDC, DOGEUSDC
```

## Dlaczego USDC na mainnet?

1. **Nizsze fees** - USDC czesto ma lepsze maker rebates na Binance
2. **Regulacje** - USDC jest bardziej regulowany (Circle, USA)
3. **Transparentnosc** - Pelne audyty rezerw co miesiac
4. **Integracje** - Lepsze integracje z DeFi (Ethereum native)
5. **Bezpieczenstwo** - Mniejsze ryzyko regulacyjne

## Dlaczego USDT na testnet?

1. **Dostepnosc** - Binance Testnet ma TYLKO USDT, brak USDC
2. **Testing** - Wystarczy do testowania strategii
3. **Podobienstwo** - USDT i USDC zachowuja sie podobnie (1:1 z USD)
4. **Funkcjonalnosc** - Wszystkie mechanizmy dzialaja identycznie

## Jak przelaczac miedzy srodowiskami?

### Testnet (paper trading)

```bash
# 1. Uruchom setup dla testnet:
python setup_testnet.py

# 2. Sprawdz dostepne pary:
python check_testnet_pairs.py

# 3. Uruchom bota:
python main.py --config config_testnet.yaml
```

### Mainnet (live trading)

```bash
# 1. Sprawdz SAFETY_CHECKLIST.md!
cat SAFETY_CHECKLIST.md

# 2. Sprawdz dostepne pary:
python check_mainnet_pairs.py

# 3. Uruchom setup dla mainnet:
python setup_mainnet.py

# 4. Uruchom bota:
python main.py --config config_mainnet.yaml
```

## Sprawdz dostepne pary

```bash
# Testnet (USDT):
python check_testnet_pairs.py

# Mainnet (USDC):
python check_mainnet_pairs.py
```

## Konfiguracja

### config_testnet.yaml
```yaml
binance:
  testnet: true

trading:
  pairs:
    - "BTCUSDT"
    - "ETHUSDT"
    # ... USDT pairs
```

### config_mainnet.yaml
```yaml
binance:
  testnet: false

trading:
  pairs:
    - "BTCUSDC"
    - "ETHUSDC"
    # ... USDC pairs
```

## Wazne informacje

### Testnet
- Wirtualne srodki (fake money)
- Mozesz doladowac na https://testnet.binance.vision/
- API keys z GitHub OAuth
- Bez limitow i restrykcji
- Idealne do testowania strategii

### Mainnet
- Prawdziwe pieniadze!
- API keys z konta Binance
- Wymagane IP whitelisting
- Limity withdrawal/trading
- Testuj minimum 30 dni na testnet przed uzyciem!

## FAQ

**Q: Dlaczego nie uzyc USDT na mainnet tez?**
A: Mozesz, ale USDC ma lepsze fees i jest bardziej regulowany.

**Q: Czy strategie dzialaja tak samo na USDT i USDC?**
A: Tak, zachowanie par jest identyczne. Tylko nazwa sie zmienia.

**Q: Co jesli para nie istnieje na testnet?**
A: Sprawdz `python check_testnet_pairs.py` i wybierz dostepna pare.

**Q: Czy moge uzyc USDT na mainnet?**
A: Tak, zmien pary w `config_mainnet.yaml` na USDT.
