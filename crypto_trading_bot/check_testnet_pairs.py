#!/usr/bin/env python3
"""
Check available trading pairs on Binance Testnet

Usage: python check_testnet_pairs.py
"""
import requests
from typing import List, Dict

def get_testnet_pairs() -> List[Dict]:
    """Get all available pairs from Binance Testnet"""
    url = "https://testnet.binance.vision/api/v3/exchangeInfo"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    
    pairs = []
    for symbol in data['symbols']:
        if symbol['status'] == 'TRADING':
            pairs.append({
                'symbol': symbol['symbol'],
                'base': symbol['baseAsset'],
                'quote': symbol['quoteAsset'],
                'status': symbol['status']
            })
    
    return pairs

def check_our_pairs():
    """Check if our configured pairs are available"""
    our_pairs = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT',
        'AVAXUSDT', 'MATICUSDT', 'XRPUSDT', 'DOGEUSDT'
    ]
    
    print("\n" + "="*60)
    print("CHECKING BINANCE TESTNET PAIRS")
    print("="*60)
    
    print("\n[INFO] Fetching available pairs from Binance Testnet...")
    all_pairs = get_testnet_pairs()
    available_symbols = [p['symbol'] for p in all_pairs]
    
    print(f"\n[INFO] Total pairs available: {len(all_pairs)}")
    
    print("\n" + "-"*60)
    print("OUR CONFIGURED PAIRS (USDT):")
    print("-"*60)
    
    all_ok = True
    for pair in our_pairs:
        if pair in available_symbols:
            print(f"  [OK] {pair} - Available")
        else:
            print(f"  [ERROR] {pair} - NOT AVAILABLE!")
            all_ok = False
    
    # Check USDC pairs (should NOT exist on testnet)
    print("\n" + "-"*60)
    print("USDC PAIRS (should NOT exist on testnet):")
    print("-"*60)
    
    usdc_pairs = [p.replace('USDT', 'USDC') for p in our_pairs]
    for pair in usdc_pairs:
        if pair in available_symbols:
            print(f"  [SURPRISE] {pair} - Available!")
        else:
            print(f"  [EXPECTED] {pair} - Not available (this is normal)")
    
    # Show all USDT pairs
    print("\n" + "-"*60)
    print("ALL USDT PAIRS ON TESTNET:")
    print("-"*60)
    
    usdt_pairs = [p for p in all_pairs if p['quote'] == 'USDT']
    for pair in sorted(usdt_pairs, key=lambda x: x['symbol']):
        print(f"  {pair['symbol']}")
    
    # Summary
    print("\n" + "="*60)
    if all_ok:
        print("[OK] All configured pairs are available on Testnet!")
    else:
        print("[WARN] Some pairs are NOT available. Check config.")
    print("="*60 + "\n")
    
    return all_ok

if __name__ == '__main__':
    try:
        check_our_pairs()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 451:
            print(f"\n[ERROR] Binance API returned 451 (Unavailable For Legal Reasons)")
            print("[INFO] This might be due to geographic restrictions")
            print("[INFO] Try using a VPN or running from a different region")
        else:
            print(f"\n[ERROR] HTTP error: {e}")
    except requests.exceptions.RequestException as e:
        print(f"\n[ERROR] Failed to check pairs: {e}")
        print("[INFO] Make sure you have internet connection")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
