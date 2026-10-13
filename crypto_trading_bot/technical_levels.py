#!/usr/bin/env python3
"""
technical_levels.py - Fibonacci Retracements & Support/Resistance Zones

Funkcjonalności:
- Automatyczne wykrywanie swing high/low
- Fibonacci levels: 23.6%, 38.2%, 50%, 61.8%, 78.6%
- Support/Resistance zones na podstawie historycznych odbić
- Integracja z pattern_analyzer.py
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class LevelType(Enum):
    """Typ poziomu technicznego"""
    SUPPORT = "support"
    RESISTANCE = "resistance"
    FIBONACCI = "fibonacci"
    PIVOT = "pivot"


@dataclass
class TechnicalLevel:
    """Reprezentacja poziomu technicznego"""
    level_type: LevelType
    price: float
    strength: float  # 0-100
    touches: int     # Ile razy cena dotknęła tego poziomu
    name: str = ""   # Np. "Fib 61.8%", "S1", "R2"
    zone_high: float = 0  # Górna granica strefy
    zone_low: float = 0   # Dolna granica strefy
    
    def __post_init__(self):
        if self.zone_high == 0:
            self.zone_high = self.price * 1.002  # 0.2% powyżej
        if self.zone_low == 0:
            self.zone_low = self.price * 0.998   # 0.2% poniżej
    
    def is_price_near(self, current_price: float, tolerance_pct: float = 0.5) -> bool:
        """Sprawdza czy cena jest blisko poziomu"""
        tolerance = self.price * (tolerance_pct / 100)
        return abs(current_price - self.price) <= tolerance
    
    def to_dict(self) -> Dict:
        return {
            'type': self.level_type.value,
            'price': self.price,
            'strength': self.strength,
            'touches': self.touches,
            'name': self.name,
            'zone_high': self.zone_high,
            'zone_low': self.zone_low
        }


@dataclass
class SwingPoint:
    """Swing High lub Swing Low"""
    price: float
    index: int
    timestamp: datetime
    is_high: bool  # True = swing high, False = swing low
    
    def to_dict(self) -> Dict:
        return {
            'price': self.price,
            'index': self.index,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
            'is_high': self.is_high
        }


@dataclass
class FibonacciLevels:
    """Poziomy Fibonacci"""
    swing_high: float
    swing_low: float
    direction: str  # 'uptrend' lub 'downtrend'
    levels: Dict[str, float] = field(default_factory=dict)
    
    def __post_init__(self):
        self._calculate_levels()
    
    def _calculate_levels(self):
        """Oblicza poziomy Fibonacci"""
        diff = self.swing_high - self.swing_low
        
        fib_ratios = {
            '0.0': 0.0,
            '23.6': 0.236,
            '38.2': 0.382,
            '50.0': 0.5,
            '61.8': 0.618,
            '78.6': 0.786,
            '100.0': 1.0,
            '127.2': 1.272,  # Extension
            '161.8': 1.618   # Extension
        }
        
        if self.direction == 'uptrend':
            # Retracement od góry (swing high) w dół
            for name, ratio in fib_ratios.items():
                self.levels[name] = self.swing_high - (diff * ratio)
        else:
            # Retracement od dołu (swing low) w górę
            for name, ratio in fib_ratios.items():
                self.levels[name] = self.swing_low + (diff * ratio)
    
    def get_nearest_level(self, price: float) -> Tuple[str, float]:
        """Zwraca najbliższy poziom Fib"""
        nearest_name = ''
        nearest_price = 0
        min_diff = float('inf')
        
        for name, level_price in self.levels.items():
            diff = abs(price - level_price)
            if diff < min_diff:
                min_diff = diff
                nearest_name = name
                nearest_price = level_price
        
        return nearest_name, nearest_price
    
    def to_dict(self) -> Dict:
        return {
            'swing_high': self.swing_high,
            'swing_low': self.swing_low,
            'direction': self.direction,
            'levels': self.levels
        }


class TechnicalLevels:
    """
    Wykrywa i zarządza poziomami technicznymi:
    - Fibonacci retracements
    - Support/Resistance zones
    - Pivot points
    """
    
    # Główne poziomy Fibonacci do scoringu
    KEY_FIB_LEVELS = ['38.2', '50.0', '61.8']
    
    def __init__(self, config: dict):
        """
        Inicjalizacja
        
        Args:
            config: Konfiguracja z sekcją 'technical_levels'
        """
        self.config = config.get('technical_levels', {})
        
        # Parametry swing detection
        self.swing_lookback = self.config.get('swing_lookback', 5)  # Ile świec po każdej stronie
        self.min_swing_distance_pct = self.config.get('min_swing_distance_pct', 1.0)  # Min różnica między swing H/L
        
        # Parametry S/R
        self.sr_lookback = self.config.get('sr_lookback', 100)  # Ile świec do analizy S/R
        self.sr_touch_tolerance_pct = self.config.get('sr_touch_tolerance_pct', 0.3)  # Tolerancja "dotknięcia"
        self.sr_min_touches = self.config.get('sr_min_touches', 2)  # Min liczba dotknięć
        self.sr_zone_pct = self.config.get('sr_zone_pct', 0.5)  # Szerokość strefy S/R
        
        # Parametry pivot
        self.pivot_type = self.config.get('pivot_type', 'standard')  # standard, fibonacci, camarilla
        
        # Cache
        self._cache: Dict[str, Dict] = {}
        
        logger.info("[OK] TechnicalLevels zainicjalizowany")
    
    def detect_swing_points(
        self,
        df: pd.DataFrame,
        lookback: int = None
    ) -> List[SwingPoint]:
        """
        Wykrywa swing high i swing low points
        
        Args:
            df: DataFrame z OHLCV
            lookback: Ile świec po każdej stronie (domyślnie z config)
        
        Returns:
            Lista SwingPoint
        """
        if lookback is None:
            lookback = self.swing_lookback
        
        swings = []
        highs = df['high'].values
        lows = df['low'].values
        
        for i in range(lookback, len(df) - lookback):
            # Swing High: najwyższe w oknie
            is_swing_high = True
            for j in range(i - lookback, i + lookback + 1):
                if j != i and highs[j] >= highs[i]:
                    is_swing_high = False
                    break
            
            if is_swing_high:
                swings.append(SwingPoint(
                    price=highs[i],
                    index=i,
                    timestamp=df.index[i] if isinstance(df.index[i], datetime) else datetime.now(),
                    is_high=True
                ))
            
            # Swing Low: najniższe w oknie
            is_swing_low = True
            for j in range(i - lookback, i + lookback + 1):
                if j != i and lows[j] <= lows[i]:
                    is_swing_low = False
                    break
            
            if is_swing_low:
                swings.append(SwingPoint(
                    price=lows[i],
                    index=i,
                    timestamp=df.index[i] if isinstance(df.index[i], datetime) else datetime.now(),
                    is_high=False
                ))
        
        return swings
    
    def calculate_fibonacci(
        self,
        df: pd.DataFrame,
        swing_high: float = None,
        swing_low: float = None
    ) -> Optional[FibonacciLevels]:
        """
        Oblicza poziomy Fibonacci
        
        Args:
            df: DataFrame z OHLCV
            swing_high: Opcjonalnie ręcznie podany swing high
            swing_low: Opcjonalnie ręcznie podany swing low
        
        Returns:
            FibonacciLevels lub None
        """
        try:
            # Automatyczne wykrywanie swing points jeśli nie podano
            if swing_high is None or swing_low is None:
                swings = self.detect_swing_points(df)
                
                if len(swings) < 2:
                    return None
                
                # Znajdź ostatni swing high i swing low
                recent_highs = [s for s in swings if s.is_high][-3:]
                recent_lows = [s for s in swings if not s.is_high][-3:]
                
                if not recent_highs or not recent_lows:
                    return None
                
                # Użyj najwyższego swing high i najniższego swing low z ostatnich
                swing_high = max(s.price for s in recent_highs)
                swing_low = min(s.price for s in recent_lows)
            
            # Sprawdź minimalną odległość
            diff_pct = ((swing_high - swing_low) / swing_low) * 100
            if diff_pct < self.min_swing_distance_pct:
                return None
            
            # Określ kierunek trendu na podstawie ostatniej ceny
            current_price = df['close'].iloc[-1]
            mid_price = (swing_high + swing_low) / 2
            direction = 'uptrend' if current_price > mid_price else 'downtrend'
            
            return FibonacciLevels(
                swing_high=swing_high,
                swing_low=swing_low,
                direction=direction
            )
            
        except Exception as e:
            logger.error(f"Błąd kalkulacji Fibonacci: {e}")
            return None
    
    def detect_support_resistance(
        self,
        df: pd.DataFrame,
        num_levels: int = 5
    ) -> List[TechnicalLevel]:
        """
        Wykrywa poziomy Support/Resistance
        
        Algorytm:
        1. Znajdź swing points
        2. Grupuj bliskie poziomy
        3. Policz "touches" - ile razy cena dotknęła i odbiła się
        4. Sortuj według siły
        
        Args:
            df: DataFrame z OHLCV
            num_levels: Ile poziomów zwrócić
        
        Returns:
            Lista TechnicalLevel
        """
        try:
            # Pobierz swing points
            swings = self.detect_swing_points(df)
            
            if not swings:
                return []
            
            # Grupuj bliskie poziomy
            tolerance = df['close'].iloc[-1] * (self.sr_touch_tolerance_pct / 100)
            
            # Zbierz wszystkie ceny swing points
            prices = [s.price for s in swings]
            
            # Grupowanie - clustering prostych poziomów
            levels = []
            used = set()
            
            for i, price in enumerate(prices):
                if i in used:
                    continue
                
                # Znajdź wszystkie ceny w tolerancji
                cluster = [price]
                cluster_indices = [i]
                
                for j, other_price in enumerate(prices):
                    if j != i and j not in used and abs(price - other_price) <= tolerance:
                        cluster.append(other_price)
                        cluster_indices.append(j)
                
                if len(cluster) >= self.sr_min_touches:
                    avg_price = np.mean(cluster)
                    
                    # Określ typ: S lub R
                    current_price = df['close'].iloc[-1]
                    level_type = LevelType.SUPPORT if avg_price < current_price else LevelType.RESISTANCE
                    
                    # Policz wszystkie touches (high/low dotknęły tego poziomu)
                    touches = self._count_touches(df, avg_price, tolerance)
                    
                    # Siła na podstawie touches i odległości od ceny
                    distance_factor = 1 - min(abs(current_price - avg_price) / current_price, 0.5)
                    strength = min(100, (touches * 15 + len(cluster) * 10) * distance_factor)
                    
                    zone_pct = self.sr_zone_pct / 100
                    levels.append(TechnicalLevel(
                        level_type=level_type,
                        price=round(avg_price, 2),
                        strength=round(strength, 1),
                        touches=touches,
                        name=f"{'S' if level_type == LevelType.SUPPORT else 'R'}{len(levels)+1}",
                        zone_high=avg_price * (1 + zone_pct),
                        zone_low=avg_price * (1 - zone_pct)
                    ))
                    
                    used.update(cluster_indices)
            
            # Sortuj po sile
            levels.sort(key=lambda x: x.strength, reverse=True)
            
            return levels[:num_levels]
            
        except Exception as e:
            logger.error(f"Błąd wykrywania S/R: {e}")
            return []
    
    def _count_touches(self, df: pd.DataFrame, level: float, tolerance: float) -> int:
        """Liczy ile razy cena dotknęła poziomu"""
        touches = 0
        
        for i in range(len(df)):
            high = df['high'].iloc[i]
            low = df['low'].iloc[i]
            
            # Dotknięcie = high lub low w tolerancji od poziomu
            if abs(high - level) <= tolerance or abs(low - level) <= tolerance:
                touches += 1
        
        return touches
    
    def calculate_pivot_points(
        self,
        df: pd.DataFrame
    ) -> Dict[str, TechnicalLevel]:
        """
        Oblicza Pivot Points
        
        Standard Pivot:
        P = (H + L + C) / 3
        R1 = 2*P - L
        R2 = P + (H - L)
        R3 = H + 2*(P - L)
        S1 = 2*P - H
        S2 = P - (H - L)
        S3 = L - 2*(H - P)
        
        Args:
            df: DataFrame z OHLCV
        
        Returns:
            Dict z poziomami pivot
        """
        try:
            # Użyj ostatniej zamkniętej świecy
            if len(df) < 2:
                return {}
            
            # Dla daily pivot używamy poprzedniego dnia
            # Dla intraday używamy poprzedniej świecy
            prev = df.iloc[-2]
            h, l, c = prev['high'], prev['low'], prev['close']
            
            current_price = df['close'].iloc[-1]
            
            # Standard Pivot
            p = (h + l + c) / 3
            r1 = 2 * p - l
            r2 = p + (h - l)
            r3 = h + 2 * (p - l)
            s1 = 2 * p - h
            s2 = p - (h - l)
            s3 = l - 2 * (h - p)
            
            pivots = {
                'PP': TechnicalLevel(
                    level_type=LevelType.PIVOT,
                    price=round(p, 2),
                    strength=80,
                    touches=1,
                    name='PP'
                ),
                'R1': TechnicalLevel(
                    level_type=LevelType.RESISTANCE,
                    price=round(r1, 2),
                    strength=70,
                    touches=0,
                    name='R1'
                ),
                'R2': TechnicalLevel(
                    level_type=LevelType.RESISTANCE,
                    price=round(r2, 2),
                    strength=60,
                    touches=0,
                    name='R2'
                ),
                'R3': TechnicalLevel(
                    level_type=LevelType.RESISTANCE,
                    price=round(r3, 2),
                    strength=50,
                    touches=0,
                    name='R3'
                ),
                'S1': TechnicalLevel(
                    level_type=LevelType.SUPPORT,
                    price=round(s1, 2),
                    strength=70,
                    touches=0,
                    name='S1'
                ),
                'S2': TechnicalLevel(
                    level_type=LevelType.SUPPORT,
                    price=round(s2, 2),
                    strength=60,
                    touches=0,
                    name='S2'
                ),
                'S3': TechnicalLevel(
                    level_type=LevelType.SUPPORT,
                    price=round(s3, 2),
                    strength=50,
                    touches=0,
                    name='S3'
                )
            }
            
            return pivots
            
        except Exception as e:
            logger.error(f"Błąd kalkulacji Pivot Points: {e}")
            return {}
    
    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str
    ) -> Dict:
        """
        Pełna analiza poziomów technicznych
        
        Args:
            df: DataFrame z OHLCV
            symbol: Symbol pary
        
        Returns:
            Dict z wynikami analizy
        """
        current_price = df['close'].iloc[-1]
        
        # Fibonacci
        fib = self.calculate_fibonacci(df)
        
        # Support/Resistance
        sr_levels = self.detect_support_resistance(df)
        
        # Pivot Points
        pivots = self.calculate_pivot_points(df)
        
        # Swing Points
        swings = self.detect_swing_points(df)
        
        # Analiza - czy cena jest przy ważnym poziomie?
        near_level = None
        level_bonus = 0
        
        # Sprawdź Fibonacci
        if fib:
            for level_name in self.KEY_FIB_LEVELS:
                level_price = fib.levels.get(level_name)
                if level_price:
                    diff_pct = abs(current_price - level_price) / current_price * 100
                    if diff_pct < 0.5:  # Blisko poziomu Fib
                        near_level = f"Fib {level_name}%"
                        level_bonus = 15
                        break
        
        # Sprawdź S/R
        if not near_level:
            for level in sr_levels[:3]:  # Top 3 levels
                if level.is_price_near(current_price, 0.5):
                    near_level = level.name
                    level_bonus = min(20, level.strength * 0.2)
                    break
        
        # Sprawdź Pivot
        if not near_level:
            for name, pivot in pivots.items():
                if pivot.is_price_near(current_price, 0.3):
                    near_level = name
                    level_bonus = 10
                    break
        
        result = {
            'symbol': symbol,
            'current_price': current_price,
            'fibonacci': fib.to_dict() if fib else None,
            'support_resistance': [l.to_dict() for l in sr_levels],
            'pivots': {k: v.to_dict() for k, v in pivots.items()},
            'swing_points': [s.to_dict() for s in swings[-10:]],  # Last 10
            'near_level': near_level,
            'level_bonus': level_bonus,
            'nearest_support': self._find_nearest_support(current_price, sr_levels, pivots),
            'nearest_resistance': self._find_nearest_resistance(current_price, sr_levels, pivots)
        }
        
        # Cache wyniki
        self._cache[symbol] = result
        
        return result
    
    def _find_nearest_support(self, price: float, sr_levels: List, pivots: Dict) -> Optional[float]:
        """Znajduje najbliższe wsparcie poniżej ceny"""
        supports = []
        
        for level in sr_levels:
            if level.level_type == LevelType.SUPPORT and level.price < price:
                supports.append(level.price)
        
        for name, pivot in pivots.items():
            if pivot.level_type == LevelType.SUPPORT and pivot.price < price:
                supports.append(pivot.price)
        
        return max(supports) if supports else None
    
    def _find_nearest_resistance(self, price: float, sr_levels: List, pivots: Dict) -> Optional[float]:
        """Znajduje najbliższy opór powyżej ceny"""
        resistances = []
        
        for level in sr_levels:
            if level.level_type == LevelType.RESISTANCE and level.price > price:
                resistances.append(level.price)
        
        for name, pivot in pivots.items():
            if pivot.level_type == LevelType.RESISTANCE and pivot.price > price:
                resistances.append(pivot.price)
        
        return min(resistances) if resistances else None
    
    def get_score_bonus(
        self,
        df: pd.DataFrame,
        symbol: str,
        direction: str,
        entry_price: float
    ) -> float:
        """
        Oblicza bonus do score za trade przy poziomie S/R lub Fib
        
        Args:
            df: DataFrame z OHLCV
            symbol: Symbol pary
            direction: 'LONG' lub 'SHORT'
            entry_price: Cena wejścia
        
        Returns:
            Bonus do score (0-20)
        """
        # Użyj cache jeśli dostępny
        if symbol not in self._cache:
            self.analyze(df, symbol)
        
        analysis = self._cache.get(symbol, {})
        
        bonus = 0
        
        # Bonus za trade przy Fibonacci
        fib = analysis.get('fibonacci')
        if fib:
            for level_name in self.KEY_FIB_LEVELS:
                level_price = fib['levels'].get(level_name)
                if level_price:
                    diff_pct = abs(entry_price - level_price) / entry_price * 100
                    if diff_pct < 0.5:
                        bonus += 10
                        logger.info(f"[INFO] {symbol}: Bonus +10 za Fib {level_name}%")
                        break
        
        # Bonus za trade przy S/R
        sr_levels = analysis.get('support_resistance', [])
        for level in sr_levels[:3]:
            diff_pct = abs(entry_price - level['price']) / entry_price * 100
            if diff_pct < 0.5:
                # LONG przy support = dobrze, SHORT przy resistance = dobrze
                if (direction == 'LONG' and level['type'] == 'support') or \
                   (direction == 'SHORT' and level['type'] == 'resistance'):
                    bonus += 10
                    logger.info(f"[INFO] {symbol}: Bonus +10 za {level['name']}")
                    break
        
        return min(bonus, 20)  # Max 20 punktów
    
    def get_visualization_data(self, symbol: str) -> Dict:
        """Zwraca dane do wizualizacji na dashboardzie"""
        return self._cache.get(symbol, {})


if __name__ == "__main__":
    # Test modułu
    import yaml
    from data_fetcher import DataFetcher
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Test
    levels = TechnicalLevels(config)
    
    # Pobierz dane
    fetcher = DataFetcher(config)
    df = fetcher.get_klines('BTCUSDC', '15m', limit=200)
    
    if not df.empty:
        # Analiza
        result = levels.analyze(df, 'BTCUSDC')
        
        print("\n[INFO] Technical Levels Analysis:")
        print(f"Current Price: {result['current_price']:.2f}")
        
        if result['fibonacci']:
            print("\n[LEVEL] Fibonacci Levels:")
            for name, price in result['fibonacci']['levels'].items():
                print(f"   {name}%: {price:.2f}")
        
        print("\n[SHIELD] Support/Resistance:")
        for level in result['support_resistance']:
            print(f"   {level['name']}: {level['price']:.2f} (strength: {level['strength']})")
        
        print("\n[PIN] Pivot Points:")
        for name, pivot in result['pivots'].items():
            print(f"   {name}: {pivot['price']:.2f}")
        
        if result['near_level']:
            print(f"\n[TARGET] Price near: {result['near_level']} (bonus: +{result['level_bonus']})")
    else:
        print("[ERROR] Could not fetch data")
