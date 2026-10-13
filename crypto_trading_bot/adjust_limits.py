#!/usr/bin/env python3
"""
Adjust risk management limits

Use this to:
- Increase limits if emergency stop triggers too often
- Decrease limits for more conservative trading

Usage:
    python adjust_limits.py
"""
import os
import yaml
import shutil
from datetime import datetime

def show_current_limits(config: dict):
    """Show current limits"""
    safety = config.get('safety', {}).get('emergency_stop', {})
    risk = config.get('risk', {})
    
    print(f"\n[CURRENT] Aktualne limity:")
    print(f"  Emergency Stop:")
    print(f"    Max dzienna strata: {safety.get('daily_loss_pct', 10)}%")
    print(f"    Max strat z rzedu: {safety.get('consecutive_losses', 5)}")
    print(f"    Max anomalia ceny: {safety.get('price_anomaly_pct', 10)}%")
    print(f"  Risk Management:")
    print(f"    Max pozycji: {risk.get('max_positions', 3)}")
    print(f"    Wielkosc pozycji: {risk.get('position_size_pct', 2.0)}%")
    print(f"    Max drawdown: {risk.get('max_drawdown_pct', 10)}%")

def adjust_limits():
    """Adjust risk management limits interactively"""
    print(f"\n{'='*60}")
    print(f"ADJUST RISK MANAGEMENT LIMITS")
    print(f"{'='*60}\n")
    
    # Find config file
    config_file = 'config_testnet.yaml'
    if not os.path.exists(config_file):
        config_file = 'config.yaml'
    
    if not os.path.exists(config_file):
        print(f"[ERROR] Brak pliku konfiguracji!")
        return False
    
    print(f"[OK] Plik konfiguracji: {config_file}")
    
    # Load config
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Show current
    show_current_limits(config)
    
    # Menu
    print(f"\n{'='*60}")
    print(f"OPCJE:")
    print(f"{'='*60}")
    print(f"  1. Wiecej tradow (loose limits) - dla aktywnego tradingu")
    print(f"  2. Mniej tradow (strict limits) - dla konserwatywnego tradingu")
    print(f"  3. Reczna edycja - ustaw wlasne wartosci")
    print(f"  4. Reset do domyslnych")
    print(f"  5. Anuluj")
    
    choice = input(f"\nWybierz opcje (1-5): ")
    
    if choice == '1':
        # Loose limits for more trades
        print(f"\n[APPLY] Stosuje 'loose limits' dla wiekszej ilosci tradow...")
        
        if 'safety' not in config:
            config['safety'] = {}
        if 'emergency_stop' not in config['safety']:
            config['safety']['emergency_stop'] = {}
        if 'risk' not in config:
            config['risk'] = {}
        
        config['safety']['emergency_stop']['daily_loss_pct'] = 15
        config['safety']['emergency_stop']['consecutive_losses'] = 8
        config['safety']['emergency_stop']['price_anomaly_pct'] = 15
        config['risk']['max_positions'] = 6
        config['risk']['position_size_pct'] = 1.5
        config['risk']['max_drawdown_pct'] = 15
        
        new_limits = {
            'daily_loss_pct': 15,
            'consecutive_losses': 8,
            'price_anomaly_pct': 15,
            'max_positions': 6,
            'position_size_pct': 1.5,
            'max_drawdown_pct': 15
        }
        
    elif choice == '2':
        # Strict limits
        print(f"\n[APPLY] Stosuje 'strict limits' dla konserwatywnego tradingu...")
        
        if 'safety' not in config:
            config['safety'] = {}
        if 'emergency_stop' not in config['safety']:
            config['safety']['emergency_stop'] = {}
        if 'risk' not in config:
            config['risk'] = {}
        
        config['safety']['emergency_stop']['daily_loss_pct'] = 5
        config['safety']['emergency_stop']['consecutive_losses'] = 3
        config['safety']['emergency_stop']['price_anomaly_pct'] = 8
        config['risk']['max_positions'] = 2
        config['risk']['position_size_pct'] = 1.0
        config['risk']['max_drawdown_pct'] = 5
        
        new_limits = {
            'daily_loss_pct': 5,
            'consecutive_losses': 3,
            'price_anomaly_pct': 8,
            'max_positions': 2,
            'position_size_pct': 1.0,
            'max_drawdown_pct': 5
        }
        
    elif choice == '3':
        # Manual
        print(f"\n[MANUAL] Wprowadz nowe wartosci (Enter = zostaw aktualne):")
        
        if 'safety' not in config:
            config['safety'] = {}
        if 'emergency_stop' not in config['safety']:
            config['safety']['emergency_stop'] = {}
        if 'risk' not in config:
            config['risk'] = {}
        
        safety = config['safety']['emergency_stop']
        risk = config['risk']
        
        # Get new values
        val = input(f"  Max dzienna strata % [{safety.get('daily_loss_pct', 10)}]: ")
        if val: safety['daily_loss_pct'] = int(val)
        
        val = input(f"  Max strat z rzedu [{safety.get('consecutive_losses', 5)}]: ")
        if val: safety['consecutive_losses'] = int(val)
        
        val = input(f"  Max anomalia ceny % [{safety.get('price_anomaly_pct', 10)}]: ")
        if val: safety['price_anomaly_pct'] = int(val)
        
        val = input(f"  Max pozycji [{risk.get('max_positions', 3)}]: ")
        if val: risk['max_positions'] = int(val)
        
        val = input(f"  Wielkosc pozycji % [{risk.get('position_size_pct', 2.0)}]: ")
        if val: risk['position_size_pct'] = float(val)
        
        val = input(f"  Max drawdown % [{risk.get('max_drawdown_pct', 10)}]: ")
        if val: risk['max_drawdown_pct'] = int(val)
        
        new_limits = {
            'daily_loss_pct': safety.get('daily_loss_pct'),
            'consecutive_losses': safety.get('consecutive_losses'),
            'max_positions': risk.get('max_positions')
        }
        
    elif choice == '4':
        # Reset to defaults
        print(f"\n[RESET] Resetuje do domyslnych wartosci...")
        
        if 'safety' not in config:
            config['safety'] = {}
        config['safety']['emergency_stop'] = {
            'daily_loss_pct': 10,
            'consecutive_losses': 5,
            'price_anomaly_pct': 10
        }
        if 'risk' not in config:
            config['risk'] = {}
        config['risk']['max_positions'] = 3
        config['risk']['position_size_pct'] = 2.0
        config['risk']['max_drawdown_pct'] = 10
        
        new_limits = {
            'daily_loss_pct': 10,
            'consecutive_losses': 5,
            'price_anomaly_pct': 10,
            'max_positions': 3,
            'position_size_pct': 2.0,
            'max_drawdown_pct': 10
        }
        
    else:
        print(f"[INFO] Anulowano")
        return False
    
    # Backup
    backup_file = f"{config_file}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(config_file, backup_file)
    print(f"\n[BACKUP] Kopia zapasowa: {backup_file}")
    
    # Save
    with open(config_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print(f"[OK] Zapisano nowe limity do {config_file}")
    
    # Show new limits
    show_current_limits(config)
    
    # Next steps
    print(f"\n{'='*60}")
    print(f"NASTEPNE KROKI:")
    print(f"{'='*60}")
    print(f"  1. Zrestartuj bota: run_bot.bat")
    print(f"  2. Reset emergency stop jesli aktywny: python reset_emergency_stop.py")
    print(f"  3. Sprawdz status: python check_status.py")
    print()
    
    return True

if __name__ == '__main__':
    adjust_limits()
