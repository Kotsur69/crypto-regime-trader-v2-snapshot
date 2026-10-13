# Emergency Stop Guide

## Co to jest Emergency Stop?

Funkcja bezpieczeństwa, która automatycznie zatrzymuje trading gdy:

| Warunek | Domyślny limit | Opis |
|---------|----------------|------|
| Dzienna strata | >= 10% | Zbyt duża strata w ciągu dnia |
| Straty z rzędu | >= 5 | Zbyt wiele przegranych tradów pod rząd |
| Anomalia ceny | >= 10% | Nagły ruch ceny (flash crash) |

## Jak sprawdzić status?

```bash
python check_emergency_stop.py
```

Pokaże:
- Czy emergency stop jest aktywny
- Aktualne wartości vs limity
- Prawdopodobny powód aktywacji
- Zalecane działania

## Jak zresetować?

### Opcja 1: Quick reset
```bash
python reset_emergency_stop.py
run_bot.bat
```

### Opcja 2: Resume trading (zalecane)
```bash
python resume_trading.py
run_bot.bat
```

### Opcja 3: Dashboard
1. Uruchom dashboard: `python dashboard.py`
2. Otwórz http://localhost:5000
3. Kliknij "Resume Trading" button

## Jak zmienić limity?

### Opcja 1: Interaktywnie
```bash
python adjust_limits.py
```

Opcje:
1. **Loose limits** - więcej tradów (dla aktywnego tradingu)
2. **Strict limits** - mniej tradów (dla konserwatywnego)
3. **Manual** - ustaw własne wartości
4. **Reset** - przywróć domyślne

### Opcja 2: Ręcznie

Edytuj `config_testnet.yaml`:

```yaml
safety:
  emergency_stop:
    daily_loss_pct: 15        # Było 10 - więcej tolerancji
    consecutive_losses: 8     # Było 5 - więcej tradów
    price_anomaly_pct: 15     # Było 10 - mniej wrażliwy

risk:
  max_positions: 6            # Było 3 - więcej pozycji
  position_size_pct: 1.5      # Było 2.0 - mniejsze pozycje
  max_drawdown_pct: 15        # Było 10 - więcej tolerancji
```

## Zalecane wartości

### Dla aktywnego tradingu (więcej tradów)
```yaml
safety:
  emergency_stop:
    daily_loss_pct: 15
    consecutive_losses: 8
    price_anomaly_pct: 15

risk:
  max_positions: 6
  position_size_pct: 1.5
```

### Dla konserwatywnego tradingu (mniej ryzyka)
```yaml
safety:
  emergency_stop:
    daily_loss_pct: 5
    consecutive_losses: 3
    price_anomaly_pct: 8

risk:
  max_positions: 2
  position_size_pct: 1.0
```

## Troubleshooting

### Emergency stop włącza się zbyt często

1. Zwiększ `consecutive_losses` do 8-10
2. Zwiększ `daily_loss_pct` do 15-20%
3. Zmniejsz `position_size_pct` - mniejsze pozycje = mniejsze straty
4. Sprawdź strategię - może wymaga optymalizacji

### Bot nie handluje mimo resetu

1. Sprawdź czy bot jest uruchomiony: `python check_status.py`
2. Sprawdź logi: `type logs\bot.log | Select-String 'ERROR'`
3. Sprawdź połączenie z API: `python check_testnet_pairs.py`
4. Zrestartuj bota: `run_bot.bat`

### Nie wiem dlaczego się włączył

```bash
python check_emergency_stop.py
```

Sprawdź też logi:
```bash
type logs\bot.log | Select-String 'EMERGENCY'
type logs\bot.log | Select-String 'LOSS'
type logs\bot.log | Select-String 'ALERT'
```

## Narzędzia

| Skrypt | Opis |
|--------|------|
| `check_emergency_stop.py` | Sprawdź status i powód |
| `reset_emergency_stop.py` | Resetuj emergency stop |
| `resume_trading.py` | Wznów trading (reset + info) |
| `adjust_limits.py` | Zmień limity interaktywnie |
| `check_status.py` | Ogólny status bota |

## API Dashboard

Endpoint do zarządzania emergency stop:

```
POST /api/emergency_stop
Body: {"action": "activate" | "deactivate" | "toggle"}
```

Przykład:
```bash
curl -X POST http://localhost:5000/api/emergency_stop -H "Content-Type: application/json" -d '{"action": "deactivate"}'
```

## Flow diagram

```
Trading aktywny
      |
      v
[Sprawdź warunki]
      |
      +-- Dzienna strata >= limit? --> EMERGENCY STOP
      |
      +-- Straty z rzędu >= limit? --> EMERGENCY STOP  
      |
      +-- Anomalia ceny >= limit? --> EMERGENCY STOP
      |
      v
Kontynuuj trading
```

## Uwagi

- Emergency stop to funkcja **bezpieczeństwa** - chroni przed dużymi stratami
- Nie wyłączaj całkowicie - ustaw rozsądne limity
- Po resecie przeanalizuj co poszło nie tak
- Rozważ zmniejszenie wielkości pozycji zamiast wyłączania limitu
