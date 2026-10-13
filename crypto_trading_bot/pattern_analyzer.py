"""
pattern_analyzer.py - Moduł analizy patternów tradingowych

Odpowiedzialny za:
- Wykrywanie pullbacków do EMA
- Identyfikacja momentum shift na MACD
- Analiza RSI w kontekście trendu
- Potwierdzenie wolumenem
- Określanie warunków aktywacji i unieważnienia
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Typy rozpoznawanych patternów"""
    EMA_PULLBACK_BULLISH = "ema_pullback_bullish"
    EMA_PULLBACK_BEARISH = "ema_pullback_bearish"
    MOMENTUM_SHIFT_BULLISH = "momentum_shift_bullish"
    MOMENTUM_SHIFT_BEARISH = "momentum_shift_bearish"
    RSI_REVERSAL_BULLISH = "rsi_reversal_bullish"
    RSI_REVERSAL_BEARISH = "rsi_reversal_bearish"
    VOLUME_BREAKOUT_BULLISH = "volume_breakout_bullish"
    VOLUME_BREAKOUT_BEARISH = "volume_breakout_bearish"
    TREND_CONTINUATION = "trend_continuation"
    VWAP_BOUNCE_BULLISH = "vwap_bounce_bullish"
    VWAP_BOUNCE_BEARISH = "vwap_bounce_bearish"
    NO_PATTERN = "no_pattern"


class SignalStrength(Enum):
    """Siła sygnału"""
    STRONG = 3
    MODERATE = 2
    WEAK = 1
    NONE = 0


@dataclass
class PatternSignal:
    """Struktura sygnału z patternu"""
    pattern_type: PatternType
    direction: str  # 'LONG' lub 'SHORT'
    strength: SignalStrength
    confidence: float  # 0-100
    entry_price: float
    stop_loss: float
    take_profit: float
    invalidation_conditions: List[str]
    activation_conditions: List[str]
    supporting_factors: List[str]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            'pattern_type': self.pattern_type.value,
            'direction': self.direction,
            'strength': self.strength.value,
            'confidence': self.confidence,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'invalidation_conditions': self.invalidation_conditions,
            'activation_conditions': self.activation_conditions,
            'supporting_factors': self.supporting_factors,
            'timestamp': self.timestamp.isoformat()
        }


class PatternAnalyzer:
    """Analizator patternów tradingowych"""
    
    def __init__(self, config: dict):
        """
        Inicjalizacja analizatora
        
        Args:
            config: Konfiguracja z parametrami patternów
        """
        self.config = config.get('patterns', {})
        self.indicators_config = config.get('indicators', {})
        self.vwap_config = config.get('vwap', {})
        
        # Parametry patternów
        self.ema_pullback_max_atr = self.config.get('ema_pullback_max_atr', 0.5)
        self.momentum_shift_threshold = self.config.get('momentum_shift_threshold', 0.001)
        self.volume_confirmation_ratio = self.config.get('volume_confirmation_ratio', 1.2)
        self.min_pattern_win_rate = self.config.get('min_pattern_win_rate', 40)
        
        # Parametry VWAP
        self.vwap_enabled = self.vwap_config.get('enabled', True)
        self.vwap_use_in_breakouts = self.vwap_config.get('use_in_breakouts', True)
        self.vwap_bounce_enabled = self.vwap_config.get('bounce_pattern_enabled', True)
        self.vwap_touch_tolerance = self.vwap_config.get('touch_tolerance_pct', 0.2)
        self.vwap_bounce_volume_multiplier = self.vwap_config.get('bounce_volume_multiplier', 1.3)
        
        # Cache skuteczności patternów
        self.pattern_stats: Dict[str, Dict] = {}
        
        logger.info("[OK] PatternAnalyzer zainicjalizowany")
    
    def analyze(self, df: pd.DataFrame, symbol: str) -> List[PatternSignal]:
        """
        Główna metoda analizy - wykrywa wszystkie aktywne patterny
        
        Args:
            df: DataFrame z obliczonymi wskaźnikami
            symbol: Symbol pary (dla loggowania)
        
        Returns:
            Lista wykrytych patternów
        """
        if df.empty or len(df) < 50:
            logger.warning(f"Za mało danych dla {symbol}")
            return []
        
        patterns = []
        
        # Sprawdź różne typy patternów
        ema_pattern = self._check_ema_pullback(df, symbol)
        if ema_pattern:
            patterns.append(ema_pattern)
        
        momentum_pattern = self._check_momentum_shift(df, symbol)
        if momentum_pattern:
            patterns.append(momentum_pattern)
        
        rsi_pattern = self._check_rsi_reversal(df, symbol)
        if rsi_pattern:
            patterns.append(rsi_pattern)
        
        volume_pattern = self._check_volume_breakout(df, symbol)
        if volume_pattern:
            patterns.append(volume_pattern)
        
        # Sprawdź trend continuation
        continuation_pattern = self._check_trend_continuation(df, symbol)
        if continuation_pattern:
            patterns.append(continuation_pattern)
        
        # Sprawdź VWAP bounce pattern
        if self.vwap_bounce_enabled and self.vwap_enabled:
            vwap_pattern = self._check_vwap_bounce(df, symbol)
            if vwap_pattern:
                patterns.append(vwap_pattern)
        
        # Dostosuj confidence patternów na podstawie VWAP
        if self.vwap_enabled:
            patterns = self._adjust_confidence_by_vwap(patterns, df)
        
        # Filtruj patterny z niską skutecznością
        patterns = self._filter_by_effectiveness(patterns)
        
        logger.info(f"[UP] {symbol}: Wykryto {len(patterns)} patternów")
        return patterns
    
    def _check_ema_pullback(self, df: pd.DataFrame, symbol: str) -> Optional[PatternSignal]:
        """
        Sprawdza pullback do EMA jako potencjalny setup
        
        Logika:
        - Trend musi być ustalony (układ EMA)
        - Cena cofnęła się do EMA (w granicach ATR)
        - Świeca pokazuje odrzucenie (knot)
        - Volume potwierdza (nie za niski)
        """
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        
        atr = last.get('atr', 0)
        if atr == 0:
            return None
        
        # ========== BULLISH PULLBACK ==========
        if last.get('ema_bullish_stack', False):
            # Sprawdź czy cena dotknęła EMA
            ema_fast = last.get('ema_fast', 0)
            ema_medium = last.get('ema_medium', 0)
            
            # Odległość od EMA (w ATR)
            dist_to_ema = abs(last['low'] - ema_fast) / atr
            
            if dist_to_ema < self.ema_pullback_max_atr:
                # Sprawdź czy jest odrzucenie (bullish wick)
                body = abs(last['close'] - last['open'])
                lower_wick = min(last['open'], last['close']) - last['low']
                
                has_rejection = lower_wick > body * 0.5
                
                # Volume confirmation
                volume_ok = last.get('volume_ratio', 0) >= self.volume_confirmation_ratio * 0.8
                
                if has_rejection or volume_ok:
                    # Oblicz stop loss i take profit
                    sl = last['low'] - atr * 0.5
                    entry = last['close']
                    risk = entry - sl
                    tp = entry + risk * 1.5  # Min R:R 1:1.5
                    
                    supporting = []
                    if has_rejection:
                        supporting.append("Bullish rejection wick")
                    if volume_ok:
                        supporting.append(f"Volume ratio: {last.get('volume_ratio', 0):.2f}")
                    if last.get('rsi_oversold', False) or last.get('rsi', 50) < 45:
                        supporting.append("RSI favorable zone")
                    if last.get('macd_hist_rising', False):
                        supporting.append("MACD momentum rising")
                    
                    confidence = self._calculate_confidence(
                        trend_aligned=True,
                        has_rejection=has_rejection,
                        volume_confirmed=volume_ok,
                        rsi_favorable=last.get('rsi', 50) < 55,
                        macd_favorable=last.get('macd_hist_rising', False)
                    )
                    
                    return PatternSignal(
                        pattern_type=PatternType.EMA_PULLBACK_BULLISH,
                        direction='LONG',
                        strength=SignalStrength.STRONG if confidence > 70 else SignalStrength.MODERATE,
                        confidence=confidence,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit=tp,
                        invalidation_conditions=[
                            f"Cena zamknie poniżej {sl:.2f}",
                            "EMA stack zmieni się na bearish",
                            "Volume znacząco spadnie"
                        ],
                        activation_conditions=[
                            "Świeca zamknie powyżej entry",
                            "MACD histogram wzrośnie"
                        ],
                        supporting_factors=supporting
                    )
        
        # ========== BEARISH PULLBACK ==========
        if last.get('ema_bearish_stack', False):
            ema_fast = last.get('ema_fast', 0)
            
            dist_to_ema = abs(last['high'] - ema_fast) / atr
            
            if dist_to_ema < self.ema_pullback_max_atr:
                body = abs(last['close'] - last['open'])
                upper_wick = last['high'] - max(last['open'], last['close'])
                
                has_rejection = upper_wick > body * 0.5
                volume_ok = last.get('volume_ratio', 0) >= self.volume_confirmation_ratio * 0.8
                
                if has_rejection or volume_ok:
                    sl = last['high'] + atr * 0.5
                    entry = last['close']
                    risk = sl - entry
                    tp = entry - risk * 1.5
                    
                    supporting = []
                    if has_rejection:
                        supporting.append("Bearish rejection wick")
                    if volume_ok:
                        supporting.append(f"Volume ratio: {last.get('volume_ratio', 0):.2f}")
                    if last.get('rsi_overbought', False) or last.get('rsi', 50) > 55:
                        supporting.append("RSI in overbought zone")
                    if last.get('macd_hist_falling', False):
                        supporting.append("MACD momentum falling")
                    
                    confidence = self._calculate_confidence(
                        trend_aligned=True,
                        has_rejection=has_rejection,
                        volume_confirmed=volume_ok,
                        rsi_favorable=last.get('rsi', 50) > 45,
                        macd_favorable=last.get('macd_hist_falling', False)
                    )
                    
                    return PatternSignal(
                        pattern_type=PatternType.EMA_PULLBACK_BEARISH,
                        direction='SHORT',
                        strength=SignalStrength.STRONG if confidence > 70 else SignalStrength.MODERATE,
                        confidence=confidence,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit=tp,
                        invalidation_conditions=[
                            f"Cena zamknie powyżej {sl:.2f}",
                            "EMA stack zmieni się na bullish",
                            "Volume znacząco spadnie"
                        ],
                        activation_conditions=[
                            "Świeca zamknie poniżej entry",
                            "MACD histogram spadnie"
                        ],
                        supporting_factors=supporting
                    )
        
        return None
    
    def _check_momentum_shift(self, df: pd.DataFrame, symbol: str) -> Optional[PatternSignal]:
        """
        Sprawdza momentum shift na MACD histogram
        
        Logika:
        - MACD histogram zmienia kierunek
        - W kontekście większego trendu (na wyższym TF)
        - Potwierdzone wolumenem
        """
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        prev2 = df.iloc[-3] if len(df) > 2 else prev
        
        atr = last.get('atr', last['close'] * 0.02)
        
        # ========== BULLISH MOMENTUM SHIFT ==========
        if last.get('momentum_shift_bullish', False):
            # Histogram był ujemny i zaczął rosnąć
            hist_change = last['macd_histogram'] - prev['macd_histogram']
            
            if abs(hist_change) > self.momentum_shift_threshold:
                volume_ok = last.get('volume_ratio', 0) >= 1.0
                trend_support = last.get('above_trend_ema', False)
                
                supporting = [
                    f"MACD histogram shift: {hist_change:.6f}",
                ]
                if volume_ok:
                    supporting.append("Volume confirms")
                if trend_support:
                    supporting.append("Above trend EMA")
                if last.get('rsi_rising', False):
                    supporting.append("RSI rising")
                
                confidence = self._calculate_confidence(
                    trend_aligned=trend_support,
                    has_rejection=False,
                    volume_confirmed=volume_ok,
                    rsi_favorable=last.get('rsi', 50) < 60,
                    macd_favorable=True
                )
                
                sl = last['low'] - atr
                entry = last['close']
                tp = entry + (entry - sl) * 1.5
                
                return PatternSignal(
                    pattern_type=PatternType.MOMENTUM_SHIFT_BULLISH,
                    direction='LONG',
                    strength=SignalStrength.MODERATE,
                    confidence=confidence,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    invalidation_conditions=[
                        "MACD histogram wróci do spadania",
                        f"Cena spadnie poniżej {sl:.2f}",
                        "Volume znacząco spadnie"
                    ],
                    activation_conditions=[
                        "MACD histogram kontynuuje wzrost",
                        "Cena utrzyma się powyżej entry"
                    ],
                    supporting_factors=supporting
                )
        
        # ========== BEARISH MOMENTUM SHIFT ==========
        if last.get('momentum_shift_bearish', False):
            hist_change = prev['macd_histogram'] - last['macd_histogram']
            
            if abs(hist_change) > self.momentum_shift_threshold:
                volume_ok = last.get('volume_ratio', 0) >= 1.0
                trend_support = last.get('below_trend_ema', False)
                
                supporting = [
                    f"MACD histogram shift: {-hist_change:.6f}",
                ]
                if volume_ok:
                    supporting.append("Volume confirms")
                if trend_support:
                    supporting.append("Below trend EMA")
                if not last.get('rsi_rising', True):
                    supporting.append("RSI falling")
                
                confidence = self._calculate_confidence(
                    trend_aligned=trend_support,
                    has_rejection=False,
                    volume_confirmed=volume_ok,
                    rsi_favorable=last.get('rsi', 50) > 40,
                    macd_favorable=True
                )
                
                sl = last['high'] + atr
                entry = last['close']
                tp = entry - (sl - entry) * 1.5
                
                return PatternSignal(
                    pattern_type=PatternType.MOMENTUM_SHIFT_BEARISH,
                    direction='SHORT',
                    strength=SignalStrength.MODERATE,
                    confidence=confidence,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    invalidation_conditions=[
                        "MACD histogram wróci do wzrostu",
                        f"Cena wzrośnie powyżej {sl:.2f}",
                        "Volume znacząco spadnie"
                    ],
                    activation_conditions=[
                        "MACD histogram kontynuuje spadek",
                        "Cena utrzyma się poniżej entry"
                    ],
                    supporting_factors=supporting
                )
        
        return None
    
    def _check_rsi_reversal(self, df: pd.DataFrame, symbol: str) -> Optional[PatternSignal]:
        """
        Sprawdza reversal RSI W KONTEKŚCIE TRENDU
        
        Logika:
        - RSI w strefie oversold/overbought to WARUNEK, nie sygnał
        - Musi być w kierunku głównego trendu
        - Potwierdzone ceną (rejection) i wolumenem
        """
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        
        atr = last.get('atr', last['close'] * 0.02)
        
        # ========== BULLISH RSI REVERSAL ==========
        # RSI był oversold i zaczyna rosnąć, W TRENDZIE WZROSTOWYM
        if (prev.get('rsi_oversold', False) or prev.get('rsi', 50) < 35):
            if last.get('rsi_rising', False) and last.get('rsi', 0) > prev.get('rsi', 0):
                # Musi być w kontekście bullish (powyżej trend EMA)
                trend_context = last.get('above_trend_ema', False)
                
                # Lub lokalne dno z odrzuceniem
                lower_wick = min(last['open'], last['close']) - last['low']
                body = abs(last['close'] - last['open'])
                has_rejection = lower_wick > body * 0.3
                
                if trend_context or has_rejection:
                    volume_ok = last.get('volume_ratio', 0) >= 0.8
                    
                    supporting = [
                        f"RSI odbija z {prev.get('rsi', 0):.1f}",
                    ]
                    if trend_context:
                        supporting.append("Powyżej trend EMA - kontekst bullish")
                    if has_rejection:
                        supporting.append("Bullish rejection wick")
                    if volume_ok:
                        supporting.append("Volume adequate")
                    if last.get('stoch_bullish_cross', False):
                        supporting.append("Stoch RSI bullish cross")
                    
                    confidence = self._calculate_confidence(
                        trend_aligned=trend_context,
                        has_rejection=has_rejection,
                        volume_confirmed=volume_ok,
                        rsi_favorable=True,
                        macd_favorable=last.get('macd_hist_rising', False)
                    )
                    
                    sl = last['low'] - atr * 0.5
                    entry = last['close']
                    tp = entry + (entry - sl) * 1.5
                    
                    return PatternSignal(
                        pattern_type=PatternType.RSI_REVERSAL_BULLISH,
                        direction='LONG',
                        strength=SignalStrength.MODERATE if confidence > 60 else SignalStrength.WEAK,
                        confidence=confidence,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit=tp,
                        invalidation_conditions=[
                            "RSI wróci poniżej 25",
                            f"Cena spadnie poniżej {sl:.2f}",
                            "Stoch RSI bearish cross"
                        ],
                        activation_conditions=[
                            "RSI kontynuuje wzrost powyżej 35",
                            "Cena utrzyma się powyżej entry"
                        ],
                        supporting_factors=supporting
                    )
        
        # ========== BEARISH RSI REVERSAL ==========
        if (prev.get('rsi_overbought', False) or prev.get('rsi', 50) > 65):
            if not last.get('rsi_rising', True) and last.get('rsi', 100) < prev.get('rsi', 100):
                trend_context = last.get('below_trend_ema', False)
                
                upper_wick = last['high'] - max(last['open'], last['close'])
                body = abs(last['close'] - last['open'])
                has_rejection = upper_wick > body * 0.3
                
                if trend_context or has_rejection:
                    volume_ok = last.get('volume_ratio', 0) >= 0.8
                    
                    supporting = [
                        f"RSI spada z {prev.get('rsi', 0):.1f}",
                    ]
                    if trend_context:
                        supporting.append("Poniżej trend EMA - kontekst bearish")
                    if has_rejection:
                        supporting.append("Bearish rejection wick")
                    if volume_ok:
                        supporting.append("Volume adequate")
                    if last.get('stoch_bearish_cross', False):
                        supporting.append("Stoch RSI bearish cross")
                    
                    confidence = self._calculate_confidence(
                        trend_aligned=trend_context,
                        has_rejection=has_rejection,
                        volume_confirmed=volume_ok,
                        rsi_favorable=True,
                        macd_favorable=last.get('macd_hist_falling', False)
                    )
                    
                    sl = last['high'] + atr * 0.5
                    entry = last['close']
                    tp = entry - (sl - entry) * 1.5
                    
                    return PatternSignal(
                        pattern_type=PatternType.RSI_REVERSAL_BEARISH,
                        direction='SHORT',
                        strength=SignalStrength.MODERATE if confidence > 60 else SignalStrength.WEAK,
                        confidence=confidence,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit=tp,
                        invalidation_conditions=[
                            "RSI wróci powyżej 75",
                            f"Cena wzrośnie powyżej {sl:.2f}",
                            "Stoch RSI bullish cross"
                        ],
                        activation_conditions=[
                            "RSI kontynuuje spadek poniżej 65",
                            "Cena utrzyma się poniżej entry"
                        ],
                        supporting_factors=supporting
                    )
        
        return None
    
    def _check_volume_breakout(self, df: pd.DataFrame, symbol: str) -> Optional[PatternSignal]:
        """
        Sprawdza breakout z wysokim wolumenem
        
        Logika:
        - Volume spike (> 1.5x średniej)
        - W kierunku trendu
        - Świeca potwierdza kierunek
        """
        last = df.iloc[-1]
        atr = last.get('atr', last['close'] * 0.02)
        
        if not last.get('volume_spike', False):
            return None
        
        # ========== BULLISH VOLUME BREAKOUT ==========
        if last.get('high_volume_bullish', False):
            trend_aligned = last.get('ema_bullish_stack', False) or last.get('above_trend_ema', False)
            
            if trend_aligned:
                supporting = [
                    f"Volume spike: {last.get('volume_ratio', 0):.2f}x average",
                    "Bullish candle with high volume"
                ]
                
                if last.get('macd_hist_rising', False):
                    supporting.append("MACD confirms")
                if last.get('rsi', 50) < 65:
                    supporting.append("RSI has room to rise")
                
                confidence = self._calculate_confidence(
                    trend_aligned=trend_aligned,
                    has_rejection=False,
                    volume_confirmed=True,
                    rsi_favorable=last.get('rsi', 50) < 70,
                    macd_favorable=last.get('macd_above_signal', False)
                )
                
                sl = last['low'] - atr * 0.3
                entry = last['close']
                tp = entry + (entry - sl) * 1.5
                
                return PatternSignal(
                    pattern_type=PatternType.VOLUME_BREAKOUT_BULLISH,
                    direction='LONG',
                    strength=SignalStrength.STRONG if confidence > 70 else SignalStrength.MODERATE,
                    confidence=confidence,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    invalidation_conditions=[
                        f"Cena spadnie poniżej {sl:.2f}",
                        "Volume spadnie poniżej średniej",
                        "Następna świeca będzie bearish"
                    ],
                    activation_conditions=[
                        "Następna świeca potwierdzi kierunek",
                        "Volume utrzyma się powyżej średniej"
                    ],
                    supporting_factors=supporting
                )
        
        # ========== BEARISH VOLUME BREAKOUT ==========
        if last.get('high_volume_bearish', False):
            trend_aligned = last.get('ema_bearish_stack', False) or last.get('below_trend_ema', False)
            
            if trend_aligned:
                supporting = [
                    f"Volume spike: {last.get('volume_ratio', 0):.2f}x average",
                    "Bearish candle with high volume"
                ]
                
                if last.get('macd_hist_falling', False):
                    supporting.append("MACD confirms")
                if last.get('rsi', 50) > 35:
                    supporting.append("RSI has room to fall")
                
                confidence = self._calculate_confidence(
                    trend_aligned=trend_aligned,
                    has_rejection=False,
                    volume_confirmed=True,
                    rsi_favorable=last.get('rsi', 50) > 30,
                    macd_favorable=not last.get('macd_above_signal', True)
                )
                
                sl = last['high'] + atr * 0.3
                entry = last['close']
                tp = entry - (sl - entry) * 1.5
                
                return PatternSignal(
                    pattern_type=PatternType.VOLUME_BREAKOUT_BEARISH,
                    direction='SHORT',
                    strength=SignalStrength.STRONG if confidence > 70 else SignalStrength.MODERATE,
                    confidence=confidence,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    invalidation_conditions=[
                        f"Cena wzrośnie powyżej {sl:.2f}",
                        "Volume spadnie poniżej średniej",
                        "Następna świeca będzie bullish"
                    ],
                    activation_conditions=[
                        "Następna świeca potwierdzi kierunek",
                        "Volume utrzyma się powyżej średniej"
                    ],
                    supporting_factors=supporting
                )
        
        return None
    
    def _check_trend_continuation(self, df: pd.DataFrame, symbol: str) -> Optional[PatternSignal]:
        """
        Sprawdza prosty setup kontynuacji trendu
        
        Logika:
        - Silny trend (wysoki trend_strength)
        - Wszystkie wskaźniki zgodne
        - Brak sygnałów odwrócenia
        """
        last = df.iloc[-1]
        atr = last.get('atr', last['close'] * 0.02)
        
        trend_strength = last.get('trend_strength', 0)
        
        if trend_strength < 70:
            return None
        
        # ========== BULLISH CONTINUATION ==========
        if last.get('ema_bullish_stack', False):
            all_aligned = (
                last.get('macd_above_signal', False) and
                last.get('macd_above_zero', False) and
                last.get('rsi', 50) > 50 and
                last.get('rsi', 50) < 70 and
                last.get('obv_trend_up', False)
            )
            
            if all_aligned:
                supporting = [
                    f"Trend strength: {trend_strength}%",
                    "All indicators aligned bullish",
                    "EMA bullish stack confirmed"
                ]
                
                confidence = min(90, trend_strength + 10)
                
                sl = last['ema_medium'] - atr * 0.5
                entry = last['close']
                tp = entry + (entry - sl) * 2  # R:R 1:2 dla trend continuation
                
                return PatternSignal(
                    pattern_type=PatternType.TREND_CONTINUATION,
                    direction='LONG',
                    strength=SignalStrength.STRONG,
                    confidence=confidence,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    invalidation_conditions=[
                        "EMA stack breaks down",
                        f"Price closes below {sl:.2f}",
                        "RSI drops below 40"
                    ],
                    activation_conditions=[
                        "Trend continues with momentum",
                        "Volume stays above average"
                    ],
                    supporting_factors=supporting
                )
        
        # ========== BEARISH CONTINUATION ==========
        if last.get('ema_bearish_stack', False):
            all_aligned = (
                not last.get('macd_above_signal', True) and
                not last.get('macd_above_zero', True) and
                last.get('rsi', 50) < 50 and
                last.get('rsi', 50) > 30 and
                not last.get('obv_trend_up', True)
            )
            
            if all_aligned:
                supporting = [
                    f"Trend strength: {trend_strength}%",
                    "All indicators aligned bearish",
                    "EMA bearish stack confirmed"
                ]
                
                confidence = min(90, trend_strength + 10)
                
                sl = last['ema_medium'] + atr * 0.5
                entry = last['close']
                tp = entry - (sl - entry) * 2
                
                return PatternSignal(
                    pattern_type=PatternType.TREND_CONTINUATION,
                    direction='SHORT',
                    strength=SignalStrength.STRONG,
                    confidence=confidence,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    invalidation_conditions=[
                        "EMA stack breaks up",
                        f"Price closes above {sl:.2f}",
                        "RSI rises above 60"
                    ],
                    activation_conditions=[
                        "Trend continues with momentum",
                        "Volume stays above average"
                    ],
                    supporting_factors=supporting
                )
        
        return None
    
    def _calculate_confidence(
        self,
        trend_aligned: bool,
        has_rejection: bool,
        volume_confirmed: bool,
        rsi_favorable: bool,
        macd_favorable: bool
    ) -> float:
        """
        Oblicza confidence score dla patternu
        
        Returns:
            Score 0-100
        """
        score = 0
        
        # Trend alignment - najważniejsze (30 punktów)
        if trend_aligned:
            score += 30
        
        # Price action rejection (20 punktów)
        if has_rejection:
            score += 20
        
        # Volume confirmation (20 punktów)
        if volume_confirmed:
            score += 20
        
        # RSI w dobrej strefie (15 punktów)
        if rsi_favorable:
            score += 15
        
        # MACD zgodny (15 punktów)
        if macd_favorable:
            score += 15
        
        return min(100, score)
    
    def _check_vwap_bounce(self, df: pd.DataFrame, symbol: str) -> Optional[PatternSignal]:
        """
        Sprawdza VWAP Bounce pattern
        
        Logika:
        - Cena dotyka VWAP (+/-0.2%)
        - Wolumen > 1.3x średnia
        - RSI potwierdza kierunek
        - VWAP działa jako dynamiczne wsparcie/opór
        
        Score: 7.5-9.0
        """
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        
        atr = last.get('atr', last['close'] * 0.02)
        
        # Znajdź aktywny VWAP
        vwap_col = None
        for col in ['vwap_daily', 'vwap_asian', 'vwap_european', 'vwap_us']:
            if col in df.columns and not np.isnan(last.get(col, np.nan)):
                vwap_col = col
                break
        
        if vwap_col is None:
            return None
        
        vwap = last[vwap_col]
        price = last['close']
        
        # Sprawdź czy cena dotyka VWAP
        distance_pct = abs((price - vwap) / vwap) * 100
        touching_vwap = distance_pct < self.vwap_touch_tolerance
        
        if not touching_vwap:
            return None
        
        # Sprawdź volume confirmation
        volume_ratio = last.get('volume_ratio', 0)
        volume_ok = volume_ratio >= self.vwap_bounce_volume_multiplier
        
        if not volume_ok:
            return None
        
        # Określ kierunek bounce na podstawie poprzedniej świecy i RSI
        prev_distance = ((prev['close'] - prev.get(vwap_col, vwap)) / vwap) * 100
        
        # ========== BULLISH VWAP BOUNCE ==========
        # Cena przyszła z dołu (była poniżej VWAP) i teraz odbija
        if prev_distance < -self.vwap_touch_tolerance:
            # RSI potwierdza bullish
            rsi = last.get('rsi', 50)
            rsi_confirms = rsi < 60  # Nie jest overbought
            
            # Candle pokazuje odrzucenie
            lower_wick = min(last['open'], last['close']) - last['low']
            body = abs(last['close'] - last['open'])
            has_rejection = lower_wick > body * 0.3
            
            if rsi_confirms and (has_rejection or last['close'] > last['open']):
                supporting = [
                    f"VWAP bounce ({vwap_col.replace('vwap_', '')} session)",
                    f"Volume ratio: {volume_ratio:.2f}x",
                    f"RSI: {rsi:.1f}"
                ]
                
                if has_rejection:
                    supporting.append("Bullish rejection wick")
                if last.get('macd_hist_rising', False):
                    supporting.append("MACD momentum rising")
                
                # Confidence: bazowy 75% + bonusy
                confidence = 75
                if has_rejection:
                    confidence += 5
                if last.get('macd_hist_rising', False):
                    confidence += 5
                if last.get('above_trend_ema', False):
                    confidence += 5
                
                confidence = min(90, confidence)
                
                sl = vwap - atr * 0.5
                entry = last['close']
                tp = entry + (entry - sl) * 1.5
                
                return PatternSignal(
                    pattern_type=PatternType.VWAP_BOUNCE_BULLISH,
                    direction='LONG',
                    strength=SignalStrength.STRONG if confidence >= 80 else SignalStrength.MODERATE,
                    confidence=confidence,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    invalidation_conditions=[
                        f"Cena zamknie poniżej VWAP ({vwap:.2f})",
                        f"Volume spadnie poniżej średniej",
                        f"Stop loss: {sl:.2f}"
                    ],
                    activation_conditions=[
                        "Cena pozostanie powyżej VWAP",
                        "MACD histogram wzrośnie"
                    ],
                    supporting_factors=supporting
                )
        
        # ========== BEARISH VWAP BOUNCE ==========
        # Cena przyszła z góry (była powyżej VWAP) i teraz odbija w dół
        if prev_distance > self.vwap_touch_tolerance:
            rsi = last.get('rsi', 50)
            rsi_confirms = rsi > 40  # Nie jest oversold
            
            upper_wick = last['high'] - max(last['open'], last['close'])
            body = abs(last['close'] - last['open'])
            has_rejection = upper_wick > body * 0.3
            
            if rsi_confirms and (has_rejection or last['close'] < last['open']):
                supporting = [
                    f"VWAP bounce ({vwap_col.replace('vwap_', '')} session)",
                    f"Volume ratio: {volume_ratio:.2f}x",
                    f"RSI: {rsi:.1f}"
                ]
                
                if has_rejection:
                    supporting.append("Bearish rejection wick")
                if last.get('macd_hist_falling', False):
                    supporting.append("MACD momentum falling")
                
                confidence = 75
                if has_rejection:
                    confidence += 5
                if last.get('macd_hist_falling', False):
                    confidence += 5
                if last.get('below_trend_ema', False):
                    confidence += 5
                
                confidence = min(90, confidence)
                
                sl = vwap + atr * 0.5
                entry = last['close']
                tp = entry - (sl - entry) * 1.5
                
                return PatternSignal(
                    pattern_type=PatternType.VWAP_BOUNCE_BEARISH,
                    direction='SHORT',
                    strength=SignalStrength.STRONG if confidence >= 80 else SignalStrength.MODERATE,
                    confidence=confidence,
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    invalidation_conditions=[
                        f"Cena zamknie powyżej VWAP ({vwap:.2f})",
                        f"Volume spadnie poniżej średniej",
                        f"Stop loss: {sl:.2f}"
                    ],
                    activation_conditions=[
                        "Cena pozostanie poniżej VWAP",
                        "MACD histogram spadnie"
                    ],
                    supporting_factors=supporting
                )
        
        return None
    
    def _adjust_confidence_by_vwap(
        self,
        patterns: List[PatternSignal],
        df: pd.DataFrame
    ) -> List[PatternSignal]:
        """
        Dostosowuje confidence patternów na podstawie pozycji względem VWAP
        
        Logika:
        - +0.5 punktu (do confidence) jeśli trade zgodny z VWAP
        - -0.5 punktu jeśli trade przeciwny do VWAP
        
        Args:
            patterns: Lista patternów
            df: DataFrame z danymi
        
        Returns:
            Lista patternów z dostosowanym confidence
        """
        if df.empty:
            return patterns
        
        last = df.iloc[-1]
        
        # Znajdź pozycję względem VWAP
        above_vwap = last.get('above_vwap', None)
        
        if above_vwap is None:
            return patterns
        
        adjusted = []
        for pattern in patterns:
            # Kopia patternu z możliwością modyfikacji
            new_pattern = pattern
            adjustment = 0
            
            if pattern.direction == 'LONG':
                if above_vwap:
                    # Long powyżej VWAP = zgodny z bullish sentiment
                    adjustment = 5
                    if 'VWAP confirms bullish position' not in pattern.supporting_factors:
                        new_supporting = list(pattern.supporting_factors)
                        new_supporting.append('VWAP confirms bullish position')
                else:
                    # Long poniżej VWAP = przeciwny
                    adjustment = -5
            
            elif pattern.direction == 'SHORT':
                if not above_vwap:
                    # Short poniżej VWAP = zgodny z bearish sentiment
                    adjustment = 5
                    if 'VWAP confirms bearish position' not in pattern.supporting_factors:
                        new_supporting = list(pattern.supporting_factors)
                        new_supporting.append('VWAP confirms bearish position')
                else:
                    # Short powyżej VWAP = przeciwny
                    adjustment = -5
            
            # Zastosuj adjustment
            if adjustment != 0:
                new_confidence = max(0, min(100, pattern.confidence + adjustment))
                
                # Aktualizuj strength jeśli confidence się znacząco zmieniło
                if new_confidence >= 70 and pattern.strength == SignalStrength.MODERATE:
                    new_strength = SignalStrength.STRONG
                elif new_confidence < 60 and pattern.strength == SignalStrength.STRONG:
                    new_strength = SignalStrength.MODERATE
                else:
                    new_strength = pattern.strength
                
                # Utwórz nowy PatternSignal z zaktualizowanymi wartościami
                new_pattern = PatternSignal(
                    pattern_type=pattern.pattern_type,
                    direction=pattern.direction,
                    strength=new_strength,
                    confidence=new_confidence,
                    entry_price=pattern.entry_price,
                    stop_loss=pattern.stop_loss,
                    take_profit=pattern.take_profit,
                    invalidation_conditions=pattern.invalidation_conditions,
                    activation_conditions=pattern.activation_conditions,
                    supporting_factors=new_supporting if adjustment > 0 else pattern.supporting_factors,
                    timestamp=pattern.timestamp
                )
            
            adjusted.append(new_pattern)
        
        return adjusted
    
    def _filter_by_effectiveness(self, patterns: List[PatternSignal]) -> List[PatternSignal]:
        """
        Filtruje patterny na podstawie historycznej skuteczności
        
        Args:
            patterns: Lista wykrytych patternów
        
        Returns:
            Przefiltrowana lista
        """
        filtered = []
        
        for pattern in patterns:
            pattern_name = pattern.pattern_type.value
            
            # Sprawdź statystyki
            if pattern_name in self.pattern_stats:
                stats = self.pattern_stats[pattern_name]
                win_rate = stats.get('win_rate', 50)
                
                if win_rate < self.min_pattern_win_rate:
                    logger.info(f"[WARNING] Pattern {pattern_name} pomięty (win rate: {win_rate}%)")
                    continue
            
            filtered.append(pattern)
        
        return filtered
    
    def update_pattern_stats(self, pattern_type: str, was_successful: bool):
        """
        Aktualizuje statystyki patternu
        
        Args:
            pattern_type: Typ patternu
            was_successful: Czy trade był zyskowny
        """
        if pattern_type not in self.pattern_stats:
            self.pattern_stats[pattern_type] = {
                'total': 0,
                'wins': 0,
                'win_rate': 50.0
            }
        
        stats = self.pattern_stats[pattern_type]
        stats['total'] += 1
        if was_successful:
            stats['wins'] += 1
        
        stats['win_rate'] = (stats['wins'] / stats['total']) * 100
        
        logger.info(f"[INFO] {pattern_type} stats: {stats['wins']}/{stats['total']} ({stats['win_rate']:.1f}%)")


if __name__ == "__main__":
    # Test modułu
    import yaml
    from data_fetcher import DataFetcher
    from indicators import TechnicalIndicators
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Pobierz dane
    fetcher = DataFetcher(config)
    df = fetcher.get_klines('BTCUSDC', '15m', limit=200)
    
    # Oblicz wskaźniki
    indicators = TechnicalIndicators(config)
    df = indicators.calculate_all(df)
    
    # Analizuj patterny
    analyzer = PatternAnalyzer(config)
    patterns = analyzer.analyze(df, 'BTCUSDC')
    
    print(f"\n[SCAN] Wykryto {len(patterns)} patternów:")
    for pattern in patterns:
        print(f"\n  [UP] {pattern.pattern_type.value}")
        print(f"     Direction: {pattern.direction}")
        print(f"     Confidence: {pattern.confidence}%")
        print(f"     Entry: {pattern.entry_price:.2f}")
        print(f"     SL: {pattern.stop_loss:.2f}")
        print(f"     TP: {pattern.take_profit:.2f}")
        print(f"     Supporting: {', '.join(pattern.supporting_factors)}")
