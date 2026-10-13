# Quick Fix: Zamknij pozycję z błędnym entry price

## Problem
Bot otworzył pozycję SOLUSDT SHORT z błędnym entry price 99.95 zamiast ~80.77.

### Przyczyna buga
W `execution_layer.py` funkcja `_get_simulated_price()` zwracała `100.0` dla nieznanych par (SOLUSDT nie było na liście). Z slippage (0.05%) dawało 99.95.

## Rozwiązanie natychmiastowe

### 1. Zamknij konkretną pozycję:
```bash
cd /home/ubuntu/crypto_trading_bot
python close_position.py SOLUSDT
```

### 2. Lub zamknij wszystkie pozycje:
```bash
python close_all_positions.py
```

### 3. Zrestartuj bota:
```bash
# Windows:
Ctrl + C
run_bot.bat

# Linux:
Ctrl + C
python main.py --config config_testnet.yaml
```

## Bug został naprawiony!

### Co zostało zmienione:

1. **`_paper_market_order()` teraz przyjmuje `reference_price`:**
   - Używa przekazanej ceny zamiast domyślnej
   - Dodano walidację ceny

2. **`place_market_order()` akceptuje `reference_price`:**
   - Parametr jest przekazywany do paper trading

3. **`open_position()` przekazuje `entry_price` do market order:**
   - `reference_price=entry_price` jest używane
   - Dodano walidację i logowanie

4. **Zaktualizowano `_get_simulated_price()`:**
   - Dodano wszystkie pary USDT i USDC
   - Dodano warning dla nieznanych par

### Logi debugowe
Po naprawie, w logach zobaczysz:
```
[DEBUG] open_position - entry_price: 80.77
[DEBUG] Using reference_price: 80.77
[LOG] Paper Market: SELL 0.217 SOLUSDT @ 80.77
```

## Weryfikacja naprawy
Po restarcie bota sprawdź czy entry price jest poprawne:
```
[OK] Pozycja otwarta: SOLUSDT SHORT | Entry: 80.77 | SL: 81.12 | TP: 80.02
```

Cena entry powinna być bardzo blisko aktualnej ceny rynkowej (±0.05% slippage).
