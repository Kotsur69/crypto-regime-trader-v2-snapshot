#!/usr/bin/env python3
"""
Close specific position on Binance Testnet
"""
import sys
import yaml
import json
import os

def close_position(pair: str):
    """Close position for specific pair"""
    print(f"\n{'='*60}")
    print(f"CLOSING POSITION: {pair}")
    print(f"{'='*60}\n")
    
    # Load state file
    state_file = './data/execution_state.json'
    
    if not os.path.exists(state_file):
        print(f"[ERROR] Brak pliku state: {state_file}")
        return
    
    with open(state_file, 'r') as f:
        state = json.load(f)
    
    positions = state.get('positions', {})
    
    if pair not in positions:
        print(f"[INFO] Brak otwartej pozycji dla {pair}")
        print(f"[INFO] Dostepne pozycje: {list(positions.keys())}")
        return
    
    position = positions[pair]
    
    print(f"[INFO] Znaleziono pozycje:")
    print(f"  Pair: {pair}")
    print(f"  Side: {position.get('side')}")
    print(f"  Entry: {position.get('entry_price')}")
    print(f"  Size: {position.get('quantity')}")
    print(f"  PnL: {position.get('unrealized_pnl', 0):.2f} USDT")
    
    # Confirm
    confirm = input(f"\nCzy na pewno zamknac pozycje {pair}? (yes/no): ")
    if confirm.lower() != 'yes':
        print("[INFO] Anulowano")
        return
    
    # Remove position from state
    del positions[pair]
    state['positions'] = positions
    
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)
    
    print(f"\n[OK] Pozycja {pair} zamknieta!")
    print(f"[INFO] State zapisany do {state_file}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python close_position.py <PAIR>")
        print("Example: python close_position.py SOLUSDT")
        
        # Show current positions
        state_file = './data/execution_state.json'
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                state = json.load(f)
            positions = state.get('positions', {})
            if positions:
                print(f"\nAktualne pozycje: {list(positions.keys())}")
        sys.exit(1)
    
    pair = sys.argv[1].upper()
    close_position(pair)
