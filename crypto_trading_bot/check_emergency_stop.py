#!/usr/bin/env python3
"""
Check why emergency stop was triggered

Usage:
    python check_emergency_stop.py
"""
import os
import json
import yaml
from datetime import datetime, date

def check_emergency_stop():
    """Check emergency stop status and reason"""
    print(f"\n{'='*60}")
    print(f"EMERGENCY STOP STATUS")
    print(f"{'='*60}\n")
    
    # Load config
    config_file = 'config_testnet.yaml'
    if not os.path.exists(config_file):
        config_file = 'config.yaml'
    
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        print(f"[OK] Konfiguracja: {config_file}")
    else:
        print(f"[WARN] Brak pliku konfiguracji")
        config = {}
    
    # Get safety limits from config
    safety_config = config.get('safety', {}).get('emergency_stop', {})
    max_daily_loss_pct = safety_config.get('daily_loss_pct', 10)
    max_consecutive_losses = safety_config.get('consecutive_losses', 5)
    max_price_anomaly_pct = safety_config.get('price_anomaly_pct', 10)
    
    print(f"\n[CONFIG] Limity bezpieczenstwa:")
    print(f"  Max dzienna strata: {max_daily_loss_pct}%")
    print(f"  Max strat z rzedu: {max_consecutive_losses}")
    print(f"  Max anomalia ceny: {max_price_anomaly_pct}%")
    
    # Load state
    state_file = './data/risk_state.json'
    if not os.path.exists(state_file):
        print(f"\n[INFO] Brak pliku stanu: {state_file}")
        print(f"[INFO] Bot prawdopodobnie nie byl jeszcze uruchomiony")
        return
    
    with open(state_file, 'r') as f:
        state = json.load(f)
    
    # Status
    emergency_active = state.get('emergency_stop_active', False)
    daily_stats = state.get('daily_stats', {})
    
    consecutive_losses = daily_stats.get('consecutive_losses', 0)
    daily_pnl = daily_stats.get('pnl', 0)
    trades_count = daily_stats.get('trades_count', 0)
    wins = daily_stats.get('wins', 0)
    losses = daily_stats.get('losses', 0)
    largest_win = daily_stats.get('largest_win', 0)
    largest_loss = daily_stats.get('largest_loss', 0)
    max_drawdown_pct = daily_stats.get('max_drawdown_pct', 0)
    state_date = daily_stats.get('date', 'N/A')
    
    # Calculate approximate daily loss percentage
    # Need initial capital for accurate calculation
    capital = state.get('capital', {})
    total_capital = sum(capital.values()) if capital else 0
    if total_capital > 0:
        daily_loss_pct = (daily_pnl / total_capital) * 100
    else:
        daily_loss_pct = 0
    
    # Status display
    print(f"\n{'='*60}")
    status_icon = "[ALERT]" if emergency_active else "[OK]"
    status_text = "AKTYWNY - TRADING WSTRZYMANY" if emergency_active else "Nieaktywny - trading normalny"
    print(f"{status_icon} Emergency Stop: {status_text}")
    print(f"{'='*60}")
    
    # Current values vs limits
    print(f"\n[VALUES] Aktualne wartosci vs limity:")
    
    # Consecutive losses
    cl_status = "[ALERT] PRZEKROCZONY!" if consecutive_losses >= max_consecutive_losses else "[OK]"
    print(f"  Strat z rzedu: {consecutive_losses} / {max_consecutive_losses} {cl_status}")
    
    # Daily PnL
    if daily_pnl < 0:
        dl_status = "[ALERT] PRZEKROCZONY!" if daily_loss_pct <= -max_daily_loss_pct else "[OK]"
    else:
        dl_status = "[OK]"
    print(f"  Dzienny PnL: {daily_pnl:.2f} USDT ({daily_loss_pct:+.2f}%) {dl_status}")
    
    # Max drawdown
    dd_status = "[ALERT] WYSOKI!" if max_drawdown_pct >= max_daily_loss_pct else "[OK]"
    print(f"  Max drawdown: {max_drawdown_pct:.2f}% {dd_status}")
    
    # Stats
    print(f"\n[STATS] Statystyki dzienne (data: {state_date}):")
    print(f"  Liczba tradow: {trades_count}")
    print(f"  Wygrane: {wins}")
    print(f"  Przegrane: {losses}")
    if trades_count > 0:
        win_rate = wins / trades_count * 100
        print(f"  Win rate: {win_rate:.1f}%")
    print(f"  Najwiekszy zysk: {largest_win:.2f} USDT")
    print(f"  Najwieksza strata: {largest_loss:.2f} USDT")
    
    # Capital
    if capital:
        print(f"\n[CAPITAL] Kapital:")
        for pair, amount in capital.items():
            print(f"  {pair}: {amount:.2f} USDT")
        print(f"  RAZEM: {total_capital:.2f} USDT")
    
    # Positions
    positions = state.get('positions', {})
    if positions:
        print(f"\n[POSITIONS] Otwarte pozycje: {len(positions)}")
        for symbol, pos in positions.items():
            print(f"  {symbol}: {pos}")
    
    # Reason analysis
    if emergency_active:
        print(f"\n{'='*60}")
        print(f"[ANALYSIS] Prawdopodobny powod aktywacji:")
        print(f"{'='*60}")
        
        reasons = []
        if consecutive_losses >= max_consecutive_losses:
            reasons.append(f"  [!] Zbyt wiele strat z rzedu: {consecutive_losses} >= {max_consecutive_losses}")
        if daily_loss_pct <= -max_daily_loss_pct:
            reasons.append(f"  [!] Dzienna strata przekroczona: {daily_loss_pct:.2f}% <= -{max_daily_loss_pct}%")
        if max_drawdown_pct >= max_daily_loss_pct:
            reasons.append(f"  [!] Drawdown przekroczony: {max_drawdown_pct:.2f}% >= {max_daily_loss_pct}%")
        
        if reasons:
            for r in reasons:
                print(r)
        else:
            print(f"  [?] Powod nieznany - mozliwa anomalia ceny lub manualny stop")
        
        print(f"\n[ACTION] Co zrobic:")
        print(f"  1. Przeanalizuj ostatnie trady")
        print(f"  2. Sprawdz logi: type logs\\bot.log | Select-String 'LOSS'")
        print(f"  3. Rozważ zmiane strategii lub limitow")
        print(f"  4. Reset: python reset_emergency_stop.py")
        print(f"  5. Wznow: run_bot.bat")
    else:
        print(f"\n[INFO] Emergency stop nie jest aktywny")
        print(f"[INFO] Trading moze dzialac normalnie")
        print(f"[INFO] Uruchom bota: run_bot.bat")
    
    # Reset info
    reset_at = state.get('reset_at')
    if reset_at:
        print(f"\n[INFO] Ostatni reset: {reset_at}")
        print(f"[INFO] Powod: {state.get('reset_reason', 'N/A')}")
    
    print()

if __name__ == '__main__':
    check_emergency_stop()
