#!/usr/bin/env python3
"""
Check learning progress and recommend next phase

Usage:
    python check_learning_progress.py
"""
import os
import json
import yaml
from datetime import datetime, timedelta

def load_config():
    """Load config file"""
    config_file = 'config_testnet.yaml'
    if not os.path.exists(config_file):
        config_file = 'config.yaml'
    
    if not os.path.exists(config_file):
        return None
    
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)

def load_state():
    """Load bot state"""
    state_file = './data/risk_state.json'
    if not os.path.exists(state_file):
        return None
    
    with open(state_file, 'r') as f:
        return json.load(f)

def load_learning_data():
    """Load learning module data"""
    learning_file = './data/learning/learning_data.json'
    if not os.path.exists(learning_file):
        return None
    
    with open(learning_file, 'r') as f:
        return json.load(f)

def check_learning_progress():
    """Check learning progress"""
    print(f"\n{'='*70}")
    print(f"LEARNING PROGRESS")
    print(f"{'='*70}\n")
    
    # Load config
    config = load_config()
    if not config:
        print(f"[ERROR] Brak pliku konfiguracji")
        return
    
    learning_config = config.get('learning_phase', {})
    current_phase = learning_config.get('phase', 'unknown')
    start_date_str = learning_config.get('start_date')
    target_trades = learning_config.get('target_trades')
    target_days = learning_config.get('target_days')
    
    print(f"[PHASE] Aktualna faza: {current_phase.upper()}")
    
    days_elapsed = 0
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            days_elapsed = (datetime.now() - start_date).days
            print(f"[TIME] Start: {start_date_str}")
            print(f"[TIME] Dni od rozpoczecia: {days_elapsed}")
            if target_days:
                progress_pct = min(100, days_elapsed / target_days * 100)
                print(f"[TIME] Cel: {target_days} dni")
                print(f"[TIME] Postep czasowy: {days_elapsed}/{target_days} ({progress_pct:.0f}%)")
        except ValueError:
            pass
    print()
    
    # Load state
    state = load_state()
    if not state:
        print(f"[WARNING] Brak pliku stanu - bot prawdopodobnie nie byl uruchomiony")
        print(f"[INFO] Uruchom bota: run_bot.bat")
        return
    
    # Stats from state
    daily_stats = state.get('daily_stats', {})
    total_trades = daily_stats.get('total_trades', 0)
    winning_trades = daily_stats.get('winning_trades', 0)
    losing_trades = daily_stats.get('losing_trades', 0)
    total_pnl = daily_stats.get('total_pnl', 0.0)
    consecutive_losses = state.get('consecutive_losses', 0)
    
    print(f"[STATS] Statystyki dzienne:")
    print(f"  Total trades: {total_trades}")
    
    if target_trades:
        progress_pct = min(100, total_trades / target_trades * 100)
        print(f"  Target trades: {target_trades}")
        print(f"  Postep tradow: {total_trades}/{target_trades} ({progress_pct:.0f}%)")
    
    win_rate = 0
    if total_trades > 0:
        win_rate = winning_trades / total_trades * 100
        print(f"  Winning trades: {winning_trades}")
        print(f"  Losing trades: {losing_trades}")
        print(f"  Win rate: {win_rate:.1f}%")
        print(f"  Total PnL: {total_pnl:.2f} USDT")
        print(f"  Consecutive losses: {consecutive_losses}")
    print()
    
    # Load learning data for more details
    learning_data = load_learning_data()
    if learning_data:
        patterns = learning_data.get('pattern_stats', {})
        symbols = learning_data.get('symbol_stats', {})
        
        if patterns:
            print(f"[PATTERNS] Statystyki patternow:")
            for pattern, stats in patterns.items():
                p_total = stats.get('total', 0)
                p_wins = stats.get('wins', 0)
                p_winrate = (p_wins / p_total * 100) if p_total > 0 else 0
                status = "[OK]" if p_winrate >= 45 else "[!]" if p_winrate >= 35 else "[X]"
                print(f"  {status} {pattern}: {p_total} trades, {p_winrate:.1f}% win rate")
            print()
        
        if symbols:
            print(f"[SYMBOLS] Statystyki par:")
            for symbol, stats in symbols.items():
                s_total = stats.get('total', 0)
                s_wins = stats.get('wins', 0)
                s_winrate = (s_wins / s_total * 100) if s_total > 0 else 0
                s_pnl = stats.get('pnl', 0)
                status = "[OK]" if s_pnl > 0 else "[!]" if s_pnl > -50 else "[X]"
                print(f"  {status} {symbol}: {s_total} trades, {s_winrate:.1f}% WR, {s_pnl:.2f} USDT")
            print()
    
    # Progress bars
    print(f"[PROGRESS] Wizualizacja postepu:")
    
    if target_trades:
        trade_pct = min(100, total_trades / target_trades * 100)
        trade_bar = "#" * int(trade_pct / 5) + "-" * (20 - int(trade_pct / 5))
        print(f"  Trades: [{trade_bar}] {trade_pct:.0f}%")
    
    if target_days:
        time_pct = min(100, days_elapsed / target_days * 100)
        time_bar = "#" * int(time_pct / 5) + "-" * (20 - int(time_pct / 5))
        print(f"  Czas:   [{time_bar}] {time_pct:.0f}%")
    
    print()
    
    # Recommendations
    print(f"[RECOMMEND] Zalecenia:")
    
    if current_phase == 'learning':
        checks = {
            'trades': total_trades >= 50,
            'days': days_elapsed >= 7,
            'patterns': learning_data and len(learning_data.get('pattern_stats', {})) >= 3 if learning_data else False
        }
        
        ready_for_optimization = all(checks.values())
        
        if ready_for_optimization:
            print(f"  [OK] Gotowy do Optimization Phase!")
            print(f"  [OK] Zebrano wystarczajaco danych ({total_trades} tradow)")
            print(f"  [OK] Uplynelo wystarczajaco czasu ({days_elapsed} dni)")
            print(f"\n  [ACTION] Przelacz na Optimization:")
            print(f"  python switch_phase.py optimization")
        else:
            print(f"  [!] Nie gotowy do nastepnej fazy:")
            if not checks['trades']:
                print(f"     - Potrzeba wiecej tradow: {total_trades}/50")
            if not checks['days']:
                print(f"     - Potrzeba wiecej czasu: {days_elapsed}/7 dni")
            if not checks.get('patterns', True):
                print(f"     - Potrzeba wiecej patternow")
            print(f"\n  [ACTION] Kontynuuj Learning Phase")
            
            # Estimate time remaining
            if total_trades > 0 and days_elapsed > 0:
                trades_per_day = total_trades / max(1, days_elapsed)
                remaining_trades = max(0, 50 - total_trades)
                remaining_days = int(remaining_trades / max(0.1, trades_per_day))
                print(f"\n  [ESTIMATE] Przy {trades_per_day:.1f} tradow/dzien:")
                print(f"     Pozostalo ~{remaining_days} dni do 50 tradow")
    
    elif current_phase == 'optimization':
        checks = {
            'total_trades': total_trades >= 80,
            'days': days_elapsed >= 14,
            'win_rate': win_rate > 45 if total_trades > 0 else False
        }
        
        ready_for_production = all(checks.values())
        
        if ready_for_production:
            print(f"  [OK] Gotowy do Production Phase!")
            print(f"  [OK] Win rate > 45% ({win_rate:.1f}%)")
            print(f"  [OK] Wystarczajaco tradow ({total_trades})")
            print(f"\n  [ACTION] Przelacz na Production:")
            print(f"  python switch_phase.py production")
        else:
            print(f"  [!] Nie gotowy do Production:")
            if not checks['total_trades']:
                print(f"     - Potrzeba wiecej tradow: {total_trades}/80")
            if not checks['win_rate']:
                print(f"     - Win rate za niski: {win_rate:.1f}% (cel: >45%)")
            if not checks['days']:
                print(f"     - Potrzeba wiecej czasu: {days_elapsed}/14 dni")
            print(f"\n  [ACTION] Kontynuuj Optimization Phase")
    
    elif current_phase == 'production':
        print(f"  [OK] Production Phase - kontynuuj trading!")
        if total_trades > 0:
            if win_rate > 55:
                print(f"  [OK] Swietny win rate: {win_rate:.1f}%")
            elif win_rate > 45:
                print(f"  [OK] Dobry win rate: {win_rate:.1f}%")
            else:
                print(f"  [!] Niski win rate: {win_rate:.1f}% - rozwaz retraining")
                print(f"\n  [ACTION] Rozwaz powrot do Optimization:")
                print(f"  python switch_phase.py optimization")
    else:
        print(f"  [!] Nieznana faza: {current_phase}")
        print(f"  [ACTION] Ustaw faze:")
        print(f"  python switch_phase.py learning")
    
    print()
    
    # Next steps
    print(f"{'='*70}")
    print(f"NEXT STEPS")
    print(f"{'='*70}\n")
    
    if current_phase == 'learning':
        print(f"1. Kontynuuj zbieranie danych (cel: 50-100 tradow)")
        print(f"2. Monitoruj postep: python check_learning_progress.py")
        print(f"3. Po 7-14 dniach: python switch_phase.py optimization")
    elif current_phase == 'optimization':
        print(f"1. Obserwuj win rate (cel: >45%)")
        print(f"2. Monitoruj ML retraining (co 3 dni)")
        print(f"3. Po osiagnieciu celow: python switch_phase.py production")
    elif current_phase == 'production':
        print(f"1. Monitoruj wyniki (cel: stabilny profit)")
        print(f"2. Sprawdzaj alerty i emergency stop")
        print(f"3. Rozwaz skalowanie pozycji jesli win rate > 55%")
    
    print()

if __name__ == '__main__':
    check_learning_progress()
