#!/usr/bin/env python3
"""
Switch between learning phases

Usage:
    python switch_phase.py
    python switch_phase.py learning
    python switch_phase.py optimization
    python switch_phase.py production
"""
import os
import sys
import shutil
import yaml
from datetime import datetime

PHASES = {
    'learning': {
        'config': 'config_learning.yaml',
        'description': 'Learning Phase - Zbieranie danych (7-14 dni)',
        'duration': '7-14 dni',
        'target_trades': 100,
        'limits': 'Bardzo luzne (20% daily loss, 20 consecutive losses)',
        'position_size': '1% (male pozycje)',
        'min_score': 55
    },
    'optimization': {
        'config': 'config_optimization.yaml',
        'description': 'Optimization Phase - Optymalizacja strategii (7 dni)',
        'duration': '7 dni',
        'target_trades': 50,
        'limits': 'Srednie (10% daily loss, 10 consecutive losses)',
        'position_size': '1.5% (srednie pozycje)',
        'min_score': 58
    },
    'production': {
        'config': 'config_production.yaml',
        'description': 'Production Phase - Bezpieczny trading (na zawsze)',
        'duration': 'Na zawsze',
        'target_trades': 'Brak celu',
        'limits': 'Scisle (8% daily loss, 8 consecutive losses)',
        'position_size': '2% (normalne pozycje)',
        'min_score': 65
    }
}

def get_current_phase():
    """Get current phase from config"""
    if not os.path.exists('config_testnet.yaml'):
        return None
    
    try:
        with open('config_testnet.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        learning_config = config.get('learning_phase', {})
        return learning_config.get('phase', 'unknown')
    except Exception:
        return 'unknown'

def switch_phase(target_phase):
    """Switch to target phase"""
    if target_phase not in PHASES:
        print(f"[ERROR] Nieznana faza: {target_phase}")
        print(f"[INFO] Dostepne fazy: {', '.join(PHASES.keys())}")
        return False
    
    phase_info = PHASES[target_phase]
    config_file = phase_info['config']
    
    if not os.path.exists(config_file):
        print(f"[ERROR] Brak pliku konfiguracji: {config_file}")
        return False
    
    # Backup current config
    if os.path.exists('config_testnet.yaml'):
        backup_file = f"config_testnet_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
        shutil.copy('config_testnet.yaml', backup_file)
        print(f"[INFO] Backup utworzony: {backup_file}")
    
    # Load source config
    with open(config_file, 'r') as f:
        new_config = yaml.safe_load(f)
    
    # Update start date to today
    if 'learning_phase' in new_config:
        new_config['learning_phase']['start_date'] = datetime.now().strftime('%Y-%m-%d')
    
    # Copy API keys from existing config if present
    if os.path.exists('config_testnet.yaml'):
        try:
            with open('config_testnet.yaml', 'r') as f:
                old_config = yaml.safe_load(f)
            
            if old_config.get('binance', {}).get('api_key') != 'YOUR_TESTNET_API_KEY':
                new_config['binance']['api_key'] = old_config['binance']['api_key']
                new_config['binance']['api_secret'] = old_config['binance']['api_secret']
        except Exception:
            pass
    
    # Save new config
    with open('config_testnet.yaml', 'w') as f:
        yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    print(f"[OK] Przelaczono na faze: {target_phase.upper()}")
    return True

def show_phases():
    """Show all phases"""
    current_phase = get_current_phase()
    
    print(f"\n{'='*70}")
    print(f"LEARNING PHASES")
    print(f"{'='*70}\n")
    
    for phase_name, phase_info in PHASES.items():
        is_current = phase_name == current_phase
        marker = "-> " if is_current else "   "
        
        print(f"{marker}[{phase_name.upper()}]")
        print(f"     Opis: {phase_info['description']}")
        print(f"     Czas trwania: {phase_info['duration']}")
        print(f"     Cel tradow: {phase_info['target_trades']}")
        print(f"     Limity: {phase_info['limits']}")
        print(f"     Rozmiar pozycji: {phase_info['position_size']}")
        print(f"     Min score: {phase_info['min_score']}")
        if is_current:
            print(f"     Status: AKTYWNA [*]")
        print()

def show_comparison():
    """Show comparison table"""
    print(f"\n{'='*70}")
    print(f"POROWNANIE FAZ")
    print(f"{'='*70}\n")
    
    print(f"{'Parametr':<25} {'Learning':<15} {'Optimization':<15} {'Production':<15}")
    print(f"{'-'*70}")
    print(f"{'Daily Loss Limit':<25} {'20%':<15} {'10%':<15} {'8%':<15}")
    print(f"{'Consecutive Losses':<25} {'20':<15} {'10':<15} {'8':<15}")
    print(f"{'Max Positions':<25} {'8':<15} {'6':<15} {'5':<15}")
    print(f"{'Position Size':<25} {'1%':<15} {'1.5%':<15} {'2%':<15}")
    print(f"{'Min Trade Score':<25} {'55':<15} {'58':<15} {'65':<15}")
    print(f"{'ML Retrain':<25} {'7 dni':<15} {'3 dni':<15} {'14 dni':<15}")
    print(f"{'Target Trades':<25} {'100':<15} {'50':<15} {'-':<15}")
    print(f"{'Duration':<25} {'7-14 dni':<15} {'7 dni':<15} {'Na zawsze':<15}")
    print()

def main():
    print(f"\n{'='*70}")
    print(f"SWITCH LEARNING PHASE")
    print(f"{'='*70}\n")
    
    current_phase = get_current_phase()
    print(f"[INFO] Aktualna faza: {current_phase.upper() if current_phase else 'BRAK'}\n")
    
    # Check for command line argument
    if len(sys.argv) > 1:
        target_phase = sys.argv[1].lower()
        if target_phase in PHASES:
            if switch_phase(target_phase):
                print(f"\n[OK] Faza zmieniona na: {target_phase.upper()}")
                print(f"[INFO] Zrestartuj bota: run_bot.bat")
            return
        elif target_phase == 'show' or target_phase == 'info':
            show_phases()
            show_comparison()
            return
        else:
            print(f"[ERROR] Nieznana faza: {target_phase}")
            print(f"[INFO] Dostepne: learning, optimization, production, show")
            return
    
    show_phases()
    show_comparison()
    
    print(f"{'='*70}")
    print(f"Wybierz faze:")
    print(f"  1. Learning (7-14 dni, bardzo luzne limity)")
    print(f"  2. Optimization (7 dni, srednie limity)")
    print(f"  3. Production (na zawsze, scisle limity)")
    print(f"  4. Pokaz tylko informacje (bez zmiany)")
    print(f"  0. Wyjscie")
    print(f"{'='*70}\n")
    
    try:
        choice = input("Wybor (0/1/2/3/4): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Anulowano")
        return
    
    if choice == '1':
        target_phase = 'learning'
    elif choice == '2':
        target_phase = 'optimization'
    elif choice == '3':
        target_phase = 'production'
    elif choice == '4' or choice == '0':
        print(f"\n[INFO] Brak zmian")
        return
    else:
        print(f"\n[ERROR] Nieprawidlowy wybor")
        return
    
    # Confirm
    phase_info = PHASES[target_phase]
    print(f"\n[CONFIRM] Przelaczyc na faze: {target_phase.upper()}?")
    print(f"  {phase_info['description']}")
    print(f"  {phase_info['limits']}")
    
    try:
        confirm = input(f"\nPotwierdzenie (yes/no): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Anulowano")
        return
    
    if confirm != 'yes':
        print(f"\n[INFO] Anulowano")
        return
    
    # Switch
    if switch_phase(target_phase):
        print(f"\n[OK] Faza zmieniona na: {target_phase.upper()}")
        print(f"[INFO] Zrestartuj bota: run_bot.bat")
        print(f"[INFO] Sprawdz postep: python check_learning_progress.py")
    else:
        print(f"\n[ERROR] Nie udalo sie zmienic fazy")

if __name__ == '__main__':
    main()
