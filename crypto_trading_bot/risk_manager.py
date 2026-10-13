"""
risk_manager.py - Moduł zarządzania ryzykiem

Odpowiedzialny za:
- Kalkulację wielkości pozycji
- Zarządzanie Stop Loss / Take Profit
- Monitorowanie drawdown
- Limity dzienne (trade'ów i strat)
- Emergency stop przy anomaliach
- Trailing stop
- Kelly Criterion Position Sizing (v3.0)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import json
import os
import statistics

logger = logging.getLogger(__name__)


# ============================================
# KELLY CRITERION POSITION SIZING
# ============================================

@dataclass
class KellyResult:
    """Wynik kalkulacji Kelly Criterion"""
    kelly_fraction: float  # Surowa Kelly fraction
    half_kelly: float  # Half-Kelly (bezpieczniejsza)
    optimal_position_pct: float  # Sugerowany % kapitału
    win_rate: float  # Historical win rate
    avg_win_rr: float  # Average win in R:R
    avg_loss_rr: float  # Average loss in R:R
    trades_analyzed: int  # Liczba trade'ów użytych do kalkulacji
    confidence: str  # 'HIGH', 'MEDIUM', 'LOW'
    fallback_used: bool  # True jeśli użyto fixed %
    
    def to_dict(self) -> Dict:
        return {
            'kelly_fraction': round(self.kelly_fraction, 4),
            'half_kelly': round(self.half_kelly, 4),
            'optimal_position_pct': round(self.optimal_position_pct, 2),
            'win_rate': round(self.win_rate, 2),
            'avg_win_rr': round(self.avg_win_rr, 2),
            'avg_loss_rr': round(self.avg_loss_rr, 2),
            'trades_analyzed': self.trades_analyzed,
            'confidence': self.confidence,
            'fallback_used': self.fallback_used
        }


class KellyCalculator:
    """
    Kalkulator Kelly Criterion dla optymalnego position sizing.
    
    Kelly formula: f* = (p * b - q) / b
    Gdzie:
    - p = probability of winning (win_rate)
    - q = probability of losing (1 - p)
    - b = ratio of win/loss (avg_win / avg_loss)
    
    Używamy Half-Kelly dla bezpieczeństwa.
    """
    
    def __init__(self, config: dict):
        """
        Inicjalizacja Kelly Calculator
        
        Args:
            config: Konfiguracja z sekcją 'position_sizing'
        """
        sizing_config = config.get('position_sizing', {})
        kelly_config = sizing_config.get('kelly', {})
        fixed_config = sizing_config.get('fixed', {})
        
        # Kelly settings
        self.enabled = kelly_config.get('enabled', True)
        self.use_half_kelly = kelly_config.get('use_half_kelly', True)
        self.min_trades_required = kelly_config.get('min_trades_required', 20)
        self.update_frequency = kelly_config.get('update_frequency', 50)  # trades
        self.min_position_pct = kelly_config.get('min_position_pct', 0.5)
        self.max_position_pct = kelly_config.get('max_position_pct', 5.0)
        
        # Fixed fallback
        self.fixed_risk_pct = fixed_config.get('risk_per_trade', 2.0)
        
        # State
        self.kelly_file = './data/kelly_stats.json'
        self.current_kelly: Optional[KellyResult] = None
        self.last_update_trade_count = 0
        self.last_update_date: Optional[date] = None
        
        self._load_state()
        logger.info("[OK] KellyCalculator zainicjalizowany")
    
    def calculate_kelly_fraction(self, trades_history: List[Dict]) -> KellyResult:
        """
        Oblicza Kelly fraction na podstawie historii trade'ów.
        
        Args:
            trades_history: Lista dictów z 'pnl', 'risk_amount', 'was_winner'
        
        Returns:
            KellyResult z obliczonymi wartościami
        """
        # Filtruj ostatnie 50-100 trade'ów
        recent_trades = trades_history[-100:] if len(trades_history) > 100 else trades_history
        num_trades = len(recent_trades)
        
        # Sprawdź czy mamy wystarczająco danych
        if num_trades < self.min_trades_required:
            logger.info(f"Kelly: Za mało trade'ów ({num_trades}/{self.min_trades_required}), używam fixed %")
            return KellyResult(
                kelly_fraction=0.0,
                half_kelly=0.0,
                optimal_position_pct=self.fixed_risk_pct,
                win_rate=0.0,
                avg_win_rr=0.0,
                avg_loss_rr=0.0,
                trades_analyzed=num_trades,
                confidence='LOW',
                fallback_used=True
            )
        
        # Oblicz win rate
        winners = [t for t in recent_trades if t.get('pnl', 0) > 0]
        losers = [t for t in recent_trades if t.get('pnl', 0) <= 0]
        
        win_rate = len(winners) / num_trades if num_trades > 0 else 0
        
        # Oblicz średnie win/loss w R:R
        if winners:
            avg_win_rr = statistics.mean([
                abs(t.get('pnl', 0)) / max(t.get('risk_amount', 1), 0.01) 
                for t in winners
            ])
        else:
            avg_win_rr = 1.0
        
        if losers:
            avg_loss_rr = statistics.mean([
                abs(t.get('pnl', 0)) / max(t.get('risk_amount', 1), 0.01) 
                for t in losers
            ])
        else:
            avg_loss_rr = 1.0
        
        # Kelly formula: (p * b - q) / b
        # Gdzie p = win_rate, q = 1-win_rate, b = avg_win/avg_loss
        if avg_loss_rr > 0 and avg_win_rr > 0:
            b = avg_win_rr / avg_loss_rr
            kelly = (win_rate * b - (1 - win_rate)) / b if b > 0 else 0
        else:
            kelly = 0
        
        # Clamp Kelly do rozsądnych wartości
        kelly = max(0, min(kelly, 0.5))  # Max 50% Kelly (przed half-kelly)
        
        # Half-Kelly dla bezpieczeństwa
        half_kelly = kelly * 0.5 if self.use_half_kelly else kelly
        
        # Konwertuj na % kapitału
        optimal_pct = half_kelly * 100
        
        # Enforce limits
        optimal_pct = max(self.min_position_pct, min(optimal_pct, self.max_position_pct))
        
        # Określ confidence
        if num_trades >= 50:
            confidence = 'HIGH'
        elif num_trades >= 30:
            confidence = 'MEDIUM'
        else:
            confidence = 'LOW'
        
        result = KellyResult(
            kelly_fraction=kelly,
            half_kelly=half_kelly,
            optimal_position_pct=optimal_pct,
            win_rate=win_rate * 100,
            avg_win_rr=avg_win_rr,
            avg_loss_rr=avg_loss_rr,
            trades_analyzed=num_trades,
            confidence=confidence,
            fallback_used=False
        )
        
        self.current_kelly = result
        self._save_state()
        
        logger.info(
            f"Kelly obliczone: {result.optimal_position_pct:.2f}% "
            f"(WR: {result.win_rate:.1f}%, trades: {num_trades}, confidence: {confidence})"
        )
        
        return result
    
    def get_optimal_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss: float,
        direction: str,
        kelly_result: Optional[KellyResult] = None
    ) -> Tuple[float, float]:
        """
        Oblicza optymalną wielkość pozycji na podstawie Kelly.
        
        Args:
            capital: Dostępny kapitał
            entry_price: Cena wejścia
            stop_loss: Poziom SL
            direction: 'LONG' lub 'SHORT'
            kelly_result: Opcjonalny wcześniej obliczony wynik Kelly
        
        Returns:
            (quantity, risk_pct) - ilość i faktyczny % ryzyka
        """
        kelly = kelly_result or self.current_kelly
        
        if kelly is None or not self.enabled:
            # Fallback do fixed %
            risk_pct = self.fixed_risk_pct
        else:
            risk_pct = kelly.optimal_position_pct
        
        # Oblicz ryzyko na unit
        if direction == 'LONG':
            risk_per_unit = entry_price - stop_loss
        else:
            risk_per_unit = stop_loss - entry_price
        
        if risk_per_unit <= 0:
            return 0.0, 0.0
        
        # Max ryzyko w USDC
        max_risk_usdc = capital * (risk_pct / 100)
        
        # Oblicz quantity
        quantity = max_risk_usdc / risk_per_unit
        
        return quantity, risk_pct
    
    def should_update(self, current_trade_count: int) -> bool:
        """
        Sprawdza czy należy zaktualizować Kelly.
        
        Aktualizacja co 50 trade'ów lub co 7 dni.
        """
        # Co N trade'ów
        trades_since_update = current_trade_count - self.last_update_trade_count
        if trades_since_update >= self.update_frequency:
            return True
        
        # Co 7 dni
        if self.last_update_date is None:
            return True
        
        days_since_update = (date.today() - self.last_update_date).days
        if days_since_update >= 7:
            return True
        
        return False
    
    def mark_updated(self, trade_count: int):
        """Oznacza że Kelly został zaktualizowany"""
        self.last_update_trade_count = trade_count
        self.last_update_date = date.today()
        self._save_state()
    
    def _save_state(self):
        """Zapisuje stan Kelly do pliku"""
        try:
            os.makedirs(os.path.dirname(self.kelly_file), exist_ok=True)
            
            state = {
                'current_kelly': self.current_kelly.to_dict() if self.current_kelly else None,
                'last_update_trade_count': self.last_update_trade_count,
                'last_update_date': self.last_update_date.isoformat() if self.last_update_date else None,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.kelly_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Błąd zapisu Kelly state: {e}")
    
    def _load_state(self):
        """Ładuje stan Kelly z pliku"""
        try:
            if os.path.exists(self.kelly_file):
                with open(self.kelly_file, 'r') as f:
                    state = json.load(f)
                
                kelly_data = state.get('current_kelly')
                if kelly_data:
                    self.current_kelly = KellyResult(**kelly_data)
                
                self.last_update_trade_count = state.get('last_update_trade_count', 0)
                
                date_str = state.get('last_update_date')
                if date_str:
                    self.last_update_date = date.fromisoformat(date_str)
                
                logger.info(f"[FOLDER] Załadowano Kelly state z {self.kelly_file}")
                
        except Exception as e:
            logger.warning(f"Nie udało się załadować Kelly state: {e}")
    
    def get_summary(self) -> Dict:
        """Zwraca podsumowanie Kelly stats"""
        if self.current_kelly:
            return {
                'enabled': self.enabled,
                'current': self.current_kelly.to_dict(),
                'last_update_trade_count': self.last_update_trade_count,
                'last_update_date': self.last_update_date.isoformat() if self.last_update_date else None
            }
        return {
            'enabled': self.enabled,
            'current': None,
            'message': 'Brak danych Kelly - za mało trade\'ów'
        }


@dataclass
class PositionSize:
    """Kalkulacja wielkości pozycji"""
    symbol: str
    side: str  # 'BUY' lub 'SELL'
    entry_price: float
    stop_loss: float
    quantity: float  # Ilość base asset
    value_usdc: float  # Wartość w USDC
    risk_amount: float  # Ryzykowana kwota w USDC
    risk_pct: float  # % kapitału
    leverage: float = 1.0
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'side': self.side,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'quantity': self.quantity,
            'value_usdc': self.value_usdc,
            'risk_amount': self.risk_amount,
            'risk_pct': self.risk_pct,
            'leverage': self.leverage
        }


@dataclass
class DailyStats:
    """Statystyki dzienne"""
    date: date
    trades_count: int = 0
    trades_per_pair: Dict[str, int] = field(default_factory=dict)
    pnl: float = 0.0
    wins: int = 0
    losses: int = 0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    consecutive_losses: int = 0
    max_drawdown_pct: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'date': self.date.isoformat(),
            'trades_count': self.trades_count,
            'trades_per_pair': self.trades_per_pair,
            'pnl': self.pnl,
            'wins': self.wins,
            'losses': self.losses,
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'consecutive_losses': self.consecutive_losses,
            'max_drawdown_pct': self.max_drawdown_pct
        }


class RiskManager:
    """Zarządzanie ryzykiem i kapitałem"""
    
    def __init__(self, config: dict):
        """
        Inicjalizacja Risk Managera
        
        Args:
            config: Konfiguracja z parametrami ryzyka
        """
        self.config = config.get('risk', {})
        self.trading_config = config.get('trading', {})
        self.safety_config = config.get('safety', {})
        self.full_config = config  # Zachowaj pełną konfigurację
        
        # Parametry ryzyka
        self.min_risk_reward = self.config.get('min_risk_reward', 1.5)
        self.max_risk_per_trade_pct = self.config.get('max_risk_per_trade_pct', 2)
        self.max_daily_drawdown_pct = self.config.get('max_daily_drawdown_pct', 5)
        self.max_daily_trades_per_pair = self.config.get('max_daily_trades_per_pair', 5)
        self.max_daily_trades_total = self.config.get('max_daily_trades_total', 15)
        self.default_stop_loss_pct = self.config.get('default_stop_loss_pct', 2)
        self.default_take_profit_pct = self.config.get('default_take_profit_pct', 3)
        
        # Trailing stop
        self.trailing_stop_activation_pct = self.config.get('trailing_stop_activation_pct', 2)
        self.trailing_stop_distance_pct = self.config.get('trailing_stop_distance_pct', 1)
        
        # Kapital per pair
        self.initial_capital_per_pair = self.trading_config.get('initial_capital_per_pair', 10000)
        self.max_position_size_pct = self.trading_config.get('max_position_size_pct', 20)
        self.max_order_value = self.safety_config.get('max_order_value', 2000)
        
        # Emergency stop parametry
        self.emergency_daily_loss_pct = self.safety_config.get('emergency_stop', {}).get('daily_loss_pct', 10)
        self.emergency_consecutive_losses = self.safety_config.get('emergency_stop', {}).get('consecutive_losses', 5)
        self.emergency_price_anomaly_pct = self.safety_config.get('emergency_stop', {}).get('price_anomaly_pct', 10)
        
        # Position sizing config
        sizing_config = config.get('position_sizing', {})
        self.use_kelly = sizing_config.get('method', 'fixed') == 'kelly'
        
        # Kelly Criterion Calculator
        self.kelly_calculator: Optional[KellyCalculator] = None
        if self.use_kelly:
            self.kelly_calculator = KellyCalculator(config)
        
        # Stan
        self.capital: Dict[str, float] = {}
        self.positions: Dict[str, Dict] = {}
        self.daily_stats = DailyStats(date=date.today())
        self.emergency_stop_active = False
        self.price_history: Dict[str, List[float]] = {}
        
        # Ścieżka do zapisywania stanu
        self.state_file = './data/risk_state.json'
        
        self._load_state()
        logger.info("[OK] RiskManager zainicjalizowany")
    
    def initialize_capital(self, pairs: List[str]):
        """
        Inicjalizuje kapitał dla par
        
        Args:
            pairs: Lista par walutowych
        """
        for pair in pairs:
            if pair not in self.capital:
                self.capital[pair] = self.initial_capital_per_pair
                logger.info(f"[$] {pair}: Zainicjalizowano kapitał {self.initial_capital_per_pair} USDC")
    
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        direction: str
    ) -> Optional[PositionSize]:
        """
        Oblicza optymalną wielkość pozycji
        
        Args:
            symbol: Para walutowa
            entry_price: Cena wejścia
            stop_loss: Poziom stop loss
            direction: 'LONG' lub 'SHORT'
        
        Returns:
            PositionSize lub None jeśli nie można otworzyć
        """
        # Sprawdź kapitał
        available_capital = self.capital.get(symbol, self.initial_capital_per_pair)
        
        # Sprawdź czy jest już otwarta pozycja
        if symbol in self.positions:
            logger.warning(f"[WARNING] {symbol}: Już jest otwarta pozycja")
            return None
        
        # Oblicz ryzyko na trade
        if direction == 'LONG':
            risk_per_unit = entry_price - stop_loss
        else:
            risk_per_unit = stop_loss - entry_price
        
        if risk_per_unit <= 0:
            logger.error(f"[ERROR] {symbol}: Nieprawidłowy SL (risk_per_unit <= 0)")
            return None
        
        # Max ryzyko w USDC
        max_risk_usdc = available_capital * (self.max_risk_per_trade_pct / 100)
        
        # Oblicz ilość
        quantity = max_risk_usdc / risk_per_unit
        position_value = quantity * entry_price
        
        # Sprawdź limity
        max_position_value = available_capital * (self.max_position_size_pct / 100)
        max_position_value = min(max_position_value, self.max_order_value)
        
        if position_value > max_position_value:
            quantity = max_position_value / entry_price
            position_value = quantity * entry_price
            actual_risk = quantity * risk_per_unit
        else:
            actual_risk = max_risk_usdc
        
        # Zaokrąglij quantity (różne precyzje dla różnych par)
        # To powinno być pobrane z exchange info, tu uproszczenie
        if 'BTC' in symbol:
            quantity = round(quantity, 5)
        elif 'ETH' in symbol:
            quantity = round(quantity, 4)
        else:
            quantity = round(quantity, 2)
        
        if quantity <= 0:
            logger.error(f"[ERROR] {symbol}: Quantity <= 0")
            return None
        
        risk_pct = (actual_risk / available_capital) * 100
        
        return PositionSize(
            symbol=symbol,
            side='BUY' if direction == 'LONG' else 'SELL',
            entry_price=entry_price,
            stop_loss=stop_loss,
            quantity=quantity,
            value_usdc=round(position_value, 2),
            risk_amount=round(actual_risk, 2),
            risk_pct=round(risk_pct, 2)
        )
    
    def calculate_position_size_kelly(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        direction: str,
        trades_history: Optional[List[Dict]] = None
    ) -> Optional[PositionSize]:
        """
        Oblicza wielkość pozycji używając Kelly Criterion.
        
        Args:
            symbol: Para walutowa
            entry_price: Cena wejścia
            stop_loss: Poziom stop loss
            direction: 'LONG' lub 'SHORT'
            trades_history: Opcjonalna historia trade'ów do kalkulacji Kelly
        
        Returns:
            PositionSize lub None jeśli nie można otworzyć
        """
        # Sprawdź kapitał
        available_capital = self.capital.get(symbol, self.initial_capital_per_pair)
        
        # Sprawdź czy jest już otwarta pozycja
        if symbol in self.positions:
            logger.warning(f"[WARNING] {symbol}: Już jest otwarta pozycja")
            return None
        
        # Użyj Kelly jeśli włączone
        if self.use_kelly and self.kelly_calculator:
            # Aktualizuj Kelly jeśli potrzeba
            if trades_history and self.kelly_calculator.should_update(len(trades_history)):
                self.kelly_calculator.calculate_kelly_fraction(trades_history)
                self.kelly_calculator.mark_updated(len(trades_history))
            
            quantity, risk_pct = self.kelly_calculator.get_optimal_position_size(
                capital=available_capital,
                entry_price=entry_price,
                stop_loss=stop_loss,
                direction=direction
            )
            
            kelly_info = self.kelly_calculator.current_kelly
            if kelly_info and not kelly_info.fallback_used:
                logger.info(
                    f"[INFO] Kelly: {risk_pct:.2f}% "
                    f"(was {self.max_risk_per_trade_pct:.1f}% fixed)"
                )
        else:
            # Fallback do standard position sizing
            return self.calculate_position_size(symbol, entry_price, stop_loss, direction)
        
        if quantity <= 0:
            logger.error(f"[ERROR] {symbol}: Quantity <= 0")
            return None
        
        # Oblicz wartości
        if direction == 'LONG':
            risk_per_unit = entry_price - stop_loss
        else:
            risk_per_unit = stop_loss - entry_price
        
        position_value = quantity * entry_price
        actual_risk = quantity * risk_per_unit
        
        # Sprawdź limity
        max_position_value = available_capital * (self.max_position_size_pct / 100)
        max_position_value = min(max_position_value, self.max_order_value)
        
        if position_value > max_position_value:
            quantity = max_position_value / entry_price
            position_value = quantity * entry_price
            actual_risk = quantity * risk_per_unit
        
        # Zaokrąglij quantity
        if 'BTC' in symbol:
            quantity = round(quantity, 5)
        elif 'ETH' in symbol:
            quantity = round(quantity, 4)
        else:
            quantity = round(quantity, 2)
        
        return PositionSize(
            symbol=symbol,
            side='BUY' if direction == 'LONG' else 'SELL',
            entry_price=entry_price,
            stop_loss=stop_loss,
            quantity=quantity,
            value_usdc=round(position_value, 2),
            risk_amount=round(actual_risk, 2),
            risk_pct=round(risk_pct, 2)
        )
    
    def update_kelly(self, trades_history: List[Dict]) -> Optional[KellyResult]:
        """
        Aktualizuje Kelly Criterion na podstawie historii trade'ów.
        
        Args:
            trades_history: Lista trade'ów z 'pnl' i 'risk_amount'
        
        Returns:
            KellyResult lub None jeśli Kelly wyłączone
        """
        if not self.use_kelly or not self.kelly_calculator:
            return None
        
        return self.kelly_calculator.calculate_kelly_fraction(trades_history)
    
    def get_kelly_summary(self) -> Dict:
        """Zwraca podsumowanie Kelly stats"""
        if self.kelly_calculator:
            return self.kelly_calculator.get_summary()
        return {'enabled': False, 'message': 'Kelly wyłączone w konfiguracji'}
    
    def can_trade(self, symbol: str) -> Tuple[bool, str]:
        """
        Sprawdza czy można otworzyć trade
        
        Returns:
            (can_trade, reason)
        """
        # Emergency stop
        if self.emergency_stop_active:
            return False, "[ALERT] Emergency stop aktywny"
        
        # Dzienny drawdown
        if self._check_daily_drawdown():
            return False, f"[ERROR] Dzienny drawdown przekroczony ({self.max_daily_drawdown_pct}%)"
        
        # Dzienny limit trade'ów (total)
        if self.daily_stats.trades_count >= self.max_daily_trades_total:
            return False, f"[ERROR] Dzienny limit trade'ów ({self.max_daily_trades_total})"
        
        # Dzienny limit trade'ów (per pair)
        pair_trades = self.daily_stats.trades_per_pair.get(symbol, 0)
        if pair_trades >= self.max_daily_trades_per_pair:
            return False, f"[ERROR] Limit trade'ów dla {symbol} ({self.max_daily_trades_per_pair})"
        
        # Consecutive losses
        if self.daily_stats.consecutive_losses >= self.emergency_consecutive_losses:
            self._activate_emergency_stop("Consecutive losses limit")
            return False, f"[ERROR] Za dużo strat z rzędu ({self.daily_stats.consecutive_losses})"
        
        # Istniejąca pozycja
        if symbol in self.positions:
            return False, f"[WARNING] Otwarta pozycja na {symbol}"
        
        return True, "[OK] OK"
    
    def validate_trade(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        direction: str
    ) -> Tuple[bool, str]:
        """
        Waliduje parametry trade'a
        
        Returns:
            (is_valid, reason)
        """
        # Podstawowa walidacja
        if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
            return False, "Ceny muszą być > 0"
        
        # Sprawdź R:R
        if direction == 'LONG':
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
            
            if stop_loss >= entry_price:
                return False, "SL musi być < entry dla LONG"
            if take_profit <= entry_price:
                return False, "TP musi być > entry dla LONG"
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
            
            if stop_loss <= entry_price:
                return False, "SL musi być > entry dla SHORT"
            if take_profit >= entry_price:
                return False, "TP musi być < entry dla SHORT"
        
        if risk <= 0:
            return False, "Nieprawidłowe ryzyko"
        
        rr = reward / risk
        if rr < self.min_risk_reward:
            return False, f"R:R {rr:.2f} < minimum {self.min_risk_reward}"
        
        return True, f"[OK] R:R: {rr:.2f}"
    
    def register_trade_open(
        self,
        symbol: str,
        position: PositionSize,
        take_profit: float
    ):
        """
        Rejestruje otwarcie trade'a
        
        Args:
            symbol: Para walutowa
            position: Dane pozycji
            take_profit: Poziom TP
        """
        self.positions[symbol] = {
            'entry_price': position.entry_price,
            'quantity': position.quantity,
            'side': position.side,
            'stop_loss': position.stop_loss,
            'take_profit': take_profit,
            'highest_price': position.entry_price if position.side == 'BUY' else None,
            'lowest_price': position.entry_price if position.side == 'SELL' else None,
            'trailing_stop': None,
            'open_time': datetime.now().isoformat(),
            'risk_amount': position.risk_amount
        }
        
        # Aktualizuj statystyki dzienne
        self._check_date_rollover()
        self.daily_stats.trades_count += 1
        self.daily_stats.trades_per_pair[symbol] = \
            self.daily_stats.trades_per_pair.get(symbol, 0) + 1
        
        self._save_state()
        logger.info(f"[LOG] Zarejestrowano otwarcie: {symbol} {position.side} @ {position.entry_price}")
    
    def register_trade_close(
        self,
        symbol: str,
        exit_price: float,
        reason: str
    ) -> float:
        """
        Rejestruje zamknięcie trade'a
        
        Args:
            symbol: Para walutowa
            exit_price: Cena zamknięcia
            reason: Powód zamknięcia
        
        Returns:
            PnL w USDC
        """
        if symbol not in self.positions:
            logger.warning(f"[WARNING] Brak otwartej pozycji dla {symbol}")
            return 0.0
        
        position = self.positions[symbol]
        entry = position['entry_price']
        qty = position['quantity']
        side = position['side']
        
        # Oblicz PnL
        if side == 'BUY':
            pnl = (exit_price - entry) * qty
        else:
            pnl = (entry - exit_price) * qty
        
        # Aktualizuj kapitał
        self.capital[symbol] = self.capital.get(symbol, self.initial_capital_per_pair) + pnl
        
        # Aktualizuj statystyki
        self._check_date_rollover()
        self.daily_stats.pnl += pnl
        
        if pnl > 0:
            self.daily_stats.wins += 1
            self.daily_stats.largest_win = max(self.daily_stats.largest_win, pnl)
            self.daily_stats.consecutive_losses = 0
        else:
            self.daily_stats.losses += 1
            self.daily_stats.largest_loss = min(self.daily_stats.largest_loss, pnl)
            self.daily_stats.consecutive_losses += 1
        
        # Oblicz drawdown
        initial_capital = self.initial_capital_per_pair * len(self.capital)
        current_capital = sum(self.capital.values())
        drawdown_pct = ((initial_capital - current_capital) / initial_capital) * 100
        self.daily_stats.max_drawdown_pct = max(self.daily_stats.max_drawdown_pct, drawdown_pct)
        
        # Usuń pozycję
        del self.positions[symbol]
        
        self._save_state()
        logger.info(f"[LOG] Zamknięto {symbol}: PnL {pnl:+.2f} USDC ({reason})")
        
        return pnl
    
    def update_trailing_stop(
        self,
        symbol: str,
        current_price: float
    ) -> Optional[float]:
        """
        Aktualizuje trailing stop
        
        Returns:
            Nowy poziom trailing stop lub None
        """
        if symbol not in self.positions:
            return None
        
        position = self.positions[symbol]
        entry = position['entry_price']
        side = position['side']
        
        # Oblicz aktualny zysk %
        if side == 'BUY':
            profit_pct = ((current_price - entry) / entry) * 100
            
            # Aktywuj trailing stop
            if profit_pct >= self.trailing_stop_activation_pct:
                new_trailing = current_price * (1 - self.trailing_stop_distance_pct / 100)
                
                if position['highest_price'] is None or current_price > position['highest_price']:
                    position['highest_price'] = current_price
                    
                    if position['trailing_stop'] is None or new_trailing > position['trailing_stop']:
                        position['trailing_stop'] = new_trailing
                        self._save_state()
                        logger.info(f"[UP] {symbol} Trailing stop: {new_trailing:.2f}")
                        return new_trailing
        else:
            profit_pct = ((entry - current_price) / entry) * 100
            
            if profit_pct >= self.trailing_stop_activation_pct:
                new_trailing = current_price * (1 + self.trailing_stop_distance_pct / 100)
                
                if position['lowest_price'] is None or current_price < position['lowest_price']:
                    position['lowest_price'] = current_price
                    
                    if position['trailing_stop'] is None or new_trailing < position['trailing_stop']:
                        position['trailing_stop'] = new_trailing
                        self._save_state()
                        logger.info(f"[DOWN] {symbol} Trailing stop: {new_trailing:.2f}")
                        return new_trailing
        
        return position.get('trailing_stop')
    
    def check_stop_hit(
        self,
        symbol: str,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        Sprawdza czy został trafiony stop
        
        Returns:
            (stop_hit, reason)
        """
        if symbol not in self.positions:
            return False, ""
        
        position = self.positions[symbol]
        sl = position['stop_loss']
        tp = position['take_profit']
        trailing = position.get('trailing_stop')
        side = position['side']
        
        if side == 'BUY':
            # Stop Loss
            if current_price <= sl:
                return True, "STOP_LOSS"
            # Take Profit
            if current_price >= tp:
                return True, "TAKE_PROFIT"
            # Trailing Stop
            if trailing and current_price <= trailing:
                return True, "TRAILING_STOP"
        else:
            if current_price >= sl:
                return True, "STOP_LOSS"
            if current_price <= tp:
                return True, "TAKE_PROFIT"
            if trailing and current_price >= trailing:
                return True, "TRAILING_STOP"
        
        return False, ""
    
    def check_price_anomaly(self, symbol: str, current_price: float) -> bool:
        """
        Sprawdza anomalię cenową (flash crash/spike)
        
        Returns:
            True jeśli wykryto anomalię
        """
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        history = self.price_history[symbol]
        history.append(current_price)
        
        # Zachowaj tylko ostatnie 5 minut (przy 15m świecach to ~1 świeca)
        # Dla lepszej detekcji potrzeba częstszych aktualizacji
        if len(history) > 20:
            history.pop(0)
        
        if len(history) >= 2:
            price_change_pct = abs((current_price - history[0]) / history[0]) * 100
            
            if price_change_pct > self.emergency_price_anomaly_pct:
                self._activate_emergency_stop(f"Price anomaly: {price_change_pct:.1f}%")
                return True
        
        return False
    
    def _check_daily_drawdown(self) -> bool:
        """Sprawdza czy przekroczono dzienny drawdown"""
        initial = self.initial_capital_per_pair * len(self.capital)
        current = sum(self.capital.values())
        
        if initial == 0:
            return False
        
        drawdown_pct = ((initial - current) / initial) * 100
        
        if drawdown_pct >= self.max_daily_drawdown_pct:
            self._activate_emergency_stop(f"Daily drawdown: {drawdown_pct:.1f}%")
            return True
        
        return False
    
    def _activate_emergency_stop(self, reason: str):
        """Aktywuje emergency stop"""
        self.emergency_stop_active = True
        logger.critical(f"[ALERT] EMERGENCY STOP ACTIVATED: {reason}")
        self._save_state()
    
    def deactivate_emergency_stop(self):
        """Dezaktywuje emergency stop (wymaga manualnej interwencji)"""
        self.emergency_stop_active = False
        logger.warning("[WARNING] Emergency stop dezaktywowany manualnie")
        self._save_state()
    
    def _check_date_rollover(self):
        """Sprawdza czy minął dzień i resetuje statystyki"""
        today = date.today()
        if self.daily_stats.date != today:
            logger.info(f"[DATE] Nowy dzień: {today}")
            self.daily_stats = DailyStats(date=today)
            
            # Reset emergency stop przy nowym dniu (opcjonalnie)
            # self.emergency_stop_active = False
    
    def get_portfolio_summary(self) -> Dict:
        """Zwraca podsumowanie portfolio"""
        total_capital = sum(self.capital.values())
        initial_total = self.initial_capital_per_pair * len(self.capital) if self.capital else 0
        
        return {
            'total_capital': total_capital,
            'initial_capital': initial_total,
            'pnl_total': total_capital - initial_total,
            'pnl_pct': ((total_capital - initial_total) / initial_total * 100) if initial_total else 0,
            'capital_per_pair': dict(self.capital),
            'open_positions': len(self.positions),
            'positions': {k: v for k, v in self.positions.items()},
            'daily_stats': self.daily_stats.to_dict(),
            'emergency_stop': self.emergency_stop_active
        }
    
    def _save_state(self):
        """Zapisuje stan do pliku"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            state = {
                'capital': self.capital,
                'positions': self.positions,
                'daily_stats': self.daily_stats.to_dict(),
                'emergency_stop_active': self.emergency_stop_active,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Błąd zapisu stanu: {e}")
    
    def _load_state(self):
        """Ładuje stan z pliku"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                self.capital = state.get('capital', {})
                self.positions = state.get('positions', {})
                self.emergency_stop_active = state.get('emergency_stop_active', False)
                
                # Odtwórz daily_stats
                ds = state.get('daily_stats', {})
                if ds:
                    saved_date = date.fromisoformat(ds.get('date', date.today().isoformat()))
                    if saved_date == date.today():
                        self.daily_stats = DailyStats(
                            date=saved_date,
                            trades_count=ds.get('trades_count', 0),
                            trades_per_pair=ds.get('trades_per_pair', {}),
                            pnl=ds.get('pnl', 0),
                            wins=ds.get('wins', 0),
                            losses=ds.get('losses', 0),
                            largest_win=ds.get('largest_win', 0),
                            largest_loss=ds.get('largest_loss', 0),
                            consecutive_losses=ds.get('consecutive_losses', 0),
                            max_drawdown_pct=ds.get('max_drawdown_pct', 0)
                        )
                
                logger.info(f"[FOLDER] Załadowano stan z {self.state_file}")
                
        except Exception as e:
            logger.warning(f"Nie udało się załadować stanu: {e}")


if __name__ == "__main__":
    # Test modułu
    import yaml
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Test Risk Manager
    rm = RiskManager(config)
    rm.initialize_capital(['BTCUSDC', 'ETHUSDC'])
    
    # Test kalkulacji pozycji
    position = rm.calculate_position_size(
        symbol='BTCUSDC',
        entry_price=50000,
        stop_loss=49000,
        direction='LONG'
    )
    
    if position:
        print(f"\n[INFO] Position Size:")
        print(f"   Quantity: {position.quantity} BTC")
        print(f"   Value: {position.value_usdc} USDC")
        print(f"   Risk: {position.risk_amount} USDC ({position.risk_pct}%)")
    
    # Test walidacji
    is_valid, reason = rm.validate_trade(
        symbol='BTCUSDC',
        entry_price=50000,
        stop_loss=49000,
        take_profit=53000,
        direction='LONG'
    )
    print(f"\n[OK] Trade valid: {is_valid} - {reason}")
    
    # Test can_trade
    can, reason = rm.can_trade('BTCUSDC')
    print(f"\n[SCAN] Can trade: {can} - {reason}")
    
    # Portfolio summary
    print(f"\n[CASE] Portfolio Summary:")
    summary = rm.get_portfolio_summary()
    for key, value in summary.items():
        print(f"   {key}: {value}")
