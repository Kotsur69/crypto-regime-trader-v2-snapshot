#!/usr/bin/env python3
"""
Resume trading after emergency stop

This script:
1. Checks current emergency stop status
2. Resets emergency stop if active
3. Resets consecutive losses counter
4. Shows current config and next steps

Usage:
    python resume_trading.py
"""
import os
import json
import yaml
from datetime import datetime, date

def resume_trading():
    """Resume trading after emergency stop"""
    print(f"\n{'='*60}")
    print(f"RESUME TRADING")
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
        print(f"[ERROR] Brak pliku konfiguracji!")
        return False
    
    # Check state file
    state_file = './data/risk_state.json'
    state = None
    
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            state = json.load(f)
        
        emergency_active = state.get('emergency_stop_active', False)
        daily_stats = state.get('daily_stats', {})
        consecutive_losses = daily_stats.get('consecutive_losses', 0)
        
        print(f"\n[STATUS] Aktualny stan:")
        print(f"  Emergency stop: {'AKTYWNY' if emergency_active else 'Nieaktywny'}")
        print(f"  Strat z rzedu: {consecutive_losses}")
        print(f"  Dzienny PnL: {daily_stats.get('pnl', 0):.2f} USDT")
        
        if emergency_active:
            print(f"\n[ACTION] Resetuje emergency stop...")
            
            # Reset
            state['emergency_stop_active'] = False
            if 'daily_stats' in state:
                state['daily_stats']['consecutive_losses'] = 0
            state['saved_at'] = datetime.now().isoformat()
            state['reset_at'] = datetime.now().isoformat()
            state['reset_reason'] = 'Resume trading via resume_trading.py'
            
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            print(f"[OK] Emergency stop zresetowany!")
            print(f"[OK] Consecutive losses zresetowane do 0")
        else:
            print(f"\n[INFO] Emergency stop nie jest aktywny")
    else:
        print(f"\n[INFO] Brak pliku stanu - tworze nowy...")
        
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        state = {
            'emergency_stop_active': False,
            'capital': {},
            'positions': {},
            'daily_stats': {
                'date': date.today().isoformat(),
                'trades_count': 0,
                'trades_per_pair': {},
                'pnl': 0,
                'wins': 0,
                'losses': 0,
                'largest_win': 0,
                'largest_loss': 0,
                'consecutive_losses': 0,
                'max_drawdown_pct': 0
            },
            'saved_at': datetime.now().isoformat(),
            'created_by': 'resume_trading.py'
        }
        
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
        
        print(f"[OK] Utworzono nowy plik stanu")
    
    # Show current config
    print(f"\n[CONFIG] Aktualna konfiguracja risk management:")
    safety_config = config.get('safety', {}).get('emergency_stop', {})
    print(f"  Max dzienna strata: {safety_config.get('daily_loss_pct', 10)}%")
    print(f"  Max strat z rzedu: {safety_config.get('consecutive_losses', 5)}")
    print(f"  Max anomalia ceny: {safety_config.get('price_anomaly_pct', 10)}%")
    
    risk_config = config.get('risk', {})
    if risk_config:
        print(f"\n  Max pozycji: {risk_config.get('max_positions', 3)}")
        print(f"  Wielkosc pozycji: {risk_config.get('position_size_pct', 2.0)}%")
        print(f"  Max drawdown: {risk_config.get('max_drawdown_pct', 10)}%")
    
    # Next steps
    print(f"\n{'='*60}")
    print(f"TRADING GOTOWY DO WZNOWIENIA")
    print(f"{'='*60}")
    print(f"\nNastepne kroki:")
    print(f"  1. Uruchom bota: run_bot.bat")
    print(f"  2. Monitoruj logi pod katem bledow")
    print(f"  3. Sprawdz status: python check_status.py")
    print(f"  4. Dashboard: python dashboard.py (port 5000)")
    print(f"\nJesli emergency stop wlacza sie zbyt czesto:")
    print(f"  python adjust_limits.py")
    print()
    
    return True

if __name__ == '__main__':
    resume_trading()
