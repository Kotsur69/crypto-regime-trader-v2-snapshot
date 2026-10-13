#!/usr/bin/env python3
"""
Check complete bot status - everything in one place
Ultra-simple status checker for the trading bot.
"""
import os
import json
import sys
from datetime import datetime

def print_header(text):
    """Print formatted header"""
    print(f"\n{'='*70}")
    print(f"{text:^70}")
    print(f"{'='*70}\n")

def print_section(text):
    """Print section header"""
    print(f"\n{text}")
    print(f"{'-'*70}")

def check_bot_running():
    """Check if bot is running"""
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline and 'python' in str(cmdline[0]).lower():
                    cmd_str = ' '.join(str(c) for c in cmdline)
                    if 'main.py' in cmd_str:
                        return True, proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return False, None
    except ImportError:
        return None, "psutil not installed"

def get_current_phase():
    """Get current learning phase"""
    try:
        import yaml
        config_file = 'config_testnet.yaml'
        if not os.path.exists(config_file):
            config_file = 'config.yaml'
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        learning_config = config.get('learning_phase', {})
        return learning_config.get('phase', 'unknown')
    except ImportError:
        # Try without yaml
        return read_phase_from_file()
    except Exception as e:
        return f"error: {e}"

def read_phase_from_file():
    """Read phase directly from config file without yaml"""
    try:
        config_file = 'config_testnet.yaml'
        if not os.path.exists(config_file):
            config_file = 'config.yaml'
        
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Simple parsing
        for line in content.split('\n'):
            if 'phase:' in line and 'learning_phase' not in line:
                phase = line.split(':')[-1].strip().strip('"').strip("'")
                if phase in ['learning', 'optimization', 'production']:
                    return phase
        return 'unknown'
    except:
        return 'unknown'

def get_emergency_stop_status():
    """Get emergency stop status"""
    try:
        state_file = './data/risk_state.json'
        if not os.path.exists(state_file):
            return False, "Brak pliku stanu (pierwszy start?)"
        
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        emergency_active = state.get('emergency_stop_active', False)
        consecutive_losses = state.get('consecutive_losses', 0)
        
        return emergency_active, f"{consecutive_losses} strat z rzedu"
    except Exception as e:
        return None, f"error: {e}"

def get_positions():
    """Get open positions"""
    positions = {}
    
    # Try execution_state.json first
    try:
        state_file = './data/execution_state.json'
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            positions = state.get('positions', {})
    except:
        pass
    
    # Also try positions.json
    if not positions:
        try:
            positions_file = './data/positions.json'
            if os.path.exists(positions_file):
                with open(positions_file, 'r', encoding='utf-8') as f:
                    positions = json.load(f)
        except:
            pass
    
    return positions

def get_stats():
    """Get trading stats"""
    try:
        state_file = 'bot_state.json'
        if not os.path.exists(state_file):
            # Try data directory
            state_file = './data/bot_state.json'
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        return state
    except:
        return None

def get_learning_stats():
    """Get learning phase statistics"""
    try:
        stats_file = './data/learning_stats.json'
        if not os.path.exists(stats_file):
            return None
        
        with open(stats_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def get_daily_stats():
    """Get daily trading stats from risk state"""
    try:
        state_file = './data/risk_state.json'
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        return state.get('daily_stats', {})
    except:
        return None

def main():
    print_header("CRYPTO TRADING BOT - COMPLETE STATUS")
    print(f"Czas sprawdzenia: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. Current Phase
    print_section("1. AKTUALNY TRYB")
    phase = get_current_phase()
    phase_info = {
        'learning': ('[LEARN]', 'Faza uczenia sie - bardzo luzne limity', 'Cel: Zbieranie danych (50-100 tradow)'),
        'optimization': ('[OPTIM]', 'Faza optymalizacji - srednie limity', 'Cel: Optymalizacja strategii'),
        'production': ('[PROD]', 'Faza produkcyjna - scisle limity', 'Cel: Bezpieczny trading'),
        'unknown': ('[?]', 'Nieznany tryb', 'Sprawdz config_testnet.yaml')
    }
    
    info = phase_info.get(phase, phase_info['unknown'])
    print(f"  {info[0]} Tryb: {phase.upper()}")
    print(f"  [INFO] {info[1]}")
    print(f"  [INFO] {info[2]}")
    
    # 2. Bot Status
    print_section("2. STATUS BOTA")
    is_running, pid = check_bot_running()
    if is_running is None:
        print(f"  [?] Nie mozna sprawdzic (zainstaluj psutil: pip install psutil)")
    elif is_running:
        print(f"  [OK] Bot jest URUCHOMIONY (PID: {pid})")
        print(f"  [INFO] Zeby zatrzymac: Ctrl+C w oknie bota")
    else:
        print(f"  [X] Bot NIE jest uruchomiony")
        print(f"  [INFO] Zeby uruchomic: Kliknij run_bot.bat")
    
    # 3. Emergency Stop
    print_section("3. EMERGENCY STOP")
    emergency_active, info = get_emergency_stop_status()
    if emergency_active is None:
        print(f"  [?] Nie mozna sprawdzic statusu: {info}")
    elif emergency_active:
        print(f"  [ALERT] EMERGENCY STOP AKTYWNY!")
        print(f"  [INFO] {info}")
        print(f"  [INFO] Zeby wznowic: Kliknij resume_trading.bat")
    else:
        print(f"  [OK] Emergency stop nieaktywny")
        print(f"  [INFO] {info}")
    
    # 4. Open Positions
    print_section("4. OTWARTE POZYCJE")
    positions = get_positions()
    if not positions:
        print(f"  [INFO] Brak otwartych pozycji")
    else:
        for pair, pos in positions.items():
            if isinstance(pos, dict):
                side = pos.get('side', 'UNKNOWN')
                entry = pos.get('entry_price', 0)
                size = pos.get('size', pos.get('quantity', 0))
                pnl = pos.get('unrealized_pnl', 0)
                
                pnl_sign = '+' if pnl >= 0 else ''
                status = '[UP]' if pnl > 0 else '[DOWN]'
                print(f"  {status} {pair}: {side} @ {entry:.2f} (size: {size:.4f})")
                print(f"       PnL: {pnl_sign}{pnl:.2f} USDT")
    
    # 5. Daily Stats
    print_section("5. DZISIEJSZE STATYSTYKI")
    daily_stats = get_daily_stats()
    if daily_stats:
        pnl = daily_stats.get('pnl', 0)
        trades = daily_stats.get('trades', 0)
        wins = daily_stats.get('wins', 0)
        losses = daily_stats.get('losses', 0)
        
        print(f"  [STAT] Dzisiejszy PnL: {'+' if pnl >= 0 else ''}{pnl:.2f} USDT")
        print(f"  [STAT] Liczba tradow: {trades}")
        print(f"  [STAT] Wygrane: {wins} | Przegrane: {losses}")
        if trades > 0:
            win_rate = wins / trades * 100
            print(f"  [STAT] Win rate: {win_rate:.1f}%")
    else:
        print(f"  [INFO] Brak statystyk (bot nie byl uruchomiony)")
    
    # 6. Learning Progress (if in learning phase)
    if phase == 'learning':
        print_section("6. POSTEP NAUKI")
        learning_stats = get_learning_stats()
        if learning_stats:
            total_trades = learning_stats.get('total_trades', 0)
            target_trades = 100
            progress = min(100, (total_trades / target_trades) * 100)
            
            print(f"  [LEARN] Zebrane trady: {total_trades}/{target_trades}")
            print(f"  [LEARN] Postep: {progress:.0f}%")
            
            bar_filled = int(progress / 5)
            bar_empty = 20 - bar_filled
            progress_bar = '[' + '#' * bar_filled + '-' * bar_empty + ']'
            print(f"  {progress_bar}")
        else:
            print(f"  [INFO] Brak danych o nauce (bot jeszcze nie zbiera danych)")
    
    # 7. Quick Actions
    print_section("7. SZYBKIE AKCJE")
    print(f"  * Uruchom bota: run_bot.bat")
    print(f"  * Zmien tryb: switch_phase.bat")
    print(f"  * Postep uczenia: check_learning_progress.bat")
    print(f"  * Zamknij pozycje: close_position.bat")
    print(f"  * Wznow trading: resume_trading.bat")
    print(f"  * Dashboard: http://localhost:5000")
    
    # 8. Files
    print_section("8. WAZNE PLIKI")
    print(f"  * Konfiguracja: config_testnet.yaml")
    print(f"  * Logi: logs/bot.log")
    print(f"  * Stan ryzyka: ./data/risk_state.json")
    print(f"  * Pozycje: ./data/execution_state.json")
    
    print(f"\n{'='*70}\n")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Przerwano przez uzytkownika\n")
    except Exception as e:
        print(f"\n[ERROR] Blad: {e}\n")
        import traceback
        traceback.print_exc()
