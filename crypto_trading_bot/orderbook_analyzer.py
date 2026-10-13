#!/usr/bin/env python3
"""
orderbook_analyzer.py - Order Book Analysis

Funkcjonalności:
- Pobieranie order book z Binance API
- Wykrywanie whale walls (duże zlecenia >100k USDC)
- Bid/Ask imbalance (przewaga kupujących/sprzedających)
- Liquidity zones (obszary z dużą płynnością)
- Scoring dla trade'ów zgodnych z order book
"""

import logging
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class OrderBookSignal(Enum):
    """Sygnały z order book"""
    STRONG_BUY = "strong_buy"       # Duża przewaga bid
    BUY = "buy"                      # Umiarkowana przewaga bid
    NEUTRAL = "neutral"              # Balans
    SELL = "sell"                    # Umiarkowana przewaga ask
    STRONG_SELL = "strong_sell"      # Duża przewaga ask


@dataclass
class WhaleWall:
    """Reprezentacja whale wall"""
    price: float
    quantity: float
    value_usdc: float
    side: str  # 'bid' lub 'ask'
    distance_pct: float  # Odległość od current price
    
    def to_dict(self) -> Dict:
        return {
            'price': self.price,
            'quantity': self.quantity,
            'value_usdc': self.value_usdc,
            'side': self.side,
            'distance_pct': self.distance_pct
        }


@dataclass
class LiquidityZone:
    """Strefa płynności"""
    price_low: float
    price_high: float
    total_liquidity: float
    side: str  # 'bid', 'ask', lub 'both'
    
    def to_dict(self) -> Dict:
        return {
            'price_low': self.price_low,
            'price_high': self.price_high,
            'total_liquidity': self.total_liquidity,
            'side': self.side
        }


@dataclass
class OrderBookAnalysis:
    """Wyniki analizy order book"""
    symbol: str
    timestamp: datetime
    bid_volume: float           # Łączny wolumen bid
    ask_volume: float           # Łączny wolumen ask
    imbalance_ratio: float      # bid/ask ratio (>1 = więcej bid)
    imbalance_pct: float        # % imbalance
    signal: OrderBookSignal
    whale_walls: List[WhaleWall]
    liquidity_zones: List[LiquidityZone]
    spread_pct: float          # Spread %
    depth_score: float         # Score głębokości (0-100)
    trade_score_bonus: float   # Bonus do trade score
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'bid_volume': round(self.bid_volume, 2),
            'ask_volume': round(self.ask_volume, 2),
            'imbalance_ratio': round(self.imbalance_ratio, 3),
            'imbalance_pct': round(self.imbalance_pct, 2),
            'signal': self.signal.value,
            'whale_walls': [w.to_dict() for w in self.whale_walls],
            'liquidity_zones': [z.to_dict() for z in self.liquidity_zones],
            'spread_pct': round(self.spread_pct, 4),
            'depth_score': round(self.depth_score, 1),
            'trade_score_bonus': round(self.trade_score_bonus, 1)
        }


class OrderBookAnalyzer:
    """
    Analizator order book
    
    UWAGA: Order book to heavy data - limituj wywołania!
    """
    
    # Progi dla whale walls
    WHALE_THRESHOLD_USDC = 100000  # 100k USDC
    
    # Progi dla imbalance
    STRONG_IMBALANCE_THRESHOLD = 2.0    # 2:1 ratio
    MODERATE_IMBALANCE_THRESHOLD = 1.3  # 1.3:1 ratio
    
    def __init__(self, config: dict, data_fetcher=None):
        """
        Inicjalizacja analyzera
        
        Args:
            config: Konfiguracja z sekcją 'orderbook'
            data_fetcher: Opcjonalnie DataFetcher do pobierania danych
        """
        self.config = config.get('orderbook', {})
        self.enabled = self.config.get('enabled', False)
        
        # Progi
        self.whale_threshold = self.config.get('whale_threshold_usdc', self.WHALE_THRESHOLD_USDC)
        self.depth_levels = self.config.get('depth_levels', 100)  # Ile poziomów order book
        self.analysis_depth_pct = self.config.get('analysis_depth_pct', 2)  # Analizuj +/- 2% od ceny
        
        # Rate limiting
        self.min_interval_seconds = self.config.get('min_interval_seconds', 10)
        self.last_call_time: Dict[str, datetime] = {}
        
        # Data fetcher
        self.data_fetcher = data_fetcher
        
        # Cache
        self._cache: Dict[str, OrderBookAnalysis] = {}
        self._cache_ttl_seconds = 30  # Cache na 30 sekund
        
        if self.enabled:
            logger.info("[OK] OrderBookAnalyzer zainicjalizowany")
        else:
            logger.info("[INFO] OrderBookAnalyzer wyłączony")
    
    def set_data_fetcher(self, data_fetcher):
        """Ustawia data fetcher"""
        self.data_fetcher = data_fetcher
    
    def can_analyze(self, symbol: str) -> bool:
        """
        Sprawdza czy można wykonać analizę (rate limiting)
        
        Returns:
            True jeśli można wykonać analizę
        """
        if not self.enabled:
            return False
        
        last_call = self.last_call_time.get(symbol)
        if last_call:
            elapsed = (datetime.now() - last_call).total_seconds()
            if elapsed < self.min_interval_seconds:
                return False
        
        return True
    
    def analyze(
        self,
        symbol: str,
        current_price: float = None,
        force: bool = False
    ) -> Optional[OrderBookAnalysis]:
        """
        Analizuje order book dla symbolu
        
        Args:
            symbol: Symbol pary
            current_price: Aktualna cena (jeśli znana)
            force: Wymuś analizę ignorując rate limit
        
        Returns:
            OrderBookAnalysis lub None
        """
        if not self.enabled:
            return None
        
        # Check cache
        if symbol in self._cache and not force:
            cached = self._cache[symbol]
            age = (datetime.now() - cached.timestamp).total_seconds()
            if age < self._cache_ttl_seconds:
                return cached
        
        # Rate limiting
        if not force and not self.can_analyze(symbol):
            logger.debug(f"Rate limit - using cached data for {symbol}")
            return self._cache.get(symbol)
        
        try:
            # Fetch order book
            order_book = self._fetch_orderbook(symbol)
            
            if not order_book:
                return None
            
            # Update rate limit
            self.last_call_time[symbol] = datetime.now()
            
            # Get current price
            if current_price is None:
                if order_book['bids'] and order_book['asks']:
                    best_bid = float(order_book['bids'][0][0])
                    best_ask = float(order_book['asks'][0][0])
                    current_price = (best_bid + best_ask) / 2
                else:
                    return None
            
            # Analyze
            analysis = self._perform_analysis(symbol, order_book, current_price)
            
            # Cache
            self._cache[symbol] = analysis
            
            logger.debug(f"[INFO] {symbol} Order book: imbalance={analysis.imbalance_pct:.1f}%, signal={analysis.signal.value}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing order book for {symbol}: {e}")
            return self._cache.get(symbol)
    
    def _fetch_orderbook(self, symbol: str) -> Optional[Dict]:
        """Pobiera order book"""
        if self.data_fetcher:
            return self.data_fetcher.get_orderbook(symbol, limit=self.depth_levels)
        
        # Fallback - direct API call
        try:
            import requests
            
            # Binance testnet
            url = f"https://testnet.binance.vision/api/v3/depth"
            params = {
                'symbol': symbol,
                'limit': self.depth_levels
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Orderbook API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return None
    
    def _perform_analysis(
        self,
        symbol: str,
        order_book: Dict,
        current_price: float
    ) -> OrderBookAnalysis:
        """
        Wykonuje pełną analizę order book
        """
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        
        # Filter to analysis depth
        price_range = current_price * (self.analysis_depth_pct / 100)
        min_price = current_price - price_range
        max_price = current_price + price_range
        
        filtered_bids = [
            (float(b[0]), float(b[1])) for b in bids
            if float(b[0]) >= min_price
        ]
        filtered_asks = [
            (float(a[0]), float(a[1])) for a in asks
            if float(a[0]) <= max_price
        ]
        
        # Calculate volumes
        bid_volume = sum(price * qty for price, qty in filtered_bids)
        ask_volume = sum(price * qty for price, qty in filtered_asks)
        
        # Imbalance
        total_volume = bid_volume + ask_volume
        if total_volume > 0:
            imbalance_ratio = bid_volume / ask_volume if ask_volume > 0 else 10
            imbalance_pct = ((bid_volume - ask_volume) / total_volume) * 100
        else:
            imbalance_ratio = 1
            imbalance_pct = 0
        
        # Signal
        signal = self._determine_signal(imbalance_ratio)
        
        # Whale walls
        whale_walls = self._detect_whale_walls(filtered_bids, filtered_asks, current_price)
        
        # Liquidity zones
        liquidity_zones = self._detect_liquidity_zones(filtered_bids, filtered_asks)
        
        # Spread
        if bids and asks:
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            spread_pct = ((best_ask - best_bid) / current_price) * 100
        else:
            spread_pct = 0
        
        # Depth score
        depth_score = self._calculate_depth_score(bid_volume, ask_volume, spread_pct)
        
        # Trade score bonus
        trade_score_bonus = self._calculate_trade_bonus(signal, whale_walls, imbalance_pct)
        
        return OrderBookAnalysis(
            symbol=symbol,
            timestamp=datetime.now(),
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            imbalance_ratio=imbalance_ratio,
            imbalance_pct=imbalance_pct,
            signal=signal,
            whale_walls=whale_walls,
            liquidity_zones=liquidity_zones,
            spread_pct=spread_pct,
            depth_score=depth_score,
            trade_score_bonus=trade_score_bonus
        )
    
    def _determine_signal(self, imbalance_ratio: float) -> OrderBookSignal:
        """Określa sygnał na podstawie imbalance"""
        if imbalance_ratio >= self.STRONG_IMBALANCE_THRESHOLD:
            return OrderBookSignal.STRONG_BUY
        elif imbalance_ratio >= self.MODERATE_IMBALANCE_THRESHOLD:
            return OrderBookSignal.BUY
        elif imbalance_ratio <= 1 / self.STRONG_IMBALANCE_THRESHOLD:
            return OrderBookSignal.STRONG_SELL
        elif imbalance_ratio <= 1 / self.MODERATE_IMBALANCE_THRESHOLD:
            return OrderBookSignal.SELL
        else:
            return OrderBookSignal.NEUTRAL
    
    def _detect_whale_walls(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        current_price: float
    ) -> List[WhaleWall]:
        """Wykrywa whale walls"""
        walls = []
        
        # Check bids
        for price, qty in bids:
            value = price * qty
            if value >= self.whale_threshold:
                distance_pct = ((current_price - price) / current_price) * 100
                walls.append(WhaleWall(
                    price=price,
                    quantity=qty,
                    value_usdc=value,
                    side='bid',
                    distance_pct=distance_pct
                ))
        
        # Check asks
        for price, qty in asks:
            value = price * qty
            if value >= self.whale_threshold:
                distance_pct = ((price - current_price) / current_price) * 100
                walls.append(WhaleWall(
                    price=price,
                    quantity=qty,
                    value_usdc=value,
                    side='ask',
                    distance_pct=distance_pct
                ))
        
        # Sort by value (largest first)
        walls.sort(key=lambda w: w.value_usdc, reverse=True)
        
        return walls[:10]  # Top 10 walls
    
    def _detect_liquidity_zones(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        zone_size: float = 0.1  # 0.1% price buckets
    ) -> List[LiquidityZone]:
        """Wykrywa strefy płynności"""
        zones = []
        
        if not bids and not asks:
            return zones
        
        # Combine all prices
        all_orders = [
            (price, qty, 'bid') for price, qty in bids
        ] + [
            (price, qty, 'ask') for price, qty in asks
        ]
        
        if not all_orders:
            return zones
        
        # Group into price buckets
        min_price = min(o[0] for o in all_orders)
        max_price = max(o[0] for o in all_orders)
        bucket_size = (max_price - min_price) * (zone_size / 100)
        
        if bucket_size == 0:
            return zones
        
        buckets = {}
        for price, qty, side in all_orders:
            bucket_idx = int((price - min_price) / bucket_size)
            if bucket_idx not in buckets:
                buckets[bucket_idx] = {'bid': 0, 'ask': 0, 'min': price, 'max': price}
            
            buckets[bucket_idx][side] += price * qty
            buckets[bucket_idx]['min'] = min(buckets[bucket_idx]['min'], price)
            buckets[bucket_idx]['max'] = max(buckets[bucket_idx]['max'], price)
        
        # Find high liquidity zones
        avg_liquidity = sum(b['bid'] + b['ask'] for b in buckets.values()) / len(buckets)
        
        for bucket_idx, bucket in buckets.items():
            total_liq = bucket['bid'] + bucket['ask']
            if total_liq > avg_liquidity * 2:  # 2x average
                side = 'both'
                if bucket['bid'] > bucket['ask'] * 2:
                    side = 'bid'
                elif bucket['ask'] > bucket['bid'] * 2:
                    side = 'ask'
                
                zones.append(LiquidityZone(
                    price_low=bucket['min'],
                    price_high=bucket['max'],
                    total_liquidity=total_liq,
                    side=side
                ))
        
        # Sort by liquidity
        zones.sort(key=lambda z: z.total_liquidity, reverse=True)
        
        return zones[:5]  # Top 5 zones
    
    def _calculate_depth_score(self, bid_vol: float, ask_vol: float, spread: float) -> float:
        """Oblicza score głębokości order book (0-100)"""
        # Higher volume = higher score
        # Lower spread = higher score
        
        total_vol = bid_vol + ask_vol
        
        # Volume score (logarithmic scale)
        # Assume 1M USDC is "good" depth
        vol_score = min(100, (np.log10(total_vol + 1) / np.log10(1000000)) * 100)
        
        # Spread score (inverse)
        if spread <= 0.01:
            spread_score = 100
        elif spread <= 0.05:
            spread_score = 80
        elif spread <= 0.1:
            spread_score = 60
        elif spread <= 0.2:
            spread_score = 40
        else:
            spread_score = 20
        
        # Combined score
        return (vol_score * 0.7 + spread_score * 0.3)
    
    def _calculate_trade_bonus(
        self,
        signal: OrderBookSignal,
        whale_walls: List[WhaleWall],
        imbalance_pct: float
    ) -> float:
        """
        Oblicza bonus do trade score na podstawie order book
        
        Returns:
            Bonus -10 to +15
        """
        bonus = 0
        
        # Signal bonus
        signal_bonuses = {
            OrderBookSignal.STRONG_BUY: 10,
            OrderBookSignal.BUY: 5,
            OrderBookSignal.NEUTRAL: 0,
            OrderBookSignal.SELL: -5,
            OrderBookSignal.STRONG_SELL: -10
        }
        bonus += signal_bonuses.get(signal, 0)
        
        # Whale wall consideration
        # Bid walls below price = support = bullish
        # Ask walls above price = resistance = bearish (for longs)
        bid_walls = [w for w in whale_walls if w.side == 'bid']
        ask_walls = [w for w in whale_walls if w.side == 'ask']
        
        if bid_walls and not ask_walls:
            bonus += 5  # Only bid walls = support
        elif ask_walls and not bid_walls:
            bonus -= 5  # Only ask walls = resistance
        
        # Imbalance bonus
        if abs(imbalance_pct) > 30:
            if imbalance_pct > 0:
                bonus += 3  # Strong bid imbalance
            else:
                bonus -= 3  # Strong ask imbalance
        
        return max(-10, min(15, bonus))
    
    def get_trade_score_modifier(
        self,
        symbol: str,
        direction: str,
        current_price: float = None
    ) -> Tuple[float, str]:
        """
        Zwraca modyfikator score dla trade'a
        
        Args:
            symbol: Symbol
            direction: 'LONG' lub 'SHORT'
            current_price: Aktualna cena
        
        Returns:
            (modifier, reason)
        """
        analysis = self.analyze(symbol, current_price)
        
        if not analysis:
            return 0, "No order book data"
        
        # Adjust bonus based on direction
        bonus = analysis.trade_score_bonus
        
        if direction == 'SHORT':
            # Invert the signal for shorts
            bonus = -bonus
        
        # Reason
        if bonus > 5:
            reason = f"Order book favorable ({analysis.signal.value})"
        elif bonus < -5:
            reason = f"Order book unfavorable ({analysis.signal.value})"
        else:
            reason = f"Order book neutral"
        
        if analysis.whale_walls:
            wall = analysis.whale_walls[0]
            reason += f", whale wall at {wall.price:.2f} ({wall.side})"
        
        return bonus, reason
    
    def get_cached_analysis(self, symbol: str) -> Optional[OrderBookAnalysis]:
        """Zwraca cached analizę"""
        return self._cache.get(symbol)


if __name__ == "__main__":
    # Test modułu
    import yaml
    
    logging.basicConfig(level=logging.DEBUG)
    
    config = {
        'orderbook': {
            'enabled': True,
            'whale_threshold_usdc': 50000,
            'depth_levels': 50,
            'min_interval_seconds': 5
        }
    }
    
    analyzer = OrderBookAnalyzer(config)
    
    # Test analysis
    print("\n[INFO] Analyzing BTCUSDC order book...")
    analysis = analyzer.analyze('BTCUSDC', force=True)
    
    if analysis:
        print(f"\nResults:")
        print(f"   Bid Volume: {analysis.bid_volume:,.0f} USDC")
        print(f"   Ask Volume: {analysis.ask_volume:,.0f} USDC")
        print(f"   Imbalance: {analysis.imbalance_pct:+.1f}%")
        print(f"   Signal: {analysis.signal.value}")
        print(f"   Spread: {analysis.spread_pct:.4f}%")
        print(f"   Depth Score: {analysis.depth_score:.1f}")
        print(f"   Trade Bonus: {analysis.trade_score_bonus:+.1f}")
        
        if analysis.whale_walls:
            print(f"\n[WHALE] Whale Walls:")
            for wall in analysis.whale_walls[:3]:
                print(f"   {wall.side.upper()}: {wall.price:.2f} ({wall.value_usdc:,.0f} USDC)")
        
        if analysis.liquidity_zones:
            print(f"\n[LIQUID] Liquidity Zones:")
            for zone in analysis.liquidity_zones[:3]:
                print(f"   {zone.price_low:.2f} - {zone.price_high:.2f}: {zone.total_liquidity:,.0f} USDC ({zone.side})")
    else:
        print("[ERROR] Could not analyze order book")
