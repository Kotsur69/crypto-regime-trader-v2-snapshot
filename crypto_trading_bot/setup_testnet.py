#!/usr/bin/env python3
"""
Setup Testnet - Interaktywny skrypt do konfiguracji Binance Testnet

Usage: python setup_testnet.py
"""

import os
import sys
import yaml
import shutil
from datetime import datetime

# Kolory dla terminala
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header():
    print(f"""
{Colors.CYAN}{'='*60}
    [TEST] CRYPTO TRADING BOT - TESTNET SETUP
{'='*60}{Colors.END}
""")

def print_step(num, text):
    print(f"\n{Colors.BLUE}[Step {num}]{Colors.END} {Colors.BOLD}{text}{Colors.END}")

def print_success(text):
    print(f"{Colors.GREEN}[OK] {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}[WARN] {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}[X] {text}{Colors.END}")

def get_input(prompt, default=None):
    if default:
        result = input(f"{prompt} [{default}]: ").strip()
        return result if result else default
    return input(f"{prompt}: ").strip()

def validate_api_key(api_key):
    """Basic validation of API key format"""
    if not api_key or len(api_key) < 20:
        return False
    return True

def test_binance_connection(api_key, api_secret):
    """Test connection to Binance Testnet"""
    try:
        from binance.client import Client
        client = Client(api_key, api_secret, testnet=True)
        account = client.get_account()
        balances = {b['asset']: float(b['free']) for b in account['balances'] 
                   if float(b['free']) > 0}
        return True, balances
    except Exception as e:
        return False, str(e)

def main():
    print_header()
    
    print(f"""
{Colors.CYAN}Ten skrypt pomoże Ci skonfigurować bota do paper tradingu
na Binance Testnet (wirtualne środki, bez ryzyka).{Colors.END}

Przed rozpoczęciem upewnij się, że:
1. Masz konto GitHub
2. Zalogowałeś się na https://testnet.binance.vision/
3. Wygenerowałeś API keys (HMAC_SHA256)
""")
    
    input(f"\n{Colors.BOLD}Naciśnij ENTER aby kontynuować...{Colors.END}")
    
    # Step 1: API Keys
    print_step(1, "Wprowadź klucze API (Binance Testnet)")
    print(f"\n{Colors.YELLOW}Uzyskaj klucze z: https://testnet.binance.vision/{Colors.END}")
    
    api_key = get_input("\nAPI Key")
    if not validate_api_key(api_key):
        print_error("API Key wygląda niepoprawnie. Sprawdź i spróbuj ponownie.")
        sys.exit(1)
    
    api_secret = get_input("API Secret")
    if not validate_api_key(api_secret):
        print_error("API Secret wygląda niepoprawnie. Sprawdź i spróbuj ponownie.")
        sys.exit(1)
    
    # Step 2: Test connection
    print_step(2, "Testowanie połączenia z Binance Testnet...")
    
    success, result = test_binance_connection(api_key, api_secret)
    
    if not success:
        print_error(f"Nie można połączyć z Binance Testnet: {result}")
        print(f"\n{Colors.YELLOW}Sprawdź:{Colors.END}")
        print("1. Czy klucze są poprawne")
        print("2. Czy masz połączenie z internetem")
        print("3. Czy używasz kluczy TESTNET (nie mainnet!)")
        sys.exit(1)
    
    print_success("Połączono z Binance Testnet!")
    print(f"\n{Colors.CYAN}Twoje salda testowe:{Colors.END}")
    for asset, balance in result.items():
        print(f"  {asset}: {balance:,.2f}")
    
    # INFO: Binance Testnet uses USDT (not USDC)
    print(f"\n{Colors.CYAN}[INFO] Binance Testnet uzywa USDT (nie USDC){Colors.END}")
    print(f"{Colors.CYAN}[INFO] Mainnet bedzie uzywal USDC jak planowano{Colors.END}")
    
    if 'USDT' not in result or result.get('USDT', 0) < 1000:
        print_warning("Masz malo USDT. Doladuj na https://testnet.binance.vision/")
    
    # Step 3: Trading pairs (USDT for testnet!)
    print_step(3, "Konfiguracja par tradingowych (USDT)")
    
    # IMPORTANT: Testnet uses USDT, not USDC!
    default_pairs = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 
                    'AVAXUSDT', 'MATICUSDT', 'XRPUSDT', 'DOGEUSDT']
    
    print(f"\nDomyslne pary (USDT): {', '.join(default_pairs)}")
    use_default = get_input("Uzyc domyslnych par? (y/n)", "y")
    
    if use_default.lower() == 'y':
        pairs = default_pairs
    else:
        pairs_input = get_input("Podaj pary (oddzielone przecinkami, np. BTCUSDT,ETHUSDT)")
        pairs = [p.strip().upper() for p in pairs_input.split(',')]
    
    # Step 4: Capital (USDT for testnet)
    print_step(4, "Konfiguracja kapitalu (USDT)")
    
    total_capital = float(get_input("Calkowity kapital testowy (USDT)", "40000"))
    capital_per_pair = total_capital / len(pairs)
    
    print(f"\n  Pary: {len(pairs)}")
    print(f"  Kapital per para: {capital_per_pair:,.0f} USDT")
    
    # Step 5: Discord (optional)
    print_step(5, "Powiadomienia Discord (opcjonalne)")
    
    discord_enabled = get_input("Włączyć Discord notifications? (y/n)", "n")
    discord_webhook = ""
    
    if discord_enabled.lower() == 'y':
        discord_webhook = get_input("Discord Webhook URL")
        if not discord_webhook.startswith("https://discord.com/api/webhooks/"):
            print_warning("Webhook URL wygląda niepoprawnie, ale kontynuuję...")
    
    # Step 6: Create config file
    print_step(6, "Tworzenie pliku konfiguracyjnego")
    
    # Load base config
    base_config_path = 'config.yaml'
    if os.path.exists(base_config_path):
        with open(base_config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        print_error("Nie znaleziono config.yaml")
        sys.exit(1)
    
    # Update config
    config['binance']['api_key'] = api_key
    config['binance']['api_secret'] = api_secret
    config['binance']['testnet'] = True
    
    config['trading']['pairs'] = pairs
    config['trading']['initial_capital_per_pair'] = int(capital_per_pair)
    
    config['paper_trading']['enabled'] = True
    config['safety']['force_testnet_only'] = True
    
    if discord_webhook:
        config['discord']['enabled'] = True
        config['discord']['webhook_url'] = discord_webhook
    
    # Save config
    output_path = 'config_testnet.yaml'
    with open(output_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    print_success(f"Konfiguracja zapisana: {output_path}")
    
    # Step 7: Test all modules
    print_step(7, "Testowanie modułów...")
    
    modules_ok = True
    
    try:
        from data_fetcher import DataFetcher
        print_success("data_fetcher")
    except Exception as e:
        print_error(f"data_fetcher: {e}")
        modules_ok = False
    
    try:
        from indicators import TechnicalIndicators
        print_success("indicators")
    except Exception as e:
        print_error(f"indicators: {e}")
        modules_ok = False
    
    try:
        from pattern_analyzer import PatternAnalyzer
        print_success("pattern_analyzer")
    except Exception as e:
        print_error(f"pattern_analyzer: {e}")
        modules_ok = False
    
    try:
        from decision_engine import DecisionEngine
        print_success("decision_engine")
    except Exception as e:
        print_error(f"decision_engine: {e}")
        modules_ok = False
    
    try:
        from risk_manager import RiskManager
        print_success("risk_manager")
    except Exception as e:
        print_error(f"risk_manager: {e}")
        modules_ok = False
    
    # Final summary
    print(f"\n{'='*60}")
    
    if modules_ok:
        print(f"""
{Colors.GREEN}{Colors.BOLD}
[OK] TESTNET READY TO GO!
{Colors.END}
{Colors.CYAN}Uruchom bota komendą:{Colors.END}

  python main.py --config config_testnet.yaml

{Colors.CYAN}Z dashboardem:{Colors.END}

  python main.py --config config_testnet.yaml --dashboard

{Colors.YELLOW}Następne kroki:{Colors.END}
1. Uruchom bota
2. Otwórz dashboard: http://localhost:5000
3. Obserwuj trade'y przez min. 30 dni
4. Sprawdź SAFETY_CHECKLIST.md przed live trading
""")
    else:
        print(f"""
{Colors.YELLOW}[WARN] Niektóre moduły mają problemy.{Colors.END}
Sprawdź czy wszystkie zależności są zainstalowane:
  pip install -r requirements.txt
""")
    
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
