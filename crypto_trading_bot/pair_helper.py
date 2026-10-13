#!/usr/bin/env python3
"""
pair_helper.py - Narzędzia do zarządzania parami tradingowymi

Funkcje:
- Pobieranie dostępnych par z Binance
- Filtrowanie po płynności i spreadzie
- Sugestie nowych par do dodania
- Walidacja par przed dodaniem
"""

import logging
from typing import List, Dict, Optional, Tuple
import json
import os

try:
    from binance.client import Client
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False

logger = logging.getLogger(__name__)


class PairHelper:
    """
    Pomocnik do zarządzania parami tradingowymi.
    
    Funkcje:
    - fetch_available_pairs(): Pobiera dostępne pary z Binance
    - filter_by_volume(): Filtruje po dziennym wolumenie
    - check_spread(): Sprawdza spread dla pary
    - suggest_pairs(): Sugeruje pary do dodania
    """
    
    # Sugerowane pary do dodania
    SUGGESTED_PAIRS = {
        'top_tier': [
            {'symbol': 'SOLUSDC', 'name': 'Solana', 'category': 'L1'},
            {'symbol': 'ADAUSDC', 'name': 'Cardano', 'category': 'L1'},
            {'symbol': 'AVAXUSDC', 'name': 'Avalanche', 'category': 'L1'},
            {'symbol': 'MATICUSDC', 'name': 'Polygon', 'category': 'L2'},
        ],
        'mid_tier': [
            {'symbol': 'LINKUSDC', 'name': 'Chainlink', 'category': 'Oracle'},
            {'symbol': 'DOTUSDC', 'name': 'Polkadot', 'category': 'L1'},
            {'symbol': 'UNIUSDC', 'name': 'Uniswap', 'category': 'DeFi'},
            {'symbol': 'ATOMUSDC', 'name': 'Cosmos', 'category': 'L1'},
        ],
        'volatile': [
            {'symbol': 'SHIBUSDC', 'name': 'Shiba Inu', 'category': 'Meme'},
            {'symbol': 'PEPEUSDC', 'name': 'Pepe', 'category': 'Meme'},
        ]
    }
    
    # Minimalne wymagania
    MIN_VOLUME_USDC = 10_000_000  # $10M daily volume
    MAX_SPREAD_PCT = 0.1  # 0.1% max spread
    
    def __init__(self, config: dict = None):
        """
        Inicjalizacja PairHelper
        
        Args:
            config: Opcjonalna konfiguracja z kluczami Binance
        """
        self.config = config or {}
        self.client = None
        
        if BINANCE_AVAILABLE:
            self._init_client()
        
        # Cache
        self.pairs_cache: Dict = {}
        self.cache_file = './data/pairs_cache.json'
        self._load_cache()
    
    def _init_client(self):
        """Inicjalizuje klienta Binance"""
        try:
            binance_config = self.config.get('binance', {})
            api_key = binance_config.get('api_key', '')
            api_secret = binance_config.get('api_secret', '')
            use_testnet = binance_config.get('testnet', True)
            
            if api_key and api_secret and api_key != 'YOUR_TESTNET_API_KEY':
                self.client = Client(api_key, api_secret, testnet=use_testnet)
            else:
                # Public client (bez kluczy)
                self.client = Client("", "", testnet=True)
                
        except Exception as e:
            logger.warning(f"Nie można zainicjować klienta Binance: {e}")
    
    def fetch_available_pairs(self, quote_asset: str = 'USDC') -> List[Dict]:
        """
        Pobiera dostępne pary z Binance.
        
        Args:
            quote_asset: Waluta kwotowana (USDC, USDT, etc.)
        
        Returns:
            Lista par z informacjami
        """
        if not self.client:
            logger.warning("Binance client niedostępny - zwracam cached/suggested pairs")
            return self._get_fallback_pairs(quote_asset)
        
        try:
            exchange_info = self.client.get_exchange_info()
            pairs = []
            
            for symbol_info in exchange_info['symbols']:
                if symbol_info['quoteAsset'] == quote_asset:
                    if symbol_info['status'] == 'TRADING':
                        pairs.append({
                            'symbol': symbol_info['symbol'],
                            'base_asset': symbol_info['baseAsset'],
                            'quote_asset': symbol_info['quoteAsset'],
                            'status': symbol_info['status'],
                            'min_qty': self._get_filter_value(symbol_info, 'LOT_SIZE', 'minQty'),
                            'min_notional': self._get_filter_value(symbol_info, 'MIN_NOTIONAL', 'minNotional')
                        })
            
            # Cache results
            self.pairs_cache[quote_asset] = {
                'pairs': pairs,
                'timestamp': str(datetime.now())
            }
            self._save_cache()
            
            return pairs
            
        except Exception as e:
            logger.error(f"Błąd pobierania par: {e}")
            return self._get_fallback_pairs(quote_asset)
    
    def filter_by_volume(
        self,
        pairs: List[Dict],
        min_volume_usdc: float = None
    ) -> List[Dict]:
        """
        Filtruje pary po dziennym wolumenie.
        
        Args:
            pairs: Lista par do filtrowania
            min_volume_usdc: Minimalny volume w USDC
        
        Returns:
            Przefiltrowana lista par
        """
        if not self.client:
            return pairs
        
        min_vol = min_volume_usdc or self.MIN_VOLUME_USDC
        filtered = []
        
        try:
            tickers = self.client.get_ticker()
            volume_map = {t['symbol']: float(t['quoteVolume']) for t in tickers}
            
            for pair in pairs:
                symbol = pair['symbol']
                volume = volume_map.get(symbol, 0)
                
                if volume >= min_vol:
                    pair['volume_24h'] = volume
                    filtered.append(pair)
            
            # Sortuj po volume
            filtered.sort(key=lambda x: x.get('volume_24h', 0), reverse=True)
            
        except Exception as e:
            logger.error(f"Błąd filtrowania po volume: {e}")
            return pairs
        
        return filtered
    
    def check_spread(self, symbol: str) -> Tuple[float, bool]:
        """
        Sprawdza spread dla pary.
        
        Args:
            symbol: Para walutowa
        
        Returns:
            (spread_pct, is_acceptable)
        """
        if not self.client:
            return 0.0, True
        
        try:
            orderbook = self.client.get_order_book(symbol=symbol, limit=5)
            
            best_bid = float(orderbook['bids'][0][0]) if orderbook['bids'] else 0
            best_ask = float(orderbook['asks'][0][0]) if orderbook['asks'] else 0
            
            if best_bid <= 0 or best_ask <= 0:
                return 0.0, False
            
            spread = best_ask - best_bid
            spread_pct = (spread / best_ask) * 100
            
            is_acceptable = spread_pct <= self.MAX_SPREAD_PCT
            
            return spread_pct, is_acceptable
            
        except Exception as e:
            logger.error(f"Błąd sprawdzania spread: {e}")
            return 0.0, True
    
    def suggest_pairs(
        self,
        current_pairs: List[str] = None,
        include_volatile: bool = False
    ) -> List[Dict]:
        """
        Sugeruje pary do dodania.
        
        Args:
            current_pairs: Lista aktualnych par
            include_volatile: Czy uwzględnić volatile pary
        
        Returns:
            Lista sugerowanych par
        """
        current = set(current_pairs or [])
        suggestions = []
        
        # Top tier - zawsze rekomendowane
        for pair in self.SUGGESTED_PAIRS['top_tier']:
            if pair['symbol'] not in current:
                pair['tier'] = 'top'
                pair['risk'] = 'medium'
                suggestions.append(pair)
        
        # Mid tier
        for pair in self.SUGGESTED_PAIRS['mid_tier']:
            if pair['symbol'] not in current:
                pair['tier'] = 'mid'
                pair['risk'] = 'medium'
                suggestions.append(pair)
        
        # Volatile - tylko jeśli włączone
        if include_volatile:
            for pair in self.SUGGESTED_PAIRS['volatile']:
                if pair['symbol'] not in current:
                    pair['tier'] = 'volatile'
                    pair['risk'] = 'high'
                    suggestions.append(pair)
        
        return suggestions
    
    def validate_pair(self, symbol: str) -> Dict:
        """
        Waliduje parę przed dodaniem.
        
        Args:
            symbol: Para do walidacji
        
        Returns:
            Dict z wynikami walidacji
        """
        result = {
            'symbol': symbol,
            'valid': False,
            'checks': {},
            'errors': []
        }
        
        # Check 1: Dostępność na Binance
        available = False
        if self.client:
            try:
                info = self.client.get_symbol_info(symbol)
                available = info is not None and info.get('status') == 'TRADING'
            except:
                pass
        
        result['checks']['available'] = available
        if not available:
            result['errors'].append(f"{symbol} nie jest dostępny na Binance")
        
        # Check 2: Volume
        has_volume = False
        if self.client and available:
            try:
                ticker = self.client.get_ticker(symbol=symbol)
                volume = float(ticker.get('quoteVolume', 0))
                has_volume = volume >= self.MIN_VOLUME_USDC
                result['checks']['volume'] = volume
            except:
                pass
        
        if not has_volume:
            result['errors'].append(f"Volume poniżej minimum ${self.MIN_VOLUME_USDC/1e6:.0f}M")
        
        # Check 3: Spread
        spread_pct, spread_ok = self.check_spread(symbol)
        result['checks']['spread_pct'] = spread_pct
        result['checks']['spread_ok'] = spread_ok
        
        if not spread_ok:
            result['errors'].append(f"Spread {spread_pct:.3f}% > max {self.MAX_SPREAD_PCT}%")
        
        # Final verdict
        result['valid'] = available and has_volume and spread_ok
        
        return result
    
    def get_pair_info(self, symbol: str) -> Optional[Dict]:
        """Pobiera szczegółowe informacje o parze"""
        if not self.client:
            return None
        
        try:
            info = self.client.get_symbol_info(symbol)
            ticker = self.client.get_ticker(symbol=symbol)
            
            return {
                'symbol': symbol,
                'base_asset': info.get('baseAsset'),
                'quote_asset': info.get('quoteAsset'),
                'status': info.get('status'),
                'price': float(ticker.get('lastPrice', 0)),
                'volume_24h': float(ticker.get('quoteVolume', 0)),
                'price_change_24h': float(ticker.get('priceChangePercent', 0)),
                'high_24h': float(ticker.get('highPrice', 0)),
                'low_24h': float(ticker.get('lowPrice', 0))
            }
            
        except Exception as e:
            logger.error(f"Błąd pobierania info dla {symbol}: {e}")
            return None
    
    def _get_filter_value(self, symbol_info: dict, filter_type: str, key: str) -> Optional[str]:
        """Pobiera wartość filtra z exchange info"""
        for f in symbol_info.get('filters', []):
            if f.get('filterType') == filter_type:
                return f.get(key)
        return None
    
    def _get_fallback_pairs(self, quote_asset: str) -> List[Dict]:
        """Zwraca fallback pary gdy API niedostępne"""
        # Połącz wszystkie sugerowane pary
        all_pairs = []
        for tier, pairs in self.SUGGESTED_PAIRS.items():
            for pair in pairs:
                if pair['symbol'].endswith(quote_asset):
                    all_pairs.append(pair)
        return all_pairs
    
    def _save_cache(self):
        """Zapisuje cache do pliku"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.pairs_cache, f, indent=2)
        except:
            pass
    
    def _load_cache(self):
        """Ładuje cache z pliku"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    self.pairs_cache = json.load(f)
        except:
            pass


# Import datetime dla cache timestamp
from datetime import datetime


def print_pair_suggestions():
    """Wyświetla sugestie par do dodania"""
    helper = PairHelper()
    
    current_pairs = ['BTCUSDC', 'ETHUSDC', 'XRPUSDC', 'DOGEUSDC']
    suggestions = helper.suggest_pairs(current_pairs, include_volatile=False)
    
    print("\n" + "="*60)
    print("[TIP] SUGESTIE PAR DO DODANIA")
    print("="*60)
    
    print("\n[INFO] Top Tier (wysoka płynność, niższe ryzyko):")
    for pair in suggestions:
        if pair['tier'] == 'top':
            print(f"   - {pair['symbol']:12} ({pair['name']}) - {pair['category']}")
    
    print("\n[UP] Mid Tier (dobra płynność):")
    for pair in suggestions:
        if pair['tier'] == 'mid':
            print(f"   - {pair['symbol']:12} ({pair['name']}) - {pair['category']}")
    
    print("\n[WARNING] Volatile (wysokie ryzyko/nagroda):")
    for pair in PairHelper.SUGGESTED_PAIRS['volatile']:
        print(f"   - {pair['symbol']:12} ({pair['name']}) - {pair['category']}")
    
    print("\n[LOG] JAK DODAĆ PARĘ:")
    print("   1. Otwórz config.yaml")
    print("   2. Znajdź sekcję trading.pairs")
    print("   3. Dodaj nową parę, np.: - 'SOLUSDC'")
    print("   4. Uruchom backtester przed live trading")
    print("\n   Wymagania: Min volume >$10M/day, spread <0.1%")
    print("="*60 + "\n")


if __name__ == "__main__":
    print_pair_suggestions()
