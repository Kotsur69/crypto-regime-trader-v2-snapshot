#!/usr/bin/env python3
"""
Setup Mainnet - Interaktywny skrypt do konfiguracji Binance Mainnet

[WARNING] OSTRZEŻENIE: Ten skrypt konfiguruje PRAWDZIWY trading!
Upewnij się, że masz minimum 30 dni profitable paper tradingu.

Usage: python setup_mainnet.py
"""

import os
import sys
import yaml
import json
from datetime import datetime, timedelta

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
{Colors.RED}{'='*60}
    [RED] CRYPTO TRADING BOT - MAINNET SETUP
    [WARNING]  PRAWDZIWE PIENIĄDZE - PRAWDZIWE RYZYKO!
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

def require_confirmation(message, required_times=3):
    """Require multiple confirmations for critical actions"""
    print(f"\n{Colors.RED}{Colors.BOLD}{message}{Colors.END}")
    print(f"\n{Colors.YELLOW}Wpisz 'YES' {required_times} razy aby kontynuować:{Colors.END}")
    
    for i in range(required_times):
        response = input(f"  Potwierdzenie {i+1}/{required_times}: ").strip()
        if response != "YES":
            print_error("Anulowano. Wpisz dokładnie 'YES' (wielkimi literami).")
            return False
    return True

def check_paper_trading_history():
    """Check if paper trading was profitable"""
    history_path = './data/learning/trade_history.json'
    
    if not os.path.exists(history_path):
        return None, "Brak historii paper tradingu"
    
    try:
        with open(history_path, 'r') as f:
            data = json.load(f)
        
        trades = data.get('trades', [])
        if len(trades) < 50:
            return None, f"Za mało trade'ów ({len(trades)}/50 minimum)"
        
        # Calculate stats
        total_pnl = sum(t.get('pnl', 0) for t in trades)
        wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
        win_rate = wins / len(trades) * 100
        
        # Check dates
        if trades:
            first_trade = datetime.fromisoformat(trades[0].get('timestamp', '2020-01-01'))
            days_trading = (datetime.now() - first_trade).days
        else:
            days_trading = 0
        
        return {
            'total_trades': len(trades),
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'days_trading': days_trading,
            'profitable': total_pnl > 0 and win_rate > 50
        }, None
        
    except Exception as e:
        return None, f"Błąd odczytu historii: {e}"

def test_binance_connection(api_key, api_secret, testnet=False):
    """Test connection to Binance"""
    try:
        from binance.client import Client
        client = Client(api_key, api_secret, testnet=testnet)
        account = client.get_account()
        balances = {b['asset']: float(b['free']) for b in account['balances'] 
                   if float(b['free']) > 0}
        return True, balances
    except Exception as e:
        return False, str(e)

def main():
    print_header()
    
    print(f"""
{Colors.RED}{Colors.BOLD}[WARNING]  PRZECZYTAJ UWAŻNIE:{Colors.END}

Ten skrypt konfiguruje bota do PRAWDZIWEGO tradingu.
Będzie używał PRAWDZIWYCH pieniędzy.

Przed kontynuacją upewnij się, że:

[ ] Masz minimum 30 dni paper tradingu
[ ] Paper trading był PROFITABLE (zysk > 0)
[ ] Win rate > 55%
[ ] Max drawdown < 15%
[ ] Przeczytałeś SAFETY_CHECKLIST.md
[ ] Zaczynasz z MAŁYM kapitałem ($100-500)
[ ] Masz włączone Discord notifications
[ ] Rozumiesz, że możesz STRACIĆ cały kapitał
""")
    
    # First confirmation
    if not require_confirmation("CZY NA PEWNO CHCESZ SKONFIGUROWAĆ MAINNET?", 3):
        print("\nAnulowano. Wróć gdy będziesz gotowy.")
        sys.exit(0)
    
    # Step 1: Check paper trading history
    print_step(1, "Sprawdzanie historii paper tradingu")
    
    stats, error = check_paper_trading_history()
    
    if error:
        print_warning(error)
        print(f"\n{Colors.YELLOW}Nie można zweryfikować historii paper tradingu.{Colors.END}")
        if not require_confirmation("CZY KONTYNUOWAĆ BEZ WERYFIKACJI?", 2):
            sys.exit(0)
    else:
        print(f"\n{Colors.CYAN}Statystyki paper tradingu:{Colors.END}")
        print(f"  Trade'y: {stats['total_trades']}")
        print(f"  P&L: ${stats['total_pnl']:,.2f}")
        print(f"  Win rate: {stats['win_rate']:.1f}%")
        print(f"  Dni tradingu: {stats['days_trading']}")
        
        if not stats['profitable']:
            print_error("Paper trading NIE był profitable!")
            print(f"\n{Colors.RED}Zalecenie: Kontynuuj paper trading do osiągnięcia profitu.{Colors.END}")
            if not require_confirmation("CZY NA PEWNO CHCESZ KONTYNUOWAĆ MIMO STRAT?", 3):
                sys.exit(0)
        
        if stats['days_trading'] < 30:
            print_warning(f"Tylko {stats['days_trading']} dni tradingu (zalecane: 30+)")
            if not require_confirmation("CZY KONTYNUOWAĆ Z KRÓTSZYM OKRESEM TESTÓW?", 2):
                sys.exit(0)
    
    # Step 2: API Keys
    print_step(2, "Wprowadź klucze API (Binance MAINNET)")
    
    print(f"""
{Colors.YELLOW}WAŻNE - Uprawnienia API:{Colors.END}
[OK] Enable Reading
[OK] Enable Spot & Margin Trading  
[ERROR] Enable Withdrawals (NIGDY nie włączaj!)
[ERROR] Enable Futures

{Colors.YELLOW}KRYTYCZNE - IP Whitelist:{Colors.END}
Dodaj swój IP do whitelisty w ustawieniach API na Binance!
""")
    
    api_key = get_input("API Key")
    api_secret = get_input("API Secret")
    
    # Step 3: Test connection
    print_step(3, "Testowanie połączenia z Binance Mainnet...")
    
    success, result = test_binance_connection(api_key, api_secret, testnet=False)
    
    if not success:
        print_error(f"Nie można połączyć: {result}")
        sys.exit(1)
    
    print_success("Połączono z Binance Mainnet!")
    print(f"\n{Colors.CYAN}Twoje salda:{Colors.END}")
    
    usdc_balance = 0
    for asset, balance in result.items():
        print(f"  {asset}: {balance:,.4f}")
        if asset == 'USDC':
            usdc_balance = balance
    
    if usdc_balance < 100:
        print_warning(f"Masz tylko {usdc_balance:.2f} USDC. Zalecane minimum: $100")
    
    # Step 4: Configure capital
    print_step(4, "Konfiguracja kapitału")
    
    print(f"\n{Colors.YELLOW}ZALECENIE: Zacznij od MAŁEGO kapitału!{Colors.END}")
    print("Sugerowane: $100-500 na start")
    print("Zwiększaj stopniowo po profitable miesiącu")
    
    max_suggested = min(usdc_balance * 0.5, 500)  # Max 50% balance or $500
    total_capital = float(get_input(f"\nKapitał do tradingu (USDC)", str(int(max_suggested))))
    
    if total_capital > usdc_balance:
        print_error(f"Nie masz tyle USDC! (dostępne: {usdc_balance:.2f})")
        sys.exit(1)
    
    if total_capital > 1000:
        print_warning(f"Kapitał > $1000 na start jest ryzykowny!")
        if not require_confirmation("CZY NA PEWNO CHCESZ TAK DUŻEGO KAPITAŁU?", 2):
            sys.exit(0)
    
    # Step 5: Trading pairs (USDC for mainnet)
    print_step(5, "Konfiguracja par tradingowych (USDC)")
    
    print(f"\n{Colors.CYAN}[INFO] Binance Mainnet uzywa USDC (jak planowano){Colors.END}")
    print(f"{Colors.CYAN}[INFO] USDC ma lepsze fees i regulacje{Colors.END}")
    print(f"\n{Colors.YELLOW}ZALECENIE: Zacznij od 2-4 par na mainnet{Colors.END}")
    
    # USDC pairs for mainnet (lower fees, better regulation)
    default_pairs = ['BTCUSDC', 'ETHUSDC', 'SOLUSDC', 'ADAUSDC',
                    'AVAXUSDC', 'MATICUSDC', 'XRPUSDC', 'DOGEUSDC']
    suggested_pairs = ['BTCUSDC', 'ETHUSDC']  # Start with just 2 for safety
    print(f"Sugerowane pary (bezpieczne): {', '.join(suggested_pairs)}")
    print(f"Dostepne pary USDC: {', '.join(default_pairs)}")
    
    use_default = get_input("Uzyc sugerowanych par (BTCUSDC, ETHUSDC)? (y/n)", "y")
    
    if use_default.lower() == 'y':
        pairs = suggested_pairs  # Start with just 2 for safety
    else:
        print(f"Wszystkie dostepne pary USDC: {', '.join(default_pairs)}")
        pairs_input = get_input("Podaj pary (oddzielone przecinkami, np. BTCUSDC,ETHUSDC,SOLUSDC)")
        pairs = [p.strip().upper() for p in pairs_input.split(',')]
    
    capital_per_pair = total_capital / len(pairs)
    print(f"\n  Pary: {len(pairs)}")
    print(f"  Kapitał per para: ${capital_per_pair:,.2f}")
    
    # Step 6: Discord notifications
    print_step(6, "Discord Notifications (WYMAGANE dla mainnet!)")
    
    discord_webhook = get_input("Discord Webhook URL")
    
    if not discord_webhook or not discord_webhook.startswith("https://discord.com/api/webhooks/"):
        print_warning("Discord jest BARDZO zalecany dla mainnet!")
        skip_discord = get_input("Kontynuować bez Discord? (y/n)", "n")
        if skip_discord.lower() != 'y':
            sys.exit(0)
    
    # Step 7: Safety checklist
    print_step(7, "Checklist bezpieczeństwa")
    
    checklist = [
        "IP Whitelist jest włączony na Binance",
        "Withdrawals są WYŁĄCZONE w API",
        "Mam backup kluczy API",
        "Emergency stop jest skonfigurowany",
        "Rozumiem, że mogę stracić cały kapitał",
        "Będę monitorować bota przez pierwsze 2 tygodnie"
    ]
    
    print(f"\n{Colors.YELLOW}Potwierdź każdy punkt:{Colors.END}\n")
    
    for i, item in enumerate(checklist, 1):
        response = get_input(f"  {i}. {item} (y/n)")
        if response.lower() != 'y':
            print_error(f"Musisz potwierdzić wszystkie punkty!")
            sys.exit(1)
    
    # Step 8: Create config file
    print_step(8, "Tworzenie pliku konfiguracyjnego")
    
    # Load base config
    base_config_path = 'config.yaml'
    if os.path.exists(base_config_path):
        with open(base_config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        print_error("Nie znaleziono config.yaml")
        sys.exit(1)
    
    # Update config for mainnet
    config['binance']['api_key'] = api_key
    config['binance']['api_secret'] = api_secret
    config['binance']['testnet'] = False
    
    config['trading']['pairs'] = pairs
    config['trading']['initial_capital_per_pair'] = int(capital_per_pair)
    
    config['paper_trading']['enabled'] = False
    config['safety']['force_testnet_only'] = False
    
    # More conservative settings for mainnet
    config['safety']['max_order_value'] = min(capital_per_pair * 0.5, 500)
    config['safety']['emergency_stop']['daily_loss_pct'] = 5
    config['safety']['emergency_stop']['consecutive_losses'] = 3
    
    config['risk']['max_risk_per_trade_pct'] = 1.5  # More conservative
    config['risk']['max_daily_drawdown_pct'] = 3    # More conservative
    
    if discord_webhook:
        config['discord']['enabled'] = True
        config['discord']['webhook_url'] = discord_webhook
        config['discord']['mention_on_emergency'] = "@everyone"
    
    # Save config
    output_path = 'config_mainnet.yaml'
    
    # Backup if exists
    if os.path.exists(output_path):
        backup_path = f"{output_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.rename(output_path, backup_path)
        print_success(f"Backup poprzedniej konfiguracji: {backup_path}")
    
    with open(output_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    print_success(f"Konfiguracja zapisana: {output_path}")
    
    # Final summary
    print(f"\n{'='*60}")
    print(f"""
{Colors.GREEN}{Colors.BOLD}
[OK] MAINNET CONFIGURED (START SMALL!)
{Colors.END}
{Colors.RED}{Colors.BOLD}[WARNING]  PAMIĘTAJ:{Colors.END}
- To są PRAWDZIWE pieniądze
- Możesz STRACIĆ cały kapitał
- Monitoruj bota przez pierwsze 2 tygodnie
- Zwiększaj kapitał STOPNIOWO

{Colors.CYAN}Uruchom bota komendą:{Colors.END}

  # Najpierw dry-run (bez trade'ów)
  python main.py --config config_mainnet.yaml --dry-run

  # Jeśli wszystko OK, uruchom normalnie
  python main.py --config config_mainnet.yaml --dashboard

{Colors.YELLOW}Harmonogram monitoringu:{Colors.END}
  Dzień 1-3:   Sprawdzaj co 2-4 godziny
  Dzień 4-7:   Sprawdzaj 3x dziennie
  Tydzień 2:   Sprawdzaj 2x dziennie
  Potem:       Rano i wieczorem

{Colors.RED}W razie problemów:{Colors.END}
  pkill -f "main.py"  # Emergency stop
""")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
