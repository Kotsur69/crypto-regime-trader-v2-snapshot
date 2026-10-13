#!/usr/bin/env python3
"""
Reset Emergency Stop and resume trading

Usage:
    python reset_emergency_stop.py
"""
import os
import json
import yaml
from datetime import datetime, date

def reset_emergency_stop():
    """Reset emergency stop and resume trading"""
    print(f"\n{'='*60}")
    print(f"RESET EMERGENCY STOP")
    print(f"{'='*60}\n")
    
    # Load config
    config_file = 'config_testnet.yaml'
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        print(f"[OK] Zaladowano konfiguracje: {config_file}")
    else:
        print(f"[WARN] Brak pliku konfiguracji: {config_file}")
        config = {}
    
    # Check if state file exists
    state_file = './data/risk_state.json'
    
    if os.path.exists(state_file):
        print(f"[INFO] Znaleziono plik stanu: {state_file}")
        
        with open(state_file, 'r') as f:
            state = json.load(f)
        
        # Show current state
        print(f"\n[INFO] Aktualny stan:")
        print(f"  Emergency stop: {state.get('emergency_stop_active', False)}")
        
        daily_stats = state.get('daily_stats', {})
        print(f"  Consecutive losses: {daily_stats.get('consecutive_losses', 0)}")
        print(f"  Daily PnL: {daily_stats.get('pnl', 0):.2f} USDT")
        print(f"  Trades today: {daily_stats.get('trades_count', 0)}")
        print(f"  Wins: {daily_stats.get('wins', 0)}")
        print(f"  Losses: {daily_stats.get('losses', 0)}")
        print(f"  Saved at: {state.get('saved_at', 'N/A')}")
        
        # Confirm reset
        print(f"\n[QUESTION] Czy na pewno chcesz zresetowac emergency stop?")
        confirm = input("Wpisz 'yes' aby potwierdzic: ")
        
        if confirm.lower() != 'yes':
            print(f"[INFO] Anulowano")
            return False
        
        # Reset emergency stop
        state['emergency_stop_active'] = False
        
        # Reset consecutive losses
        if 'daily_stats' in state:
            state['daily_stats']['consecutive_losses'] = 0
        
        # Update timestamp
        state['saved_at'] = datetime.now().isoformat()
        state['reset_at'] = datetime.now().isoformat()
        state['reset_reason'] = 'Manual reset via reset_emergency_stop.py'
        
        # Save
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
        
        print(f"\n[OK] Emergency stop zresetowany!")
        print(f"[OK] Consecutive losses zresetowane do 0")
        print(f"[INFO] Bot moze teraz wznowic trading")
        
    else:
        print(f"[INFO] Brak pliku stanu: {state_file}")
        print(f"[INFO] Emergency stop prawdopodobnie w pamieci")
        print(f"[INFO] Zrestartuj bota zeby zresetowac")
        
        # Create initial state file
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        initial_state = {
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
            'created_by': 'reset_emergency_stop.py'
        }
        
        with open(state_file, 'w') as f:
            json.dump(initial_state, f, indent=2)
        
        print(f"[OK] Utworzono nowy plik stanu z emergency_stop_active=False")
    
    # Show next steps
    print(f"\n{'='*60}")
    print(f"NASTEPNE KROKI:")
    print(f"{'='*60}")
    print(f"1. Jesli bot jest uruchomiony - zrestartuj go")
    print(f"2. Jesli bot nie jest uruchomiony - uruchom: run_bot.bat")
    print(f"3. Sprawdz status: python check_status.py")
    print(f"4. Monitoruj logi pod katem EMERGENCY")
    print()
    
    return True

if __name__ == '__main__':
    reset_emergency_stop()
