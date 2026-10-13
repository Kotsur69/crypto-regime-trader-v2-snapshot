#!/usr/bin/env python3
"""
Close all positions on Binance Testnet
"""
import yaml
import json
import os

def close_all_positions():
    """Close all open positions"""
    print(f"\n{'='*60}")
    print(f"CLOSING ALL POSITIONS")
    print(f"{'='*60}\n")
    
    # Load state file
    state_file = './data/execution_state.json'
    
    if not os.path.exists(state_file):
        print(f"[ERROR] Brak pliku state: {state_file}")
        return
    
    with open(state_file, 'r') as f:
        state = json.load(f)
    
    positions = state.get('positions', {})
    
    if not positions:
        print("[INFO] Brak otwartych pozycji")
        return
    
    print(f"[INFO] Znaleziono {len(positions)} pozycji:\n")
    for pair, position in positions.items():
        print(f"  {pair}:")
        print(f"    Side: {position.get('side')}")
        print(f"    Entry: {position.get('entry_price')}")
        print(f"    Size: {position.get('quantity')}")
        print(f"    PnL: {position.get('unrealized_pnl', 0):.2f} USDT")
        print()
    
    # Confirm
    confirm = input(f"Czy na pewno zamknac WSZYSTKIE pozycje? (yes/no): ")
    if confirm.lower() != 'yes':
        print("[INFO] Anulowano")
        return
    
    # Clear all positions
    closed_pairs = list(positions.keys())
    state['positions'] = {}
    
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)
    
    print(f"\n[OK] Zamknieto {len(closed_pairs)} pozycji:")
    for pair in closed_pairs:
        print(f"  - {pair}")
    print(f"\n[INFO] State zapisany do {state_file}")

if __name__ == '__main__':
    close_all_positions()
