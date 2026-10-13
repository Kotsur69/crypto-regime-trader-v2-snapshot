#!/usr/bin/env python3
"""
test_vwap.py - Skrypt testowy dla modułu VWAP

Ten skrypt testuje:
1. Obliczanie VWAP dla różnych sesji
2. Pozycję ceny względem VWAP
3. Wizualizację VWAP na wykresie
4. Pattern VWAP_BOUNCE

Użycie:
    python test_vwap.py
"""

import sys
import yaml
import logging
from datetime import datetime
import pandas as pd
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Ładuje konfigurację"""
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("[ERROR] Brak pliku config.yaml")
        sys.exit(1)


def test_vwap_calculation(config: dict) -> pd.DataFrame:
    """Testuje obliczanie VWAP"""
    print("\n" + "="*60)
    print("[INFO] TEST: VWAP Calculation")
    print("="*60)
    
    try:
        from data_fetcher import DataFetcher
        from indicators import TechnicalIndicators
        
        # Pobierz dane
        print("\n[SYNC] Pobieranie danych...")
        fetcher = DataFetcher(config)
        df = fetcher.get_klines('BTCUSDC', '15m', limit=200)
        
        if df.empty:
            print("[ERROR] Brak danych")
            return pd.DataFrame()
        
        print(f"[OK] Pobrano {len(df)} świec")
        print(f"   Zakres: {df.index[0]} - {df.index[-1]}")
        
        # Oblicz wskaźniki (włącznie z VWAP)
        print("\n[SYNC] Obliczanie wskaźników i VWAP...")
        indicators = TechnicalIndicators(config)
        df = indicators.calculate_all(df)
        
        # Dodaj VWAP
        df = indicators.add_vwap(df, config)
        
        # Podsumowanie VWAP
        print("\n[OK] VWAP obliczone:")
        
        vwap_cols = [col for col in df.columns if col.startswith('vwap_')]
        last = df.iloc[-1]
        
        for col in vwap_cols:
            session_name = col.replace('vwap_', '')
            vwap_value = last[col]
            if not np.isnan(vwap_value):
                position = indicators.vwap_position(last['close'], vwap_value)
                print(f"   {session_name.upper():12} VWAP: {vwap_value:.2f}")
                print(f"                   Position: {position['position']} ({position['distance_pct']:.2f}%)")
        
        # Current session
        current_session = indicators.get_current_session()
        print(f"\n   [TIME] Current session: {current_session.upper()}")
        print(f"   [$] Current price: {last['close']:.2f}")
        
        return df
        
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def test_vwap_summary(config: dict, df: pd.DataFrame) -> None:
    """Testuje podsumowanie VWAP"""
    print("\n" + "="*60)
    print("[CLIPBOARD] TEST: VWAP Summary")
    print("="*60)
    
    if df.empty:
        print("\n[WARNING] Brak danych")
        return
    
    try:
        from indicators import TechnicalIndicators
        
        indicators = TechnicalIndicators(config)
        summary = indicators.get_vwap_summary(df)
        
        print("\n[INFO] VWAP Summary:")
        for key, value in summary.items():
            if isinstance(value, float):
                print(f"   {key}: {value:.4f}")
            elif isinstance(value, dict):
                print(f"   {key}:")
                for k, v in value.items():
                    print(f"      {k}: {v}")
            else:
                print(f"   {key}: {value}")
                
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")


def test_vwap_pattern(config: dict, df: pd.DataFrame) -> None:
    """Testuje wykrywanie VWAP_BOUNCE pattern"""
    print("\n" + "="*60)
    print("[SCAN] TEST: VWAP Bounce Pattern")
    print("="*60)
    
    if df.empty:
        print("\n[WARNING] Brak danych")
        return
    
    try:
        from pattern_analyzer import PatternAnalyzer, PatternType
        
        analyzer = PatternAnalyzer(config)
        
        print("\n[SYNC] Analizuję patterny...")
        patterns = analyzer.analyze(df, 'BTCUSDC')
        
        vwap_patterns = [p for p in patterns if 'VWAP' in p.pattern_type.value]
        
        if vwap_patterns:
            print(f"\n[OK] Znaleziono {len(vwap_patterns)} VWAP patternów:")
            for pattern in vwap_patterns:
                print(f"\n   [UP] {pattern.pattern_type.value}")
                print(f"      Direction: {pattern.direction}")
                print(f"      Confidence: {pattern.confidence}%")
                print(f"      Entry: {pattern.entry_price:.2f}")
                print(f"      SL: {pattern.stop_loss:.2f}")
                print(f"      TP: {pattern.take_profit:.2f}")
                print(f"      Supporting: {', '.join(pattern.supporting_factors[:3])}")
        else:
            print("\n[WARNING] Brak VWAP patternów w aktualnych danych")
            print("   (VWAP bounce wymaga ceny blisko VWAP + wysokiego volume)")
        
        # Wszystkie patterny
        print(f"\n[INFO] Wszystkie wykryte patterny ({len(patterns)}):")
        for pattern in patterns:
            vwap_indicator = " [VWAP]" if 'VWAP' in pattern.pattern_type.value else ""
            print(f"   - {pattern.pattern_type.value}{vwap_indicator}: {pattern.confidence:.0f}%")
            
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")
        import traceback
        traceback.print_exc()


def test_vwap_visualization(config: dict, df: pd.DataFrame) -> None:
    """Testuje wizualizację VWAP"""
    print("\n" + "="*60)
    print("[UP] TEST: VWAP Visualization")
    print("="*60)
    
    if df.empty:
        print("\n[WARNING] Brak danych")
        return
    
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        
        # Użyj ostatnich 100 świec
        df_plot = df.tail(100).copy()
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), 
                                        gridspec_kw={'height_ratios': [3, 1]})
        
        # Wykres ceny
        ax1.plot(df_plot.index, df_plot['close'], 'b-', linewidth=1.5, label='Price')
        
        # VWAP lines
        vwap_colors = {
            'asian': '#FFD700',      # Żółty
            'european': '#1E90FF',   # Niebieski
            'us': '#32CD32',         # Zielony
            'daily': '#FF4500'       # Czerwony
        }
        
        for session, color in vwap_colors.items():
            col = f'vwap_{session}'
            if col in df_plot.columns:
                ax1.plot(df_plot.index, df_plot[col], 
                        color=color, linewidth=1.5, linestyle='--',
                        label=f'VWAP {session.capitalize()}')
        
        ax1.set_title('BTCUSDC with Session VWAPs', fontsize=14)
        ax1.set_ylabel('Price (USDC)')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # Wykres volume
        colors = ['green' if c > o else 'red' 
                  for c, o in zip(df_plot['close'], df_plot['open'])]
        ax2.bar(df_plot.index, df_plot['volume'], color=colors, alpha=0.7)
        
        if 'volume_ma' in df_plot.columns:
            ax2.plot(df_plot.index, df_plot['volume_ma'], 'orange', 
                    linewidth=1.5, label='Volume MA')
        
        ax2.set_ylabel('Volume')
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        
        # Formatowanie osi X
        for ax in [ax1, ax2]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
        
        plt.tight_layout()
        
        # Zapisz wykres
        output_path = './reports/vwap_visualization.png'
        import os
        os.makedirs('./reports', exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        
        print(f"\n[OK] Wykres zapisany: {output_path}")
        print("\n[INFO] Legenda:")
        print("   [YELLOW] Żółty: VWAP Asian (00:00 UTC)")
        print("   [BLUE] Niebieski: VWAP European (09:00 UTC)")
        print("   [GREEN] Zielony: VWAP US (15:30 UTC)")
        print("   [RED] Czerwony: VWAP Daily")
        
        plt.close()
        
    except ImportError:
        print("\n[WARNING] matplotlib nie zainstalowany")
        print("   Zainstaluj: pip install matplotlib")
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")
        import traceback
        traceback.print_exc()


def test_session_detection() -> None:
    """Testuje wykrywanie aktualnej sesji"""
    print("\n" + "="*60)
    print("[TIME] TEST: Session Detection")
    print("="*60)
    
    from datetime import datetime, timezone
    from indicators import TechnicalIndicators
    
    # Create minimal config
    indicators = TechnicalIndicators({'indicators': {}})
    
    current = indicators.get_current_session()
    now = datetime.now(timezone.utc)
    
    print(f"\n   Current UTC time: {now.strftime('%H:%M')}")
    print(f"   Current session: {current.upper()}")
    
    print("\n   Session boundaries (UTC):")
    print("   [ASIA] Asian:    00:00 - 09:00")
    print("   [EU] European: 09:00 - 15:30")
    print("   [US] US:       15:30 - 22:00")
    print("   [NIGHT] Night:    22:00 - 00:00 (Asian pre-market)")


def main():
    """Main test function"""
    print("\n" + "#"*60)
    print("#  CRYPTO TRADING BOT - VWAP TEST SUITE")
    print("#"*60)
    print(f"\n[TIME] Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load config
    config = load_config()
    
    # Ensure VWAP is enabled
    if 'vwap' not in config:
        config['vwap'] = {
            'enabled': True,
            'sessions': {
                'asian': '00:00',
                'european': '09:00',
                'us': '15:30'
            },
            'use_in_breakouts': True,
            'bounce_pattern_enabled': True
        }
    
    # 1. Test Session Detection
    test_session_detection()
    
    # 2. Test VWAP Calculation
    df = test_vwap_calculation(config)
    
    # 3. Test VWAP Summary
    test_vwap_summary(config, df)
    
    # 4. Test VWAP Pattern
    test_vwap_pattern(config, df)
    
    # 5. Test Visualization
    test_vwap_visualization(config, df)
    
    # Summary
    print("\n" + "="*60)
    print("[CLIPBOARD] PODSUMOWANIE")
    print("="*60)
    print(f"\n   VWAP Calculation: {'[OK] OK' if not df.empty else '[ERROR] Failed'}")
    print(f"   Session Detection: [OK] OK")
    print(f"   Visualization: Sprawdź ./reports/vwap_visualization.png")
    print(f"\n[TIME] Koniec: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
