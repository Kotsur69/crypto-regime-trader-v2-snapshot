#!/usr/bin/env python3
"""
market_regime.py - Market Regime Detection

Wykrywa stan rynku:
- TRENDING: Silny trend (up lub down)
- RANGING: Konsolidacja, ruch boczny
- VOLATILE: Duże wahania bez wyraźnego kierunku

Metryki:
- ADX (Average Directional Index) - siła trendu
- Bollinger Bands width - zmienność
- Price action patterns
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List
from enum import Enum

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Stan rynku"""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass
class RegimeAnalysis:
    """Wyniki analizy reżimu rynkowego"""
    regime: MarketRegime
    confidence: float  # 0-100
    adx: float
    adx_trend: str  # 'rising', 'falling', 'flat'
    bb_width: float
    bb_width_percentile: float  # Percentyl szerokości BB w historii
    volatility_ratio: float
    trend_strength: float  # -100 to 100 (negatywne = downtrend)
    recommendations: List[str]
    
    def to_dict(self) -> Dict:
        return {
            'regime': self.regime.value,
            'confidence': self.confidence,
            'adx': self.adx,
            'adx_trend': self.adx_trend,
            'bb_width': self.bb_width,
            'bb_width_percentile': self.bb_width_percentile,
            'volatility_ratio': self.volatility_ratio,
            'trend_strength': self.trend_strength,
            'recommendations': self.recommendations
        }


class MarketRegimeDetector:
    """
    Wykrywa reżim rynkowy i dostosowuje strategie
    """
    
    # Progi dla klasyfikacji
    ADX_TREND_THRESHOLD = 25      # Powyżej = trending
    ADX_STRONG_TREND = 40         # Powyżej = silny trend
    BB_WIDTH_HIGH_PERCENTILE = 80  # Powyżej = wysoka zmienność
    BB_WIDTH_LOW_PERCENTILE = 20   # Poniżej = niska zmienność (ranging)
    
    def __init__(self, config: dict):
        """
        Inicjalizacja detektora
        
        Args:
            config: Konfiguracja z sekcją 'market_regime'
        """
        self.config = config.get('market_regime', {})
        
        # Parametry
        self.adx_period = self.config.get('adx_period', 14)
        self.bb_period = self.config.get('bb_period', 20)
        self.bb_std = self.config.get('bb_std', 2.0)
        self.lookback_periods = self.config.get('lookback_periods', 100)
        
        # Progi konfigurowane
        self.adx_trend_threshold = self.config.get('adx_trend_threshold', self.ADX_TREND_THRESHOLD)
        self.adx_strong_trend = self.config.get('adx_strong_trend', self.ADX_STRONG_TREND)
        
        # Modyfikatory strategii
        self.strategy_modifiers = {
            MarketRegime.TRENDING_UP: {
                'position_size_multiplier': 1.2,
                'stop_loss_multiplier': 1.0,
                'preferred_patterns': ['trend_continuation', 'ema_pullback', 'breakout'],
                'avoid_patterns': ['rsi_reversal']
            },
            MarketRegime.TRENDING_DOWN: {
                'position_size_multiplier': 1.2,
                'stop_loss_multiplier': 1.0,
                'preferred_patterns': ['trend_continuation', 'ema_pullback', 'breakout'],
                'avoid_patterns': ['rsi_reversal']
            },
            MarketRegime.RANGING: {
                'position_size_multiplier': 0.8,
                'stop_loss_multiplier': 0.8,
                'preferred_patterns': ['rsi_reversal', 'support_resistance_bounce'],
                'avoid_patterns': ['breakout', 'momentum_shift']
            },
            MarketRegime.VOLATILE: {
                'position_size_multiplier': 0.5,
                'stop_loss_multiplier': 1.5,
                'preferred_patterns': [],
                'avoid_patterns': ['all']  # Unikaj tradingu
            },
            MarketRegime.UNKNOWN: {
                'position_size_multiplier': 0.7,
                'stop_loss_multiplier': 1.2,
                'preferred_patterns': [],
                'avoid_patterns': []
            }
        }
        
        # Cache
        self._cache: Dict[str, RegimeAnalysis] = {}
        
        logger.info("[OK] MarketRegimeDetector zainicjalizowany")
    
    def calculate_adx(self, df: pd.DataFrame, period: int = None) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Oblicza ADX, +DI i -DI
        
        Returns:
            (ADX, +DI, -DI)
        """
        if period is None:
            period = self.adx_period
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Directional Movement
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Smoothed averages
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * pd.Series(plus_dm).rolling(window=period).mean() / atr
        minus_di = 100 * pd.Series(minus_dm).rolling(window=period).mean() / atr
        
        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx, plus_di, minus_di
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = None, std: float = None) -> Dict:
        """
        Oblicza Bollinger Bands i szerokość
        
        Returns:
            Dict z upper, middle, lower, width, width_pct
        """
        if period is None:
            period = self.bb_period
        if std is None:
            std = self.bb_std
        
        close = df['close']
        
        middle = close.rolling(window=period).mean()
        rolling_std = close.rolling(window=period).std()
        
        upper = middle + (rolling_std * std)
        lower = middle - (rolling_std * std)
        
        # Szerokość jako % ceny
        width = upper - lower
        width_pct = (width / middle) * 100
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'width': width,
            'width_pct': width_pct
        }
    
    def analyze_regime(
        self,
        df: pd.DataFrame,
        symbol: str = 'UNKNOWN'
    ) -> RegimeAnalysis:
        """
        Analizuje reżim rynkowy
        
        Args:
            df: DataFrame z OHLCV
            symbol: Symbol pary
        
        Returns:
            RegimeAnalysis
        """
        try:
            if len(df) < self.lookback_periods:
                return self._unknown_regime()
            
            # Oblicz wskaźniki
            adx, plus_di, minus_di = self.calculate_adx(df)
            bb = self.calculate_bollinger_bands(df)
            
            # Pobierz ostatnie wartości
            current_adx = adx.iloc[-1]
            current_plus_di = plus_di.iloc[-1]
            current_minus_di = minus_di.iloc[-1]
            current_bb_width = bb['width_pct'].iloc[-1]
            
            # ADX trend (rising/falling)
            adx_sma = adx.rolling(5).mean()
            adx_trend = 'rising' if adx.iloc[-1] > adx_sma.iloc[-1] else 'falling'
            if abs(adx.iloc[-1] - adx_sma.iloc[-1]) < 1:
                adx_trend = 'flat'
            
            # BB width percentile
            bb_width_history = bb['width_pct'].iloc[-self.lookback_periods:]
            bb_width_percentile = (bb_width_history < current_bb_width).mean() * 100
            
            # Volatility ratio (ATR / price)
            atr = self._calculate_atr(df)
            volatility_ratio = (atr.iloc[-1] / df['close'].iloc[-1]) * 100
            
            # Trend strength (-100 to 100)
            if current_adx > self.adx_trend_threshold:
                trend_strength = current_adx if current_plus_di > current_minus_di else -current_adx
            else:
                trend_strength = 0
            
            # Klasyfikacja reżimu
            regime, confidence = self._classify_regime(
                adx=current_adx,
                plus_di=current_plus_di,
                minus_di=current_minus_di,
                bb_width_percentile=bb_width_percentile,
                volatility_ratio=volatility_ratio,
                adx_trend=adx_trend
            )
            
            # Rekomendacje
            recommendations = self._generate_recommendations(regime, confidence)
            
            analysis = RegimeAnalysis(
                regime=regime,
                confidence=confidence,
                adx=round(current_adx, 2) if not pd.isna(current_adx) else 0,
                adx_trend=adx_trend,
                bb_width=round(current_bb_width, 2) if not pd.isna(current_bb_width) else 0,
                bb_width_percentile=round(bb_width_percentile, 1),
                volatility_ratio=round(volatility_ratio, 3),
                trend_strength=round(trend_strength, 1),
                recommendations=recommendations
            )
            
            # Cache
            self._cache[symbol] = analysis
            
            logger.info(f"[UP] {symbol} Regime: {regime.value} (confidence: {confidence:.0f}%)")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Błąd analizy reżimu: {e}")
            return self._unknown_regime()
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Oblicza ATR"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        return tr.rolling(window=period).mean()
    
    def _classify_regime(
        self,
        adx: float,
        plus_di: float,
        minus_di: float,
        bb_width_percentile: float,
        volatility_ratio: float,
        adx_trend: str
    ) -> Tuple[MarketRegime, float]:
        """
        Klasyfikuje reżim rynkowy
        
        Returns:
            (MarketRegime, confidence)
        """
        # Handle NaN values
        if pd.isna(adx) or pd.isna(bb_width_percentile):
            return MarketRegime.UNKNOWN, 50
        
        # VOLATILE: Bardzo szeroki BB + ADX może być różny
        if bb_width_percentile >= self.BB_WIDTH_HIGH_PERCENTILE:
            if adx < self.adx_trend_threshold:
                # Wysoka zmienność bez trendu = VOLATILE
                confidence = min(90, 50 + bb_width_percentile - self.BB_WIDTH_HIGH_PERCENTILE)
                return MarketRegime.VOLATILE, confidence
        
        # TRENDING: Wysoki ADX
        if adx >= self.adx_trend_threshold:
            if plus_di > minus_di:
                # Uptrend
                confidence = min(95, 50 + adx)
                if adx >= self.adx_strong_trend:
                    confidence = min(98, confidence + 10)
                return MarketRegime.TRENDING_UP, confidence
            else:
                # Downtrend
                confidence = min(95, 50 + adx)
                if adx >= self.adx_strong_trend:
                    confidence = min(98, confidence + 10)
                return MarketRegime.TRENDING_DOWN, confidence
        
        # RANGING: Niski ADX + wąski BB
        if adx < self.adx_trend_threshold and bb_width_percentile <= self.BB_WIDTH_LOW_PERCENTILE:
            confidence = min(90, 50 + (self.adx_trend_threshold - adx) + (self.BB_WIDTH_LOW_PERCENTILE - bb_width_percentile) / 2)
            return MarketRegime.RANGING, confidence
        
        # Niski ADX ale szersze BB - może być początek breakoutu lub choppy
        if adx < self.adx_trend_threshold:
            if adx_trend == 'rising':
                # ADX rośnie - możliwy początek trendu
                confidence = 60
                if plus_di > minus_di:
                    return MarketRegime.TRENDING_UP, confidence
                else:
                    return MarketRegime.TRENDING_DOWN, confidence
            else:
                # Ranging z umiarkowaną zmiennością
                confidence = 70
                return MarketRegime.RANGING, confidence
        
        return MarketRegime.UNKNOWN, 50
    
    def _generate_recommendations(self, regime: MarketRegime, confidence: float) -> List[str]:
        """Generuje rekomendacje na podstawie reżimu"""
        recommendations = []
        
        if regime == MarketRegime.TRENDING_UP:
            recommendations.append("[OK] Preferuj pozycje LONG")
            recommendations.append("[OK] Używaj trend-following patterns")
            recommendations.append("[OK] Trzymaj zyski dłużej - trailing stop")
            if confidence >= 80:
                recommendations.append("[STRONG] Silny trend - można zwiększyć pozycję")
        
        elif regime == MarketRegime.TRENDING_DOWN:
            recommendations.append("[OK] Preferuj pozycje SHORT")
            recommendations.append("[OK] Używaj trend-following patterns")
            recommendations.append("[OK] Szybko ucinaj straty")
            if confidence >= 80:
                recommendations.append("[STRONG] Silny trend - można zwiększyć pozycję")
        
        elif regime == MarketRegime.RANGING:
            recommendations.append("[INFO] Używaj mean-reversion (RSI extremes)")
            recommendations.append("[INFO] Mniejsze pozycje")
            recommendations.append("[INFO] Szybkie TP przy S/R")
            recommendations.append("[WARNING] Unikaj breakout patterns")
        
        elif regime == MarketRegime.VOLATILE:
            recommendations.append("[WARNING] OSTROŻNOŚĆ - wysoka zmienność")
            recommendations.append("[WARNING] Zmniejsz pozycje o 50%")
            recommendations.append("[WARNING] Szersze stop lossy")
            recommendations.append("[WARNING] Rozważ pozostanie poza rynkiem")
        
        else:
            recommendations.append("[?] Niejednoznaczny reżim - zachowaj ostrożność")
            recommendations.append("[?] Zmniejsz pozycje")
        
        return recommendations
    
    def _unknown_regime(self) -> RegimeAnalysis:
        """Zwraca unknown regime dla błędów"""
        return RegimeAnalysis(
            regime=MarketRegime.UNKNOWN,
            confidence=0,
            adx=0,
            adx_trend='unknown',
            bb_width=0,
            bb_width_percentile=0,
            volatility_ratio=0,
            trend_strength=0,
            recommendations=["[?] Nie można określić reżimu - brak wystarczających danych"]
        )
    
    def get_strategy_modifiers(self, regime: MarketRegime) -> Dict:
        """
        Zwraca modyfikatory strategii dla danego reżimu
        
        Returns:
            Dict z modyfikatorami
        """
        return self.strategy_modifiers.get(regime, self.strategy_modifiers[MarketRegime.UNKNOWN])
    
    def should_trade(self, regime: MarketRegime, pattern_type: str = '') -> Tuple[bool, str]:
        """
        Sprawdza czy powinniśmy tradować w danym reżimie z danym patternem
        
        Returns:
            (should_trade, reason)
        """
        modifiers = self.get_strategy_modifiers(regime)
        
        # Sprawdź czy pattern jest w avoid list
        avoid = modifiers.get('avoid_patterns', [])
        if 'all' in avoid:
            return False, f"Reżim {regime.value} - unikaj tradingu"
        
        if pattern_type.lower() in [p.lower() for p in avoid]:
            return False, f"Pattern {pattern_type} nie zalecany w reżimie {regime.value}"
        
        # Preferowane patterny dają bonus
        preferred = modifiers.get('preferred_patterns', [])
        if pattern_type.lower() in [p.lower() for p in preferred]:
            return True, f"Pattern {pattern_type} preferowany w reżimie {regime.value}"
        
        return True, "OK"
    
    def get_position_size_modifier(self, regime: MarketRegime) -> float:
        """Zwraca mnożnik wielkości pozycji"""
        modifiers = self.get_strategy_modifiers(regime)
        return modifiers.get('position_size_multiplier', 1.0)
    
    def get_stop_loss_modifier(self, regime: MarketRegime) -> float:
        """Zwraca mnożnik stop loss (szerszy w volatile)"""
        modifiers = self.get_strategy_modifiers(regime)
        return modifiers.get('stop_loss_multiplier', 1.0)
    
    def get_cached_analysis(self, symbol: str) -> Optional[RegimeAnalysis]:
        """Zwraca cached analizę dla symbolu"""
        return self._cache.get(symbol)


if __name__ == "__main__":
    # Test modułu
    import yaml
    from data_fetcher import DataFetcher
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Test
    detector = MarketRegimeDetector(config)
    
    # Pobierz dane
    fetcher = DataFetcher(config)
    df = fetcher.get_klines('BTCUSDC', '15m', limit=200)
    
    if not df.empty:
        # Analiza
        analysis = detector.analyze_regime(df, 'BTCUSDC')
        
        print("\n[UP] Market Regime Analysis:")
        print(f"Regime: {analysis.regime.value}")
        print(f"Confidence: {analysis.confidence:.1f}%")
        print(f"ADX: {analysis.adx:.2f} ({analysis.adx_trend})")
        print(f"BB Width Percentile: {analysis.bb_width_percentile:.1f}%")
        print(f"Trend Strength: {analysis.trend_strength:.1f}")
        
        print("\n[CLIPBOARD] Recommendations:")
        for rec in analysis.recommendations:
            print(f"   {rec}")
        
        print("\n[GEAR] Strategy Modifiers:")
        modifiers = detector.get_strategy_modifiers(analysis.regime)
        for key, value in modifiers.items():
            print(f"   {key}: {value}")
    else:
        print("[ERROR] Could not fetch data")
