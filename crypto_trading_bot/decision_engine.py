"""
decision_engine.py - Silnik decyzyjny bota

Odpowiedzialny za:
- Ocenę scenariuszy na podstawie patternów
- Podejmowanie decyzji TRADE / NO TRADE
- Walidację warunków aktywacji/unieważnienia
- Priorytetyzację sygnałów
- Multi-timeframe confirmation
- Integrację z LLM Sentiment Analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np

from pattern_analyzer import PatternSignal, PatternType, SignalStrength

# Graceful import for LLM sentiment
try:
    from llm_sentiment import LLMSentimentAnalyzer, SentimentResult, get_llm_analyzer
    from news_fetcher import NewsFetcher
    HAS_LLM_MODULE = True
except ImportError:
    HAS_LLM_MODULE = False
    LLMSentimentAnalyzer = None
    SentimentResult = None

logger = logging.getLogger(__name__)


class Decision(Enum):
    """Decyzja tradingowa"""
    TRADE = "TRADE"
    NO_TRADE = "NO_TRADE"
    WAIT = "WAIT"  # Czekaj na potwierdzenie


@dataclass
class TradeRecommendation:
    """Rekomendacja tradingowa"""
    decision: Decision
    symbol: str
    direction: Optional[str]  # 'LONG' lub 'SHORT'
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    position_size: Optional[float]  # w USDC
    confidence: float
    risk_reward: float
    reasoning: List[str]
    patterns_used: List[PatternType]
    invalidation_price: Optional[float]
    timestamp: datetime = field(default_factory=datetime.now)
    # Score field for bonuses from technical levels, orderbook, etc.
    score: float = 0.0
    # LLM Sentiment fields
    llm_sentiment_score: Optional[float] = None
    llm_sentiment_reasoning: Optional[str] = None
    llm_veto_applied: bool = False
    llm_explanation: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'decision': self.decision.value,
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'position_size': self.position_size,
            'confidence': self.confidence,
            'risk_reward': self.risk_reward,
            'score': self.score,
            'reasoning': self.reasoning,
            'patterns_used': [p.value for p in self.patterns_used],
            'invalidation_price': self.invalidation_price,
            'timestamp': self.timestamp.isoformat(),
            'llm_sentiment_score': self.llm_sentiment_score,
            'llm_sentiment_reasoning': self.llm_sentiment_reasoning,
            'llm_veto_applied': self.llm_veto_applied,
            'llm_explanation': self.llm_explanation
        }


class DecisionEngine:
    """
    Silnik decyzyjny - ocenia sygnały i podejmuje decyzje
    
    Filozofia:
    - NIE handluj bez wyraźnej przewagi
    - Każda decyzja musi mieć jasne uzasadnienie
    - NO TRADE jest zawsze opcją
    - LLM sentiment może stosować veto przy silnym bearish sentiment
    
    Wagi decyzyjne (v2.0):
    - Technical Analysis: 60%
    - ML Prediction: 25%
    - LLM Sentiment: 15%
    """
    
    def __init__(self, config: dict):
        """
        Inicjalizacja silnika decyzyjnego
        
        Args:
            config: Konfiguracja z parametrami decyzji
        """
        self.config = config.get('decision', {})
        self.risk_config = config.get('risk', {})
        self.llm_config = config.get('llm', {})
        self.full_config = config
        
        # Parametry decyzyjne
        self.min_trade_score = self.config.get('min_trade_score', 60)
        self.min_risk_reward = self.risk_config.get('min_risk_reward', 1.5)
        self.trade_cooldown = self.config.get('trade_cooldown_minutes', 30)
        
        # Wagi czynników (Technical: 60%, ML: 25%, LLM: 15%)
        self.weights = self.config.get('weights', {
            'trend_alignment': 25,
            'pattern_strength': 25,
            'risk_reward': 20,
            'volume_confirmation': 15,
            'momentum': 15
        })
        
        # LLM Sentiment configuration
        self.llm_enabled = self.llm_config.get('enabled', False) and HAS_LLM_MODULE
        self.llm_sentiment_weight = self.llm_config.get('sentiment_weight', 0.15)  # 15%
        self.llm_veto_threshold = self.llm_config.get('veto_threshold', -0.7)
        self.llm_bonus_threshold = self.llm_config.get('bonus_threshold', 0.6)
        self.technical_bonus_threshold = 7.0  # Score techiczny dla bonusu
        
        # LLM components (lazy initialization)
        self._llm_analyzer: Optional[Any] = None
        self._news_fetcher: Optional[Any] = None
        self._cached_sentiment: Optional[Any] = None
        self._sentiment_cache_time: Optional[datetime] = None
        self._sentiment_cache_duration = timedelta(minutes=5)
        
        # Historia ostatnich decyzji (dla cooldown)
        self.last_trades: Dict[str, datetime] = {}
        
        logger.info(f"[OK] DecisionEngine zainicjalizowany (LLM: {'enabled' if self.llm_enabled else 'disabled'})")
    
    def _get_llm_analyzer(self) -> Optional[Any]:
        """Lazy initialization of LLM analyzer"""
        if not self.llm_enabled:
            return None
        
        if self._llm_analyzer is None:
            try:
                self._llm_analyzer = get_llm_analyzer(self.full_config)
            except Exception as e:
                logger.error(f"[ERROR] Błąd inicjalizacji LLM analyzer: {e}")
                return None
        
        return self._llm_analyzer
    
    def _get_news_fetcher(self) -> Optional[Any]:
        """Lazy initialization of news fetcher"""
        if not self.llm_enabled:
            return None
        
        if self._news_fetcher is None:
            try:
                self._news_fetcher = NewsFetcher(self.full_config)
            except Exception as e:
                logger.error(f"[ERROR] Błąd inicjalizacji NewsFetcher: {e}")
                return None
        
        return self._news_fetcher
    
    def _get_sentiment(self, symbol: str) -> Tuple[Optional[float], Optional[str], bool]:
        """
        Pobiera sentiment z LLM z cachowaniem
        
        Returns:
            (sentiment_score, reasoning, is_emergency)
        """
        if not self.llm_enabled:
            return None, None, False
        
        # Sprawdź cache
        now = datetime.now()
        if (self._cached_sentiment is not None and 
            self._sentiment_cache_time is not None and
            now - self._sentiment_cache_time < self._sentiment_cache_duration):
            result = self._cached_sentiment
            return result.score, result.reasoning, result.is_emergency
        
        # Pobierz nowy sentiment
        analyzer = self._get_llm_analyzer()
        fetcher = self._get_news_fetcher()
        
        if analyzer is None or fetcher is None:
            return None, None, False
        
        try:
            # Wyciągnij walutę z symbolu (np. BTCUSDC -> BTC)
            currency = symbol.replace('USDC', '').replace('USDT', '')
            
            # Pobierz newsy
            news = fetcher.get_latest_news(hours=12, currencies=[currency])
            
            if not news:
                logger.debug(f"Brak newsów dla {currency}")
                return None, None, False
            
            # Sprawdź emergency
            is_emergency, emergency_details = analyzer.emergency_detection(news)
            
            if is_emergency:
                logger.warning(f"[ALERT] Emergency detected for {symbol}!")
                return -1.0, emergency_details.get('reasoning', 'Emergency detected'), True
            
            # Analiza sentymentu
            sentiment = analyzer.analyze_news(news)
            
            if sentiment is None:
                return None, None, False
            
            # Cache result
            self._cached_sentiment = sentiment
            self._sentiment_cache_time = now
            
            return sentiment.score, sentiment.reasoning, sentiment.is_emergency
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd pobierania sentiment: {e}")
            return None, None, False
    
    def evaluate(
        self,
        symbol: str,
        patterns: List[PatternSignal],
        df_primary: pd.DataFrame,
        df_trend: Optional[pd.DataFrame] = None,
        current_positions: Optional[Dict] = None
    ) -> TradeRecommendation:
        """
        Główna metoda - ocenia sytuację i wydaje rekomendację
        
        Integruje:
        - Technical Analysis (60%)
        - ML Predictions (25%) - jeśli dostępne
        - LLM Sentiment (15%) - jeśli włączone
        
        Args:
            symbol: Para walutowa
            patterns: Lista wykrytych patternów
            df_primary: DataFrame z głównego timeframe
            df_trend: DataFrame z wyższego timeframe (opcjonalnie)
            current_positions: Aktualne pozycje (opcjonalnie)
        
        Returns:
            TradeRecommendation z decyzją
        """
        reasoning = []
        llm_sentiment_score = None
        llm_sentiment_reasoning = None
        llm_veto_applied = False
        llm_explanation = None
        
        # ========== LLM SENTIMENT CHECK ==========
        
        if self.llm_enabled:
            try:
                llm_sentiment_score, llm_sentiment_reasoning, is_emergency = self._get_sentiment(symbol)
                
                if llm_sentiment_score is not None:
                    reasoning.append(f"[BOT] LLM Sentiment: {llm_sentiment_score:.2f}")
                    
                    # Emergency veto - natychmiast blokuj trading
                    if is_emergency:
                        reasoning.append("[ALERT] EMERGENCY DETECTED - Trading halted")
                        return self._no_trade_recommendation(
                            symbol, reasoning,
                            llm_sentiment_score=llm_sentiment_score,
                            llm_sentiment_reasoning=llm_sentiment_reasoning,
                            llm_veto_applied=True
                        )
                    
                    # Veto rule: sentiment < -0.7 = NO TRADE
                    if llm_sentiment_score < self.llm_veto_threshold:
                        reasoning.append(f"[STOP] LLM VETO: Sentiment {llm_sentiment_score:.2f} < {self.llm_veto_threshold}")
                        llm_veto_applied = True
                        return self._no_trade_recommendation(
                            symbol, reasoning,
                            llm_sentiment_score=llm_sentiment_score,
                            llm_sentiment_reasoning=llm_sentiment_reasoning,
                            llm_veto_applied=True
                        )
                else:
                    reasoning.append("[BOT] LLM Sentiment: N/A (brak newsów)")
            except Exception as e:
                logger.warning(f"[WARNING] LLM sentiment failed: {e}")
                reasoning.append("[BOT] LLM Sentiment: Error (using fallback)")
        
        # ========== WSTĘPNE WALIDACJE ==========
        
        # 1. Cooldown check
        if symbol in self.last_trades:
            time_since_last = datetime.now() - self.last_trades[symbol]
            if time_since_last < timedelta(minutes=self.trade_cooldown):
                remaining = self.trade_cooldown - time_since_last.seconds // 60
                reasoning.append(f"[WAIT] Cooldown aktywny ({remaining} min pozostało)")
                return self._no_trade_recommendation(symbol, reasoning)
        
        # 2. Sprawdź czy są jakiekolwiek patterny
        if not patterns:
            reasoning.append("[ERROR] Brak wykrytych patternów")
            return self._no_trade_recommendation(symbol, reasoning)
        
        # 3. Sprawdź dane
        if df_primary.empty:
            reasoning.append("[ERROR] Brak danych rynkowych")
            return self._no_trade_recommendation(symbol, reasoning)
        
        # ========== MULTI-TIMEFRAME ANALYSIS ==========
        
        trend_direction = 0
        if df_trend is not None and not df_trend.empty:
            last_trend = df_trend.iloc[-1]
            if last_trend.get('ema_bullish_stack', False):
                trend_direction = 1
                reasoning.append("[UP] Higher TF: Bullish trend")
            elif last_trend.get('ema_bearish_stack', False):
                trend_direction = -1
                reasoning.append("[DOWN] Higher TF: Bearish trend")
            else:
                reasoning.append("-> Higher TF: No clear trend")
        
        # ========== FILTRACJA PATTERNÓW ==========
        
        # Filtruj patterny zgodne z trendem (jeśli jest trend)
        valid_patterns = []
        for pattern in patterns:
            if trend_direction == 1 and pattern.direction == 'SHORT':
                reasoning.append(f"[WARNING] {pattern.pattern_type.value} SHORT ignorowany (bullish HTF)")
                continue
            elif trend_direction == -1 and pattern.direction == 'LONG':
                reasoning.append(f"[WARNING] {pattern.pattern_type.value} LONG ignorowany (bearish HTF)")
                continue
            valid_patterns.append(pattern)
        
        if not valid_patterns:
            reasoning.append("[ERROR] Brak patternów zgodnych z trendem HTF")
            return self._no_trade_recommendation(symbol, reasoning)
        
        # ========== OCENA NAJLEPSZEGO PATTERNU ==========
        
        best_pattern = self._select_best_pattern(valid_patterns, df_primary)
        
        if best_pattern is None:
            reasoning.append("[ERROR] Żaden pattern nie spełnia minimalnych kryteriów")
            return self._no_trade_recommendation(symbol, reasoning)
        
        # ========== WALIDACJA RISK:REWARD ==========
        
        risk_reward = self._calculate_risk_reward(best_pattern)
        
        if risk_reward < self.min_risk_reward:
            reasoning.append(f"[ERROR] R:R {risk_reward:.2f} < minimum {self.min_risk_reward}")
            return self._no_trade_recommendation(symbol, reasoning)
        
        reasoning.append(f"[OK] R:R: {risk_reward:.2f}")
        
        # ========== OBLICZ KOŃCOWY SCORE (z LLM) ==========
        
        # Technical score (0-100)
        technical_score = self._calculate_final_score(
            best_pattern, df_primary, trend_direction
        )
        reasoning.append(f"[INFO] Technical score: {technical_score:.1f}/100")
        
        # Zastosuj wagi: Technical 60%, ML 25% (TODO), LLM 15%
        final_score = technical_score * 0.60
        
        # ML score placeholder (25%)
        ml_score = technical_score  # Fallback to technical if no ML
        final_score += ml_score * 0.25
        
        # LLM Sentiment contribution (15%)
        if llm_sentiment_score is not None:
            # Konwertuj sentiment (-1 do +1) na score (0-100)
            llm_score = (llm_sentiment_score + 1) * 50  # -1 -> 0, +1 -> 100
            final_score += llm_score * self.llm_sentiment_weight
            
            # Bonus: sentiment > +0.6 AND technical > 70 -> +5 points
            if llm_sentiment_score > self.llm_bonus_threshold and technical_score > 70:
                final_score += 5
                reasoning.append("[TARGET] Bonus: Strong sentiment + technical alignment")
        else:
            # Bez LLM, użyj neutralnego (50)
            final_score += 50 * self.llm_sentiment_weight
        
        reasoning.append(f"[INFO] Final score: {final_score:.1f}/100")
        
        # ========== DECYZJA ==========
        
        if final_score < self.min_trade_score:
            reasoning.append(f"[ERROR] Score {final_score:.1f} < minimum {self.min_trade_score}")
            return self._no_trade_recommendation(
                symbol, reasoning,
                llm_sentiment_score=llm_sentiment_score,
                llm_sentiment_reasoning=llm_sentiment_reasoning
            )
        
        # ========== REKOMENDACJA TRADE ==========
        
        reasoning.append(f"[OK] Pattern: {best_pattern.pattern_type.value}")
        reasoning.append(f"[OK] Direction: {best_pattern.direction}")
        reasoning.append(f"[OK] Supporting factors: {', '.join(best_pattern.supporting_factors[:3])}")
        
        # Pobierz wyjaśnienie LLM (opcjonalne)
        if self.llm_enabled:
            try:
                analyzer = self._get_llm_analyzer()
                if analyzer:
                    llm_explanation = analyzer.explain_trade({
                        'symbol': symbol,
                        'direction': best_pattern.direction,
                        'pattern': best_pattern.pattern_type.value,
                        'technical_score': technical_score,
                        'sentiment_score': llm_sentiment_score or 0,
                        'reasoning': reasoning[:5]
                    })
            except Exception as e:
                logger.debug(f"LLM explanation failed: {e}")
        
        # Zapisz czas trade'a dla cooldown
        self.last_trades[symbol] = datetime.now()
        
        return TradeRecommendation(
            decision=Decision.TRADE,
            symbol=symbol,
            direction=best_pattern.direction,
            entry_price=best_pattern.entry_price,
            stop_loss=best_pattern.stop_loss,
            take_profit=best_pattern.take_profit,
            position_size=None,  # Zostanie obliczone przez RiskManager
            confidence=best_pattern.confidence,
            risk_reward=risk_reward,
            score=final_score,  # Initialize with calculated final score
            reasoning=reasoning,
            patterns_used=[best_pattern.pattern_type],
            invalidation_price=best_pattern.stop_loss,
            llm_sentiment_score=llm_sentiment_score,
            llm_sentiment_reasoning=llm_sentiment_reasoning,
            llm_veto_applied=llm_veto_applied,
            llm_explanation=llm_explanation
        )
    
    def _select_best_pattern(
        self,
        patterns: List[PatternSignal],
        df: pd.DataFrame
    ) -> Optional[PatternSignal]:
        """
        Wybiera najlepszy pattern do tradingu
        
        Priorytet:
        1. Trend Continuation (najwyższa skuteczność)
        2. EMA Pullback (klasyczny setup)
        3. Volume Breakout (silne potwierdzenie)
        4. Momentum Shift
        5. RSI Reversal (najmniej pewny)
        """
        if not patterns:
            return None
        
        # Sortuj po confidence i sile
        scored_patterns = []
        
        priority_map = {
            PatternType.TREND_CONTINUATION: 5,
            PatternType.EMA_PULLBACK_BULLISH: 4,
            PatternType.EMA_PULLBACK_BEARISH: 4,
            PatternType.VOLUME_BREAKOUT_BULLISH: 3,
            PatternType.VOLUME_BREAKOUT_BEARISH: 3,
            PatternType.MOMENTUM_SHIFT_BULLISH: 2,
            PatternType.MOMENTUM_SHIFT_BEARISH: 2,
            PatternType.RSI_REVERSAL_BULLISH: 1,
            PatternType.RSI_REVERSAL_BEARISH: 1,
        }
        
        for pattern in patterns:
            priority = priority_map.get(pattern.pattern_type, 0)
            strength_score = pattern.strength.value * 10
            
            # Composite score
            score = (
                pattern.confidence * 0.5 +
                priority * 10 +
                strength_score
            )
            
            scored_patterns.append((score, pattern))
        
        # Sortuj malejąco
        scored_patterns.sort(key=lambda x: x[0], reverse=True)
        
        # Zwróć najlepszy (jeśli spełnia minimum)
        best_score, best_pattern = scored_patterns[0]
        
        if best_pattern.confidence >= 50:  # Minimum 50% confidence
            return best_pattern
        
        return None
    
    def _calculate_risk_reward(self, pattern: PatternSignal) -> float:
        """Oblicza stosunek Risk:Reward"""
        if pattern.direction == 'LONG':
            risk = pattern.entry_price - pattern.stop_loss
            reward = pattern.take_profit - pattern.entry_price
        else:
            risk = pattern.stop_loss - pattern.entry_price
            reward = pattern.entry_price - pattern.take_profit
        
        if risk <= 0:
            return 0
        
        return reward / risk
    
    def _calculate_final_score(
        self,
        pattern: PatternSignal,
        df: pd.DataFrame,
        trend_direction: int
    ) -> float:
        """
        Oblicza końcowy score dla decyzji
        
        Składniki:
        - Trend alignment
        - Pattern strength
        - Risk:Reward
        - Volume confirmation
        - Momentum
        """
        last = df.iloc[-1]
        score = 0
        
        # 1. Trend alignment (25 punktów)
        pattern_direction = 1 if pattern.direction == 'LONG' else -1
        
        if trend_direction == pattern_direction:
            score += self.weights['trend_alignment']
        elif trend_direction == 0:
            score += self.weights['trend_alignment'] * 0.5  # Neutralny trend
        # Przeciwny trend = 0 punktów
        
        # 2. Pattern strength (25 punktów)
        strength_pct = pattern.strength.value / 3.0
        score += self.weights['pattern_strength'] * strength_pct
        
        # 3. Risk:Reward (20 punktów)
        rr = self._calculate_risk_reward(pattern)
        if rr >= 2:
            score += self.weights['risk_reward']
        elif rr >= 1.5:
            score += self.weights['risk_reward'] * 0.8
        elif rr >= 1:
            score += self.weights['risk_reward'] * 0.5
        
        # 4. Volume confirmation (15 punktów)
        volume_ratio = last.get('volume_ratio', 0)
        if volume_ratio >= 1.5:
            score += self.weights['volume_confirmation']
        elif volume_ratio >= 1.2:
            score += self.weights['volume_confirmation'] * 0.7
        elif volume_ratio >= 1.0:
            score += self.weights['volume_confirmation'] * 0.5
        
        # 5. Momentum (15 punktów)
        if pattern.direction == 'LONG':
            if last.get('macd_hist_rising', False):
                score += self.weights['momentum']
            elif last.get('macd_above_signal', False):
                score += self.weights['momentum'] * 0.5
        else:
            if last.get('macd_hist_falling', False):
                score += self.weights['momentum']
            elif not last.get('macd_above_signal', True):
                score += self.weights['momentum'] * 0.5
        
        return score
    
    def _no_trade_recommendation(
        self,
        symbol: str,
        reasoning: List[str],
        llm_sentiment_score: Optional[float] = None,
        llm_sentiment_reasoning: Optional[str] = None,
        llm_veto_applied: bool = False
    ) -> TradeRecommendation:
        """Tworzy rekomendację NO TRADE"""
        return TradeRecommendation(
            decision=Decision.NO_TRADE,
            symbol=symbol,
            direction=None,
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            position_size=None,
            confidence=0,
            risk_reward=0,
            reasoning=reasoning,
            patterns_used=[],
            invalidation_price=None,
            llm_sentiment_score=llm_sentiment_score,
            llm_sentiment_reasoning=llm_sentiment_reasoning,
            llm_veto_applied=llm_veto_applied
        )
    
    def check_invalidation(
        self,
        recommendation: TradeRecommendation,
        current_price: float,
        df: pd.DataFrame
    ) -> Tuple[bool, str]:
        """
        Sprawdza czy warunki wejścia są nadal ważne
        
        Args:
            recommendation: Oryginalna rekomendacja
            current_price: Aktualna cena
            df: Aktualne dane z wskaźnikami
        
        Returns:
            (is_invalidated, reason)
        """
        if recommendation.invalidation_price is None:
            return False, ""
        
        # Price invalidation
        if recommendation.direction == 'LONG':
            if current_price < recommendation.invalidation_price:
                return True, f"Price {current_price} < invalidation {recommendation.invalidation_price}"
        else:
            if current_price > recommendation.invalidation_price:
                return True, f"Price {current_price} > invalidation {recommendation.invalidation_price}"
        
        # Struktura rynku się zmieniła
        if not df.empty:
            last = df.iloc[-1]
            
            if recommendation.direction == 'LONG':
                # Trend zmienił się na bearish
                if last.get('ema_bearish_stack', False):
                    return True, "EMA structure turned bearish"
                # MACD znacząco się pogorszył
                if last.get('macd_histogram', 0) < -0.001:
                    return True, "MACD turned significantly negative"
            else:
                if last.get('ema_bullish_stack', False):
                    return True, "EMA structure turned bullish"
                if last.get('macd_histogram', 0) > 0.001:
                    return True, "MACD turned significantly positive"
        
        return False, ""
    
    def should_take_profit_early(
        self,
        recommendation: TradeRecommendation,
        current_price: float,
        df: pd.DataFrame
    ) -> Tuple[bool, str]:
        """
        Sprawdza czy warto wziąć profit wcześniej
        
        Returns:
            (should_close, reason)
        """
        # WAŻNE: Sprawdź czy recommendation nie jest None
        if recommendation is None:
            return False, ""
        
        if recommendation.entry_price is None:
            return False, ""
        
        if recommendation.direction == 'LONG':
            pnl_pct = ((current_price - recommendation.entry_price) / recommendation.entry_price) * 100
        else:
            pnl_pct = ((recommendation.entry_price - current_price) / recommendation.entry_price) * 100
        
        # Zysk > 75% TP i momentum słabnie
        if pnl_pct > 0:
            target_reached = pnl_pct / ((recommendation.take_profit - recommendation.entry_price) / recommendation.entry_price * 100 * (1 if recommendation.direction == 'LONG' else -1))
            
            if not df.empty:
                last = df.iloc[-1]
                
                if target_reached > 0.75:
                    # Momentum słabnie
                    if recommendation.direction == 'LONG':
                        if last.get('macd_hist_falling', False) or last.get('rsi_overbought', False):
                            return True, f"75% TP reached ({pnl_pct:.2f}%) and momentum weakening"
                    else:
                        if last.get('macd_hist_rising', False) or last.get('rsi_oversold', False):
                            return True, f"75% TP reached ({pnl_pct:.2f}%) and momentum weakening"
        
        return False, ""
    
    def reset_cooldown(self, symbol: str):
        """Resetuje cooldown dla symbolu"""
        if symbol in self.last_trades:
            del self.last_trades[symbol]
            logger.info(f"[SYNC] Cooldown reset dla {symbol}")


if __name__ == "__main__":
    # Test modułu
    import yaml
    from data_fetcher import DataFetcher
    from indicators import TechnicalIndicators
    from pattern_analyzer import PatternAnalyzer
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Pobierz dane
    fetcher = DataFetcher(config)
    df_15m = fetcher.get_klines('BTCUSDC', '15m', limit=200)
    df_1h = fetcher.get_klines('BTCUSDC', '1h', limit=100)
    
    # Oblicz wskaźniki
    indicators = TechnicalIndicators(config)
    df_15m = indicators.calculate_all(df_15m)
    df_1h = indicators.calculate_all(df_1h)
    
    # Analizuj patterny
    analyzer = PatternAnalyzer(config)
    patterns = analyzer.analyze(df_15m, 'BTCUSDC')
    
    # Podejmij decyzję
    engine = DecisionEngine(config)
    recommendation = engine.evaluate(
        symbol='BTCUSDC',
        patterns=patterns,
        df_primary=df_15m,
        df_trend=df_1h
    )
    
    print(f"\n[TARGET] REKOMENDACJA dla BTCUSDC:")
    print(f"   Decision: {recommendation.decision.value}")
    print(f"   Direction: {recommendation.direction}")
    print(f"   Entry: {recommendation.entry_price}")
    print(f"   SL: {recommendation.stop_loss}")
    print(f"   TP: {recommendation.take_profit}")
    print(f"   Confidence: {recommendation.confidence}%")
    print(f"   R:R: {recommendation.risk_reward:.2f}")
    print(f"\n   Reasoning:")
    for r in recommendation.reasoning:
        print(f"     - {r}")
