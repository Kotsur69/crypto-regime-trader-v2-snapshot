#!/usr/bin/env python3
"""
test_llm.py - Skrypt testowy dla modułu LLM Sentiment Analysis

Ten skrypt testuje:
1. Połączenie z LM Studio
2. Pobieranie newsów
3. Analizę sentymentu
4. Daily briefing
5. Emergency detection
6. Trade explanation

Wymagania:
- LM Studio uruchomione na localhost:1234
- Model Llama 3 8B (lub inny) załadowany

Użycie:
    python test_llm.py
"""

import sys
import yaml
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_news_fetcher(config: dict) -> list:
    """Testuje NewsFetcher"""
    print("\n" + "="*60)
    print("[NEWS] TEST: News Fetcher")
    print("="*60)
    
    try:
        from news_fetcher import NewsFetcher
        
        fetcher = NewsFetcher(config)
        
        # Pobierz newsy
        print("\n[SYNC] Pobieranie newsów...")
        news = fetcher.get_latest_news(hours=24)
        
        print(f"[OK] Znaleziono {len(news)} newsów")
        
        if news:
            print("\n[CLIPBOARD] Ostatnie 5 newsów:")
            for i, item in enumerate(news[:5], 1):
                print(f"\n  {i}. [{item.importance.name}] {item.source.value}")
                print(f"     [DATE] {item.published_at}")
                print(f"     [$] {', '.join(item.currencies)}")
                print(f"     [LOG] {item.title[:70]}...")
        
        # Stats
        stats = fetcher.get_stats()
        print(f"\n[INFO] Statystyki:")
        print(f"   Total cached: {stats['total_cached']}")
        print(f"   Last 24h: {stats['last_24h']}")
        print(f"   By source: {stats['by_source']}")
        
        return news
        
    except ImportError as e:
        print(f"[ERROR] Brak wymaganych modułów: {e}")
        print("   Zainstaluj: pip install feedparser requests")
        return []
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")
        return []


def test_llm_connection(config: dict) -> bool:
    """Testuje połączenie z LM Studio"""
    print("\n" + "="*60)
    print("[BOT] TEST: LLM Connection")
    print("="*60)
    
    try:
        from llm_sentiment import LLMSentimentAnalyzer
        
        analyzer = LLMSentimentAnalyzer(config)
        
        print(f"\n[SIGNAL] Provider: {config.get('llm', {}).get('provider', 'lm_studio')}")
        print(f"   Base URL: {config.get('llm', {}).get('base_url', 'http://localhost:1234/v1')}")
        print(f"   Model: {config.get('llm', {}).get('model', 'llama3:8b')}")
        
        # Test połączenia
        is_available = analyzer.is_available()
        
        if is_available:
            print("\n[OK] LLM jest dostępny!")
            return True
        else:
            print("\n[ERROR] LLM niedostępny")
            print("\n[TIP] Sprawdź czy:")
            print("   1. LM Studio jest uruchomione")
            print("   2. Model jest załadowany")
            print("   3. Server nasłuchuje na localhost:1234")
            return False
            
    except ImportError as e:
        print(f"[ERROR] Brak wymaganych modułów: {e}")
        print("   Zainstaluj: pip install openai")
        return False
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")
        return False


def test_sentiment_analysis(config: dict, news: list) -> None:
    """Testuje analizę sentymentu"""
    print("\n" + "="*60)
    print("[INFO] TEST: Sentiment Analysis")
    print("="*60)
    
    if not news:
        print("\n[WARNING] Brak newsów do analizy - używam fallback")
    
    try:
        from llm_sentiment import LLMSentimentAnalyzer
        
        analyzer = LLMSentimentAnalyzer(config)
        
        print("\n[SYNC] Analizuję sentiment...")
        sentiment = analyzer.analyze_news(news)
        
        if sentiment:
            print(f"\n[OK] Wynik analizy:")
            print(f"   Score: {sentiment.score:.2f} (-1.0 do +1.0)")
            print(f"   Confidence: {sentiment.confidence:.2f}")
            print(f"   Emergency: {sentiment.is_emergency}")
            print(f"   Reasoning: {sentiment.reasoning}")
            print(f"   Key factors: {sentiment.key_factors}")
            
            # Interpretacja
            if sentiment.score > 0.6:
                interpretation = "[GREEN] BARDZO BULLISH"
            elif sentiment.score > 0.3:
                interpretation = "[GREEN] BULLISH"
            elif sentiment.score > -0.3:
                interpretation = "[YELLOW] NEUTRAL"
            elif sentiment.score > -0.6:
                interpretation = "[RED] BEARISH"
            else:
                interpretation = "[RED] BARDZO BEARISH"
            
            print(f"\n   Interpretacja: {interpretation}")
        else:
            print("\n[WARNING] Brak wyniku analizy")
            
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")


def test_daily_briefing(config: dict, news: list) -> None:
    """Testuje daily briefing"""
    print("\n" + "="*60)
    print("[LOG] TEST: Daily Briefing")
    print("="*60)
    
    if not news:
        print("\n[WARNING] Brak newsów - pomijam test")
        return
    
    try:
        from llm_sentiment import LLMSentimentAnalyzer
        
        analyzer = LLMSentimentAnalyzer(config)
        
        if not analyzer.is_available():
            print("\n[WARNING] LLM niedostępny - pomijam test")
            return
        
        print("\n[SYNC] Generuję daily briefing...")
        print("   (to może potrwać 30-60 sekund)")
        
        briefing = analyzer.daily_briefing(news)
        
        if briefing:
            print(f"\n[OK] Daily Briefing:")
            print(f"   [DATE] Data: {briefing.date.strftime('%Y-%m-%d %H:%M')}")
            print(f"   [INFO] Overall Sentiment: {briefing.overall_sentiment:.2f}")
            print(f"   [TARGET] Recommendation: {briefing.recommendation}")
            print(f"\n   [CLIPBOARD] Summary:")
            print(f"   {briefing.market_summary}")
            print(f"\n   [KEY] Key Events:")
            for event in briefing.key_events[:3]:
                print(f"   - {event}")
            print(f"\n   [TIP] Opportunities:")
            for opp in briefing.opportunities[:3]:
                print(f"   - {opp}")
            print(f"\n   [WARNING] Risks:")
            for risk in briefing.risks[:3]:
                print(f"   - {risk}")
        else:
            print("\n[WARNING] Brak wyniku")
            
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")


def test_emergency_detection(config: dict, news: list) -> None:
    """Testuje wykrywanie black swan events"""
    print("\n" + "="*60)
    print("[ALERT] TEST: Emergency Detection")
    print("="*60)
    
    try:
        from llm_sentiment import LLMSentimentAnalyzer
        
        analyzer = LLMSentimentAnalyzer(config)
        
        print("\n[SYNC] Sprawdzam emergency events...")
        
        is_emergency, details = analyzer.emergency_detection(news)
        
        if is_emergency:
            print(f"\n[ALERT] EMERGENCY DETECTED!")
            print(f"   Details: {details}")
        else:
            print(f"\n[OK] Brak emergency events")
            if details:
                print(f"   Analysis: {details}")
            
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")


def test_trade_explanation(config: dict) -> None:
    """Testuje wyjaśnienie trade'a"""
    print("\n" + "="*60)
    print("[TIP] TEST: Trade Explanation")
    print("="*60)
    
    try:
        from llm_sentiment import LLMSentimentAnalyzer
        
        analyzer = LLMSentimentAnalyzer(config)
        
        # Przykładowy kontekst trade'a
        trade_context = {
            'symbol': 'BTCUSDC',
            'direction': 'LONG',
            'pattern': 'EMA_PULLBACK_BULLISH',
            'technical_score': 72.5,
            'sentiment_score': 0.45,
            'reasoning': [
                'Bullish trend (HTF)',
                'EMA pullback confirmed',
                'Volume rising',
                'RSI favorable (45)',
                'VWAP above'
            ]
        }
        
        print("\n[INFO] Kontekst trade'a:")
        for key, value in trade_context.items():
            print(f"   {key}: {value}")
        
        print("\n[SYNC] Generuję wyjaśnienie...")
        
        explanation = analyzer.explain_trade(trade_context)
        
        if explanation:
            print(f"\n[TIP] Wyjaśnienie:")
            print(f"   {explanation}")
        else:
            print("\n[WARNING] Brak wyjaśnienia")
            
    except Exception as e:
        print(f"[ERROR] Błąd: {e}")


def main():
    """Main test function"""
    print("\n" + "#"*60)
    print("#  CRYPTO TRADING BOT - LLM SENTIMENT TEST SUITE")
    print("#"*60)
    print(f"\n[TIME] Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Załaduj konfigurację
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("\n[ERROR] Brak pliku config.yaml")
        print("   Uruchom z katalogu projektu")
        sys.exit(1)
    
    # Upewnij się, że LLM jest włączone
    if 'llm' not in config:
        config['llm'] = {
            'enabled': True,
            'provider': 'lm_studio',
            'base_url': 'http://localhost:1234/v1',
            'model': 'llama3:8b',
            'timeout': 30,
            'temperature': 0.1
        }
    
    if 'news' not in config:
        config['news'] = {
            'enabled': True,
            'sources': ['coindesk', 'cointelegraph'],
            'cache_hours': 24
        }
    
    # 1. Test News Fetcher
    news = test_news_fetcher(config)
    
    # 2. Test LLM Connection
    llm_available = test_llm_connection(config)
    
    # 3. Test Sentiment Analysis
    test_sentiment_analysis(config, news)
    
    # 4. Test Emergency Detection
    test_emergency_detection(config, news)
    
    # 5. Test Daily Briefing (tylko jeśli LLM dostępny)
    if llm_available and news:
        test_daily_briefing(config, news)
    
    # 6. Test Trade Explanation
    if llm_available:
        test_trade_explanation(config)
    
    # Summary
    print("\n" + "="*60)
    print("[CLIPBOARD] PODSUMOWANIE")
    print("="*60)
    print(f"\n   News Fetcher: {'[OK] OK' if news else '[WARNING] Brak newsów'}")
    print(f"   LLM Connection: {'[OK] OK' if llm_available else '[ERROR] Niedostępny'}")
    print(f"\n[TIME] Koniec: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
