# Learning Strategy - 3-Fazowa Strategia Uczenia Sie

## Dlaczego 3 fazy?

Bot ma 4 poziomy uczenia sie:
1. **Pattern Learning** - win rate per pattern
2. **Machine Learning** - Random Forest, grid search
3. **Portfolio Learning** - performance per pair
4. **Market Regime Adaptation** - learns which patterns work

Zeby sie nauczyc, bot potrzebuje **DANYCH** (trades).

### Problem ze scislymi limitami:
```
Scisle limity (5 strat z rzedu):
- Bot moze sie zatrzymac po 5 tradach
- To za malo danych do uczenia sie
- Machine Learning potrzebuje minimum 20-30 tradow
- Pattern Learning potrzebuje minimum 10 tradow per pattern
```

### Rozwiazanie - 3 fazy:
```
Faza 1: Learning (luzne limity) -> Zbieranie danych
Faza 2: Optimization (srednie limity) -> Optymalizacja
Faza 3: Production (scisle limity) -> Bezpieczny trading
```

---

## Faza 1: Learning Phase (7-14 dni)

### Cel:
- Zbieranie danych
- Uczenie sie podstawowych wzorcow
- Testowanie roznych warunkow rynkowych

### Limity:
```yaml
daily_loss_pct: 20%           # Bardzo luzne
consecutive_losses: 20        # Bardzo luzne
max_drawdown: 30%             # Bardzo luzne
max_positions: 8              # Wiecej pozycji
position_size: 1%             # Male pozycje
min_score_threshold: 55       # Nizszy prog
```

### Oczekiwane rezultaty:
- **50-100 tradow** w 7-14 dni
- **Win rate: 30-50%** (normalne na poczatku)
- **Drawdown: -10% do -25%** (akceptowalne)
- **Dane dla ML:** 50-100 tradow = wystarczajace

### Co sie dzieje:
1. Bot robi wiele tradow (6-10 dziennie)
2. Zbiera dane o win rate per pattern
3. Machine Learning trenuje sie co 7 dni
4. Portfolio Learning optymalizuje alokacje
5. Market Regime uczy sie warunkow

### Kiedy przejsc do Fazy 2:
- [x] Minimum 50 tradow
- [x] Wszystkie pary przetestowane (min 5 tradow per pair)
- [x] 7-14 dni uplynelo
- [x] Machine Learning wytrenowany (min 1 raz)

---

## Faza 2: Optimization Phase (7 dni)

### Cel:
- Optymalizacja strategii
- Fine-tuning parametrow
- Testowanie ze srednimi limitami

### Limity:
```yaml
daily_loss_pct: 10%           # Srednie
consecutive_losses: 10        # Srednie
max_drawdown: 15%             # Srednie
max_positions: 6              # Srednio
position_size: 1.5%           # Srednie pozycje
min_score_threshold: 58       # Sredni prog
```

### Oczekiwane rezultaty:
- **30-50 tradow** w 7 dni
- **Win rate: 45-60%** (poprawa!)
- **Drawdown: -5% do -12%** (lepsze)
- **Sharpe ratio: 1.0-1.5** (rozsadne)

### Co sie dzieje:
1. Bot uzywa nauczonych wzorcow
2. Machine Learning retraining co 3 dni
3. Portfolio Learning optymalizuje dalej
4. Patterns z <40% win rate sa wylaczane

### Kiedy przejsc do Fazy 3:
- [x] Win rate > 45%
- [x] Sharpe ratio > 1.0
- [x] 7 dni uplynelo
- [x] Stabilne wyniki (nie losowe)

---

## Faza 3: Production Phase (na zawsze)

### Cel:
- Bezpieczny trading
- Maksymalizacja zyskow
- Minimalizacja ryzyka

### Limity:
```yaml
daily_loss_pct: 8%            # Scisle
consecutive_losses: 8         # Scisle
max_drawdown: 10%             # Scisle
max_positions: 5              # Kontrolowane
position_size: 2%             # Normalne pozycje
min_score_threshold: 65       # Wysoki prog
```

### Oczekiwane rezultaty:
- **15-30 tradow** miesiecznie
- **Win rate: 55-70%** (dobry)
- **Drawdown: -3% do -8%** (niski)
- **Sharpe ratio: 1.5-2.5** (bardzo dobry)
- **Monthly return: +5% do +15%** (realistyczny)

### Co sie dzieje:
1. Bot uzywa tylko najlepszych sygnalow (score >= 65)
2. Machine Learning retraining co 14 dni
3. Portfolio Learning dynamicznie alokuje kapital
4. Tylko sprawdzone patterns sa uzywane

---

## Jak uzywac?

### Przelaczanie faz:
```bash
python switch_phase.py
```

### Sprawdzanie postepu:
```bash
python check_learning_progress.py
```

### Timeline:
```
Dzien 1-14:   Learning Phase (luzne limity)
Dzien 15-21:  Optimization Phase (srednie limity)
Dzien 22+:    Production Phase (scisle limity)
```

---

## Porownanie faz

| Parametr | Learning | Optimization | Production |
|----------|----------|--------------|------------|
| Daily Loss Limit | 20% | 10% | 8% |
| Consecutive Losses | 20 | 10 | 8 |
| Max Positions | 8 | 6 | 5 |
| Position Size | 1% | 1.5% | 2% |
| Min Trade Score | 55 | 58 | 65 |
| ML Retrain | 7 dni | 3 dni | 14 dni |
| Target Trades | 100 | 50 | - |
| Duration | 7-14 dni | 7 dni | Na zawsze |

---

## FAQ

### Q: Czy moge pominac faze Learning?
**A:** NIE. Bot potrzebuje danych zeby sie nauczyc. Bez danych, bedzie losowy.

### Q: Czy moge zostac w fazie Learning na zawsze?
**A:** NIE. Luzne limity = wieksze ryzyko. Po zebraniu danych, zaostrzaj limity.

### Q: Co jesli strace 30% w fazie Learning?
**A:** To jest testnet, wiec OK. Ale rozwaz zmniejszenie position_size do 0.5%.

### Q: Ile tradow potrzebuje bot zeby sie nauczyc?
**A:** Minimum 50 tradow. Optymalnie 100-200 tradow.

### Q: Czy moge uzywac tego na prawdziwych pieniadzach?
**A:** TAK, ale zacznij od malego kapitalu ($100-500) w fazie Learning.

### Q: Czy limity calkowicie wylaczone sa OK?
**A:** NIE. Nawet w fazie uczenia, bardzo luzne limity (20%) sa lepsze niz brak limitow.

### Q: Kiedy wlaczyc Discord powiadomienia?
**A:** W fazie Production. W fazie Learning bedzie za duzo powiadomien.

---

## Pliki konfiguracyjne

```
config_learning.yaml      # Faza 1 - Learning
config_optimization.yaml  # Faza 2 - Optimization
config_production.yaml    # Faza 3 - Production
config_testnet.yaml       # Aktywna konfiguracja
```

## Narzedzia

```
switch_phase.py           # Przelaczanie miedzy fazami
check_learning_progress.py # Sprawdzanie postepu
```

---

## Wizualizacja strategii

```
                    TIMELINE
    |-------- Learning --------|--- Opt ---|------ Production ------>
    Day 1                    Day 14      Day 21                 ...

                    RISK LEVEL
    HIGH |  *******
         |         *****
    MED  |              ******
         |                    ********
    LOW  |                            ****************************
         +-------------------------------------------------------->
              Learning    Optimization       Production

                    EXPECTED WIN RATE
    70%  |
         |                                    ******************
    55%  |                         **********
         |              ***********
    40%  |   ***********
         +-------------------------------------------------------->
              Learning    Optimization       Production
```

---

## Troubleshooting

### Bot zatrzymuje sie za czesto w Learning?
- Zwieksz `consecutive_losses` do 25
- Zwieksz `daily_loss_pct` do 25%
- Zmniejsz `position_size` do 0.5%

### Win rate nie poprawia sie w Optimization?
- Zostaw w Optimization dluzej (14 dni)
- Sprawdz ktore patterns dzialaja: `python check_learning_progress.py`
- Rozwaz wylaczenie zlych patterns recznie

### Bot robi za malo tradow?
- Zmniejsz `min_trade_score`
- Zwieksz `max_daily_trades_per_pair`
- Skroc `trade_cooldown_minutes`

---

*Ostatnia aktualizacja: 2026-02-24*
