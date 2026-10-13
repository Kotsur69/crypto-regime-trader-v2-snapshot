#!/usr/bin/env python3
"""
Check available trading pairs on Binance Mainnet

Usage: python check_mainnet_pairs.py
"""
import requests
from typing import List, Dict

def get_mainnet_pairs() -> List[Dict]:
    """Get all available pairs from Binance Mainnet"""
    url = "https://api.binance.com/api/v3/exchangeInfo"
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
    """Check if our configured USDC pairs are available on Mainnet"""
    our_pairs_usdc = [
        'BTCUSDC', 'ETHUSDC', 'SOLUSDC', 'ADAUSDC',
        'AVAXUSDC', 'MATICUSDC', 'XRPUSDC', 'DOGEUSDC'
    ]
    
    print("\n" + "="*60)
    print("CHECKING BINANCE MAINNET PAIRS")
    print("="*60)
    
    print("\n[INFO] Fetching available pairs from Binance Mainnet...")
    all_pairs = get_mainnet_pairs()
    available_symbols = [p['symbol'] for p in all_pairs]
    
    print(f"\n[INFO] Total pairs available: {len(all_pairs)}")
    
    # Check USDC pairs (for mainnet production)
    print("\n" + "-"*60)
    print("USDC PAIRS (for Mainnet production):")
    print("-"*60)
    
    usdc_ok = True
    for pair in our_pairs_usdc:
        if pair in available_symbols:
            print(f"  [OK] {pair} - Available")
        else:
            print(f"  [ERROR] {pair} - NOT AVAILABLE!")
            usdc_ok = False
    
    # Check USDT pairs (alternative)
    print("\n" + "-"*60)
    print("USDT PAIRS (alternative):")
    print("-"*60)
    
    usdt_pairs = [p.replace('USDC', 'USDT') for p in our_pairs_usdc]
    for pair in usdt_pairs:
        if pair in available_symbols:
            print(f"  [OK] {pair} - Available")
        else:
            print(f"  [ERROR] {pair} - NOT AVAILABLE!")
    
    # Show all USDC pairs available
    print("\n" + "-"*60)
    print("ALL USDC PAIRS ON MAINNET:")
    print("-"*60)
    
    usdc_pairs_all = [p for p in all_pairs if p['quote'] == 'USDC']
    for pair in sorted(usdc_pairs_all, key=lambda x: x['symbol'])[:30]:
        print(f"  {pair['symbol']}")
    if len(usdc_pairs_all) > 30:
        print(f"  ... and {len(usdc_pairs_all) - 30} more")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY:")
    print(f"  Total USDC pairs: {len(usdc_pairs_all)}")
    print(f"  Total USDT pairs: {len([p for p in all_pairs if p['quote'] == 'USDT'])}")
    print("\n[INFO] Mainnet has both USDC and USDT pairs")
    print("[INFO] We use USDC for lower fees and better regulation")
    print("="*60 + "\n")
    
    return usdc_ok

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
