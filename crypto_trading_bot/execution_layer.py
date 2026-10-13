"""
execution_layer.py - Warstwa wykonawcza zleceń

Odpowiedzialny za:
- Wysyłanie zleceń na Binance (Testnet)
- Obsługa market/limit orders
- Paper trading simulation
- Zarządzanie otwartymi pozycjami
- Logowanie wszystkich operacji
- Scale Out (Partial Profit Taking) v3.0
- Smart Order Execution (Maker/Taker optimization) v3.0
"""

import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable
import json
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException

logger = logging.getLogger(__name__)


# ============================================
# SCALE OUT MANAGER - PARTIAL PROFIT TAKING
# ============================================

@dataclass
class ScaleOutLevel:
    """Definicja poziomu scale out"""
    level_id: str  # 'tp1', 'tp2', 'tp3'
    rr_multiplier: float  # np. 1.0, 1.5, 2.5
    close_percentage: int  # np. 50, 30, 20
    price: float = 0.0
    quantity: float = 0.0
    triggered: bool = False
    triggered_at: Optional[str] = None


@dataclass
class ScaleOutState:
    """Stan scale out dla pozycji"""
    symbol: str
    entry_price: float
    stop_loss: float
    original_quantity: float
    remaining_quantity: float
    direction: str  # 'LONG' lub 'SHORT'
    levels: Dict[str, ScaleOutLevel] = field(default_factory=dict)
    total_realized_pnl: float = 0.0
    original_sl: float = 0.0
    current_sl: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'original_quantity': self.original_quantity,
            'remaining_quantity': self.remaining_quantity,
            'direction': self.direction,
            'levels': {k: {
                'level_id': v.level_id,
                'rr_multiplier': v.rr_multiplier,
                'close_percentage': v.close_percentage,
                'price': v.price,
                'quantity': v.quantity,
                'triggered': v.triggered,
                'triggered_at': v.triggered_at
            } for k, v in self.levels.items()},
            'total_realized_pnl': self.total_realized_pnl,
            'original_sl': self.original_sl,
            'current_sl': self.current_sl
        }


class ScaleOutManager:
    """
    Zarządza scale out (partial profit taking) dla pozycji.
    
    Domyślne poziomy:
    - TP1: 1.0x R:R -> Zamknij 50%
    - TP2: 1.5x R:R -> Zamknij 30%
    - TP3: 2.5x R:R -> Zamknij 20%
    
    Po TP1: SL -> breakeven
    Po TP2: SL -> TP1 price
    """
    
    def __init__(self, config: dict, discord_notifier=None):
        """
        Inicjalizacja Scale Out Manager
        
        Args:
            config: Konfiguracja z sekcją 'profit_taking'
            discord_notifier: Opcjonalny notifier Discord
        """
        profit_config = config.get('profit_taking', {})
        scale_out_config = profit_config.get('scale_out', {})
        
        self.enabled = scale_out_config.get('enabled', True)
        self.move_sl_to_breakeven_after_tp1 = scale_out_config.get('move_sl_to_breakeven_after_tp1', True)
        self.move_sl_to_tp1_after_tp2 = scale_out_config.get('move_sl_to_tp1_after_tp2', True)
        
        # Poziomy z konfiguracji
        levels_config = scale_out_config.get('levels', {})
        self.levels_config = {
            'tp1': {
                'rr_multiplier': levels_config.get('tp1', {}).get('rr_multiplier', 1.0),
                'close_percentage': levels_config.get('tp1', {}).get('close_percentage', 50)
            },
            'tp2': {
                'rr_multiplier': levels_config.get('tp2', {}).get('rr_multiplier', 1.5),
                'close_percentage': levels_config.get('tp2', {}).get('close_percentage', 30)
            },
            'tp3': {
                'rr_multiplier': levels_config.get('tp3', {}).get('rr_multiplier', 2.5),
                'close_percentage': levels_config.get('tp3', {}).get('close_percentage', 20)
            }
        }
        
        self.discord_notifier = discord_notifier
        
        # Stan aktywnych scale out
        self.active_scale_outs: Dict[str, ScaleOutState] = {}
        
        # Monitoring thread
        self.monitoring_thread: Optional[threading.Thread] = None
        self.stop_monitoring = threading.Event()
        self.check_interval = 15  # sekund
        
        # Callbacks
        self.on_partial_close: Optional[Callable] = None
        self.get_current_price: Optional[Callable] = None
        
        # Persistence
        self.state_file = './data/execution/scale_out_state.json'
        self._load_state()
        
        logger.info("[OK] ScaleOutManager zainicjalizowany")
    
    def calculate_scale_out_levels(
        self,
        entry_price: float,
        stop_loss: float,
        quantity: float,
        direction: str
    ) -> Dict[str, ScaleOutLevel]:
        """
        Oblicza poziomy scale out dla pozycji.
        
        Args:
            entry_price: Cena wejścia
            stop_loss: Poziom SL
            quantity: Całkowita ilość
            direction: 'LONG' lub 'SHORT'
        
        Returns:
            Dict z poziomami TP1, TP2, TP3
        """
        if direction == 'LONG':
            risk = entry_price - stop_loss
        else:
            risk = stop_loss - entry_price
        
        levels = {}
        remaining_pct = 100
        
        for level_id, config in self.levels_config.items():
            rr_mult = config['rr_multiplier']
            close_pct = config['close_percentage']
            
            # Oblicz cenę TP
            if direction == 'LONG':
                tp_price = entry_price + (risk * rr_mult)
            else:
                tp_price = entry_price - (risk * rr_mult)
            
            # Oblicz quantity dla tego poziomu
            level_qty = quantity * (close_pct / 100)
            
            levels[level_id] = ScaleOutLevel(
                level_id=level_id,
                rr_multiplier=rr_mult,
                close_percentage=close_pct,
                price=round(tp_price, 8),
                quantity=round(level_qty, 8),
                triggered=False
            )
            
            remaining_pct -= close_pct
        
        return levels
    
    def register_position(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        quantity: float,
        direction: str
    ) -> ScaleOutState:
        """
        Rejestruje nową pozycję do scale out monitoring.
        
        Returns:
            ScaleOutState z obliczonymi poziomami
        """
        levels = self.calculate_scale_out_levels(entry_price, stop_loss, quantity, direction)
        
        state = ScaleOutState(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            original_quantity=quantity,
            remaining_quantity=quantity,
            direction=direction,
            levels=levels,
            original_sl=stop_loss,
            current_sl=stop_loss
        )
        
        self.active_scale_outs[symbol] = state
        self._save_state()
        
        logger.info(
            f"[INFO] Scale Out zarejestrowany: {symbol} | "
            f"TP1: {levels['tp1'].price:.2f} ({levels['tp1'].close_percentage}%) | "
            f"TP2: {levels['tp2'].price:.2f} ({levels['tp2'].close_percentage}%) | "
            f"TP3: {levels['tp3'].price:.2f} ({levels['tp3'].close_percentage}%)"
        )
        
        return state
    
    def check_scale_out_triggers(
        self,
        symbol: str,
        current_price: float
    ) -> List[ScaleOutLevel]:
        """
        Sprawdza czy któryś z poziomów scale out został osiągnięty.
        
        Returns:
            Lista triggeredych poziomów (do wykonania partial close)
        """
        if symbol not in self.active_scale_outs:
            return []
        
        state = self.active_scale_outs[symbol]
        triggered = []
        
        for level_id in ['tp1', 'tp2', 'tp3']:
            level = state.levels.get(level_id)
            if not level or level.triggered:
                continue
            
            # Sprawdź czy cena osiągnęła poziom
            if state.direction == 'LONG':
                if current_price >= level.price:
                    level.triggered = True
                    level.triggered_at = datetime.now().isoformat()
                    triggered.append(level)
            else:
                if current_price <= level.price:
                    level.triggered = True
                    level.triggered_at = datetime.now().isoformat()
                    triggered.append(level)
        
        if triggered:
            self._save_state()
        
        return triggered
    
    def execute_partial_close(
        self,
        symbol: str,
        level: ScaleOutLevel,
        actual_close_price: float
    ) -> Tuple[float, float]:
        """
        Wykonuje partial close dla danego poziomu.
        
        Args:
            symbol: Para walutowa
            level: Triggered poziom
            actual_close_price: Faktyczna cena zamknięcia
        
        Returns:
            (closed_quantity, realized_pnl)
        """
        if symbol not in self.active_scale_outs:
            return 0.0, 0.0
        
        state = self.active_scale_outs[symbol]
        
        # Oblicz PnL
        if state.direction == 'LONG':
            pnl = (actual_close_price - state.entry_price) * level.quantity
        else:
            pnl = (state.entry_price - actual_close_price) * level.quantity
        
        # Aktualizuj stan
        state.remaining_quantity -= level.quantity
        state.remaining_quantity = max(0, state.remaining_quantity)
        state.total_realized_pnl += pnl
        
        self._save_state()
        
        logger.info(
            f"[OK] Partial Close: {symbol} {level.level_id.upper()} | "
            f"Closed: {level.quantity:.4f} @ {actual_close_price:.2f} | "
            f"PnL: {pnl:+.2f} USDC | Remaining: {state.remaining_quantity:.4f}"
        )
        
        # Discord notification
        if self.discord_notifier:
            self._send_discord_notification(symbol, level, actual_close_price, pnl, state)
        
        return level.quantity, pnl
    
    def update_stop_loss_after_tp(
        self,
        symbol: str,
        tp_level: str
    ) -> Optional[float]:
        """
        Aktualizuje stop loss po triggeredym TP.
        
        - Po TP1: SL -> breakeven
        - Po TP2: SL -> TP1 price
        
        Returns:
            Nowy poziom SL lub None
        """
        if symbol not in self.active_scale_outs:
            return None
        
        state = self.active_scale_outs[symbol]
        new_sl = None
        
        if tp_level == 'tp1' and self.move_sl_to_breakeven_after_tp1:
            # Move SL to breakeven
            new_sl = state.entry_price
            state.current_sl = new_sl
            logger.info(f"[LOCK] {symbol}: SL moved to breakeven @ {new_sl:.2f}")
            
        elif tp_level == 'tp2' and self.move_sl_to_tp1_after_tp2:
            # Move SL to TP1 price
            tp1_level = state.levels.get('tp1')
            if tp1_level:
                new_sl = tp1_level.price
                state.current_sl = new_sl
                logger.info(f"[LOCK] {symbol}: SL moved to TP1 @ {new_sl:.2f}")
        
        if new_sl:
            self._save_state()
        
        return new_sl
    
    def get_remaining_quantity(self, symbol: str) -> float:
        """Zwraca pozostałą ilość dla pozycji"""
        if symbol in self.active_scale_outs:
            return self.active_scale_outs[symbol].remaining_quantity
        return 0.0
    
    def get_current_sl(self, symbol: str) -> Optional[float]:
        """Zwraca aktualny SL (może być zmodyfikowany przez scale out)"""
        if symbol in self.active_scale_outs:
            return self.active_scale_outs[symbol].current_sl
        return None
    
    def remove_position(self, symbol: str) -> Optional[ScaleOutState]:
        """Usuwa pozycję z monitoringu (po pełnym zamknięciu)"""
        if symbol in self.active_scale_outs:
            state = self.active_scale_outs.pop(symbol)
            self._save_state()
            return state
        return None
    
    def get_scale_out_stats(self, symbol: str) -> Optional[Dict]:
        """Zwraca statystyki scale out dla pozycji"""
        if symbol not in self.active_scale_outs:
            return None
        
        state = self.active_scale_outs[symbol]
        triggered_count = sum(1 for l in state.levels.values() if l.triggered)
        
        return {
            'symbol': symbol,
            'entry_price': state.entry_price,
            'original_quantity': state.original_quantity,
            'remaining_quantity': state.remaining_quantity,
            'total_realized_pnl': state.total_realized_pnl,
            'triggered_levels': triggered_count,
            'current_sl': state.current_sl,
            'levels': {k: {
                'price': v.price,
                'triggered': v.triggered,
                'close_pct': v.close_percentage
            } for k, v in state.levels.items()}
        }
    
    def start_monitoring(self, price_callback: Callable[[str], float]):
        """
        Uruchamia monitoring thread dla scale out.
        
        Args:
            price_callback: Funkcja zwracająca aktualną cenę dla symbolu
        """
        if not self.enabled:
            return
        
        self.get_current_price = price_callback
        self.stop_monitoring.clear()
        
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self.monitoring_thread.start()
        logger.info("[SYNC] Scale Out monitoring uruchomiony")
    
    def stop_monitoring_thread(self):
        """Zatrzymuje monitoring thread"""
        self.stop_monitoring.set()
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("[STOP] Scale Out monitoring zatrzymany")
    
    def _monitoring_loop(self):
        """Główna pętla monitoringu"""
        while not self.stop_monitoring.is_set():
            try:
                for symbol in list(self.active_scale_outs.keys()):
                    if self.get_current_price:
                        current_price = self.get_current_price(symbol)
                        if current_price:
                            triggered = self.check_scale_out_triggers(symbol, current_price)
                            
                            for level in triggered:
                                # Callback do execution layer
                                if self.on_partial_close:
                                    self.on_partial_close(symbol, level, current_price)
            except Exception as e:
                logger.error(f"Scale Out monitoring error: {e}")
            
            self.stop_monitoring.wait(self.check_interval)
    
    def _send_discord_notification(
        self,
        symbol: str,
        level: ScaleOutLevel,
        price: float,
        pnl: float,
        state: ScaleOutState
    ):
        """Wysyła Discord notification o partial close"""
        try:
            if hasattr(self.discord_notifier, 'send_message'):
                emoji = "[GREEN]" if pnl > 0 else "[RED]"
                message = (
                    f"{emoji} **PARTIAL CLOSE - {symbol}**\n"
                    f"Level: {level.level_id.upper()} ({level.close_percentage}%)\n"
                    f"Price: ${price:.2f}\n"
                    f"PnL: ${pnl:+.2f}\n"
                    f"Remaining: {state.remaining_quantity:.4f}"
                )
                self.discord_notifier.send_message(message)
        except Exception as e:
            logger.error(f"Discord notification error: {e}")
    
    def _save_state(self):
        """Zapisuje stan do pliku"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            state = {
                symbol: s.to_dict() for symbol, s in self.active_scale_outs.items()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Błąd zapisu scale out state: {e}")
    
    def _load_state(self):
        """Ładuje stan z pliku"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                
                for symbol, state_data in data.items():
                    levels = {}
                    for level_id, level_data in state_data.get('levels', {}).items():
                        levels[level_id] = ScaleOutLevel(**level_data)
                    
                    self.active_scale_outs[symbol] = ScaleOutState(
                        symbol=state_data['symbol'],
                        entry_price=state_data['entry_price'],
                        stop_loss=state_data['stop_loss'],
                        original_quantity=state_data['original_quantity'],
                        remaining_quantity=state_data['remaining_quantity'],
                        direction=state_data['direction'],
                        levels=levels,
                        total_realized_pnl=state_data.get('total_realized_pnl', 0.0),
                        original_sl=state_data.get('original_sl', state_data['stop_loss']),
                        current_sl=state_data.get('current_sl', state_data['stop_loss'])
                    )
                
                logger.info(f"[FOLDER] Załadowano {len(self.active_scale_outs)} scale out states")
                
        except Exception as e:
            logger.warning(f"Nie udało się załadować scale out state: {e}")


# ============================================
# SMART ORDER EXECUTION - FEE OPTIMIZATION
# ============================================

@dataclass
class FeeStats:
    """Statystyki opłat"""
    total_maker_orders: int = 0
    total_taker_orders: int = 0
    total_fees_paid: float = 0.0
    total_rebates_earned: float = 0.0
    total_slippage: float = 0.0
    avg_slippage_pct: float = 0.0
    savings_vs_all_taker: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'total_maker_orders': self.total_maker_orders,
            'total_taker_orders': self.total_taker_orders,
            'total_fees_paid': round(self.total_fees_paid, 4),
            'total_rebates_earned': round(self.total_rebates_earned, 4),
            'net_fees': round(self.total_fees_paid - self.total_rebates_earned, 4),
            'total_slippage': round(self.total_slippage, 4),
            'avg_slippage_pct': round(self.avg_slippage_pct, 4),
            'savings_vs_all_taker': round(self.savings_vs_all_taker, 4),
            'maker_ratio': round(
                self.total_maker_orders / max(self.total_maker_orders + self.total_taker_orders, 1) * 100, 1
            )
        }


class SmartOrderExecution:
    """
    Smart order execution z optymalizacją maker/taker fees.
    
    Strategia:
    1. Sprawdź spread - jeśli > 0.1% -> Skip trade
    2. Próbuj LIMIT order (maker) na best bid/ask
    3. Czekaj max 30s na fill
    4. Jeśli nie filled -> Cancel i market order fallback
    """
    
    def __init__(self, config: dict):
        """
        Inicjalizacja Smart Order Execution
        
        Args:
            config: Konfiguracja z sekcją 'execution'
        """
        exec_config = config.get('execution', {})
        
        self.enabled = exec_config.get('prefer_maker_orders', True)
        self.limit_order_timeout = exec_config.get('limit_order_timeout', 30)
        self.max_spread_pct = exec_config.get('max_spread_pct', 0.1)
        self.track_slippage = exec_config.get('track_slippage', True)
        self.vip_tier = exec_config.get('vip_tier', 0)
        
        # Fee rates bazowane na VIP tier
        self.fee_rates = self._get_fee_rates(self.vip_tier)
        
        # Statistics
        self.fee_stats = FeeStats()
        self.slippage_history: List[Dict] = []
        
        # Persistence
        self.stats_file = './data/execution/fee_stats.json'
        self._load_stats()
        
        logger.info(f"[OK] SmartOrderExecution zainicjalizowany (VIP Tier: {self.vip_tier})")
    
    def _get_fee_rates(self, vip_tier: int) -> Dict:
        """Zwraca fee rates dla VIP tier"""
        rates = {
            0: {'maker': -0.0001, 'taker': 0.0004},  # Regular: -0.01% maker rebate, 0.04% taker
            1: {'maker': -0.0001, 'taker': 0.0003},  # VIP1: -0.01% maker, 0.03% taker
            2: {'maker': -0.0002, 'taker': 0.0002},  # VIP2: -0.02% maker, 0.02% taker
        }
        return rates.get(vip_tier, rates[0])
    
    def check_spread(self, bid: float, ask: float) -> Tuple[bool, float]:
        """
        Sprawdza czy spread jest akceptowalny.
        
        Args:
            bid: Best bid price
            ask: Best ask price
        
        Returns:
            (is_acceptable, spread_pct)
        """
        if bid <= 0 or ask <= 0:
            return False, 0.0
        
        spread = ask - bid
        spread_pct = (spread / ask) * 100
        
        is_acceptable = spread_pct <= self.max_spread_pct
        
        if not is_acceptable:
            logger.warning(f"[WARNING] Spread za wysoki: {spread_pct:.3f}% > {self.max_spread_pct}%")
        
        return is_acceptable, spread_pct
    
    def estimate_total_cost(
        self,
        quantity: float,
        price: float,
        order_type: str  # 'maker' lub 'taker'
    ) -> Dict:
        """
        Szacuje całkowity koszt zlecenia.
        
        Returns:
            Dict z fee, estimated_slippage, total_cost
        """
        notional = quantity * price
        
        if order_type == 'maker':
            fee_rate = self.fee_rates['maker']
            estimated_slippage_pct = 0.0  # Maker = no slippage
        else:
            fee_rate = self.fee_rates['taker']
            estimated_slippage_pct = 0.02  # ~0.02% average slippage
        
        fee = notional * fee_rate
        slippage = notional * (estimated_slippage_pct / 100)
        
        return {
            'notional': round(notional, 2),
            'fee_rate': fee_rate,
            'fee': round(fee, 4),
            'estimated_slippage_pct': estimated_slippage_pct,
            'estimated_slippage': round(slippage, 4),
            'total_cost': round(fee + slippage, 4),
            'order_type': order_type
        }
    
    def calculate_slippage(
        self,
        expected_price: float,
        actual_price: float,
        side: str
    ) -> float:
        """
        Oblicza slippage.
        
        Returns:
            Slippage jako % (dodatni = niekorzystny)
        """
        if expected_price <= 0:
            return 0.0
        
        if side == 'BUY':
            # Dla BUY: wyższa actual price = niekorzystny slippage
            slippage_pct = ((actual_price - expected_price) / expected_price) * 100
        else:
            # Dla SELL: niższa actual price = niekorzystny slippage
            slippage_pct = ((expected_price - actual_price) / expected_price) * 100
        
        return slippage_pct
    
    def record_order_execution(
        self,
        symbol: str,
        side: str,
        quantity: float,
        expected_price: float,
        actual_price: float,
        order_type: str,  # 'maker' lub 'taker'
        notional: float
    ):
        """Zapisuje wykonanie zlecenia do statystyk"""
        # Fee calculation
        fee_rate = self.fee_rates[order_type]
        fee = notional * fee_rate
        
        if order_type == 'maker':
            self.fee_stats.total_maker_orders += 1
            self.fee_stats.total_rebates_earned += abs(fee)  # Rebate jest ujemny
        else:
            self.fee_stats.total_taker_orders += 1
            self.fee_stats.total_fees_paid += fee
        
        # Slippage
        slippage_pct = self.calculate_slippage(expected_price, actual_price, side)
        slippage_cost = notional * (slippage_pct / 100)
        self.fee_stats.total_slippage += slippage_cost
        
        # Update average slippage
        self.slippage_history.append({
            'symbol': symbol,
            'slippage_pct': slippage_pct,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep last 100
        self.slippage_history = self.slippage_history[-100:]
        
        if self.slippage_history:
            self.fee_stats.avg_slippage_pct = sum(
                s['slippage_pct'] for s in self.slippage_history
            ) / len(self.slippage_history)
        
        # Calculate savings vs all taker
        total_orders = self.fee_stats.total_maker_orders + self.fee_stats.total_taker_orders
        if total_orders > 0:
            # Gdyby wszystkie były taker
            hypothetical_all_taker_fees = (
                self.fee_stats.total_maker_orders * notional * self.fee_rates['taker']
            )
            actual_maker_cost = self.fee_stats.total_maker_orders * notional * self.fee_rates['maker']
            self.fee_stats.savings_vs_all_taker = hypothetical_all_taker_fees - actual_maker_cost
        
        self._save_stats()
        
        logger.debug(
            f"[INFO] Order recorded: {order_type} | Fee: {fee:.4f} | Slippage: {slippage_pct:.4f}%"
        )
    
    def get_optimal_limit_price(
        self,
        side: str,
        bid: float,
        ask: float,
        aggression: float = 0.0
    ) -> float:
        """
        Oblicza optymalną cenę limit order.
        
        Args:
            side: 'BUY' lub 'SELL'
            bid: Best bid
            ask: Best ask
            aggression: 0.0 = passive, 1.0 = aggressive (bliżej mid)
        
        Returns:
            Optymalna cena limit
        """
        spread = ask - bid
        
        if side == 'BUY':
            # Buy: startujemy od bid, możemy iść wyżej
            base_price = bid
            adjustment = spread * aggression
            return round(base_price + adjustment, 8)
        else:
            # Sell: startujemy od ask, możemy iść niżej
            base_price = ask
            adjustment = spread * aggression
            return round(base_price - adjustment, 8)
    
    def get_fee_summary(self) -> Dict:
        """Zwraca podsumowanie fee stats"""
        return self.fee_stats.to_dict()
    
    def detect_vip_tier(self, volume_30d_usdc: float) -> int:
        """
        Wykrywa VIP tier na podstawie 30-day volume.
        
        Args:
            volume_30d_usdc: 30-day trading volume w USDC
        
        Returns:
            VIP tier (0, 1, 2)
        """
        if volume_30d_usdc >= 10_000_000:
            return 2  # VIP2: >$10M
        elif volume_30d_usdc >= 1_000_000:
            return 1  # VIP1: >$1M
        else:
            return 0  # Regular
    
    def update_vip_tier(self, volume_30d_usdc: float):
        """Aktualizuje VIP tier"""
        new_tier = self.detect_vip_tier(volume_30d_usdc)
        if new_tier != self.vip_tier:
            old_tier = self.vip_tier
            self.vip_tier = new_tier
            self.fee_rates = self._get_fee_rates(new_tier)
            logger.info(f"[UP] VIP Tier upgraded: {old_tier} -> {new_tier}")
    
    def _save_stats(self):
        """Zapisuje statystyki do pliku"""
        try:
            os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)
            
            data = {
                'fee_stats': self.fee_stats.to_dict(),
                'slippage_history': self.slippage_history[-50:],  # Keep last 50
                'vip_tier': self.vip_tier,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.stats_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Błąd zapisu fee stats: {e}")
    
    def _load_stats(self):
        """Ładuje statystyki z pliku"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                
                stats = data.get('fee_stats', {})
                self.fee_stats = FeeStats(
                    total_maker_orders=stats.get('total_maker_orders', 0),
                    total_taker_orders=stats.get('total_taker_orders', 0),
                    total_fees_paid=stats.get('total_fees_paid', 0.0),
                    total_rebates_earned=stats.get('total_rebates_earned', 0.0),
                    total_slippage=stats.get('total_slippage', 0.0),
                    avg_slippage_pct=stats.get('avg_slippage_pct', 0.0),
                    savings_vs_all_taker=stats.get('savings_vs_all_taker', 0.0)
                )
                
                self.slippage_history = data.get('slippage_history', [])
                self.vip_tier = data.get('vip_tier', 0)
                
                logger.info(f"[FOLDER] Załadowano fee stats z {self.stats_file}")
                
        except Exception as e:
            logger.warning(f"Nie udało się załadować fee stats: {e}")


class OrderType(Enum):
    """Typ zlecenia"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class OrderSide(Enum):
    """Strona zlecenia"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Status zlecenia"""
    NEW = "NEW"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class Order:
    """Struktura zlecenia"""
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float]
    stop_price: Optional[float]
    status: str
    filled_qty: float
    avg_price: float
    created_at: str
    updated_at: str
    is_paper: bool = True
    
    def to_dict(self) -> Dict:
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side,
            'order_type': self.order_type,
            'quantity': self.quantity,
            'price': self.price,
            'stop_price': self.stop_price,
            'status': self.status,
            'filled_qty': self.filled_qty,
            'avg_price': self.avg_price,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'is_paper': self.is_paper
        }


@dataclass
class Position:
    """Otwarta pozycja"""
    symbol: str
    side: str  # 'LONG' lub 'SHORT'
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss_order_id: Optional[str] = None
    take_profit_order_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    opened_at: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'side': self.side,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'current_price': self.current_price,
            'unrealized_pnl': self.unrealized_pnl,
            'stop_loss_order_id': self.stop_loss_order_id,
            'take_profit_order_id': self.take_profit_order_id,
            'entry_order_id': self.entry_order_id,
            'opened_at': self.opened_at
        }


class ExecutionLayer:
    """
    Warstwa wykonawcza - obsługuje zlecenia i pozycje
    
    Wspiera:
    - Paper trading (domyślnie)
    - Real trading na Binance Testnet
    - Scale Out (Partial Profit Taking) v3.0
    - Smart Order Execution v3.0
    """
    
    def __init__(self, config: dict, discord_notifier=None):
        """
        Inicjalizacja
        
        Args:
            config: Konfiguracja
            discord_notifier: Opcjonalny notifier Discord
        """
        self.config = config
        self.binance_config = config.get('binance', {})
        self.paper_config = config.get('paper_trading', {})
        self.safety_config = config.get('safety', {})
        self.discord_notifier = discord_notifier
        
        # Paper trading settings
        self.paper_trading_enabled = self.paper_config.get('enabled', True)
        self.simulated_fee_pct = self.paper_config.get('simulated_fee_pct', 0.1)
        self.simulated_slippage_pct = self.paper_config.get('simulated_slippage_pct', 0.05)
        
        # Safety
        self.force_testnet = self.safety_config.get('force_testnet_only', True)
        
        # Binance client
        self.client = None
        if not self.paper_trading_enabled:
            self._init_binance_client()
        
        # Stan
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
        self.order_counter = 0
        
        # Symbol info cache
        self.symbol_info: Dict[str, Dict] = {}
        
        # Ścieżki plików
        self.data_path = './data/execution/'
        os.makedirs(self.data_path, exist_ok=True)
        self.orders_file = os.path.join(self.data_path, 'orders.json')
        self.positions_file = os.path.join(self.data_path, 'positions.json')
        
        # Scale Out Manager (Partial Profit Taking)
        self.scale_out_manager: Optional[ScaleOutManager] = None
        profit_config = config.get('profit_taking', {})
        if profit_config.get('scale_out', {}).get('enabled', True):
            self.scale_out_manager = ScaleOutManager(config, discord_notifier)
            self.scale_out_manager.on_partial_close = self._handle_partial_close
        
        # Smart Order Execution
        self.smart_execution: Optional[SmartOrderExecution] = None
        exec_config = config.get('execution', {})
        if exec_config.get('prefer_maker_orders', True):
            self.smart_execution = SmartOrderExecution(config)
        
        self._load_state()
        
        mode = "PAPER" if self.paper_trading_enabled else "TESTNET"
        logger.info(f"[OK] ExecutionLayer zainicjalizowany (mode: {mode})")
    
    def _init_binance_client(self):
        """Inicjalizuje klienta Binance"""
        try:
            api_key = self.binance_config.get('api_key', '')
            api_secret = self.binance_config.get('api_secret', '')
            
            if not api_key or not api_secret or api_key == 'YOUR_TESTNET_API_KEY':
                logger.warning("[WARNING] Brak kluczy API - tylko paper trading")
                self.paper_trading_enabled = True
                return
            
            use_testnet = self.binance_config.get('testnet', True)
            
            if self.force_testnet and not use_testnet:
                raise ValueError("BEZPIECZEŃSTWO: Wymuszono użycie testnet!")
            
            self.client = Client(api_key, api_secret, testnet=use_testnet)
            self.client.ping()
            
            logger.info("[OK] Połączono z Binance API (Testnet)")
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd połączenia z Binance: {e}")
            logger.info("Przełączam na paper trading")
            self.paper_trading_enabled = True
    
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reduce_only: bool = False,
        reference_price: float = None
    ) -> Optional[Order]:
        """
        Składa zlecenie market
        
        Args:
            symbol: Para walutowa
            side: 'BUY' lub 'SELL'
            quantity: Ilość
            reduce_only: Czy tylko zamyka pozycję
            reference_price: Cena referencyjna dla paper trading
        
        Returns:
            Order lub None
        """
        logger.info(f"[UPLOAD] Market order: {side} {quantity} {symbol}")
        
        if self.paper_trading_enabled:
            return self._paper_market_order(symbol, side, quantity, reference_price)
        else:
            return self._binance_market_order(symbol, side, quantity)
    
    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float
    ) -> Optional[Order]:
        """
        Składa zlecenie limit
        
        Args:
            symbol: Para walutowa
            side: 'BUY' lub 'SELL'
            quantity: Ilość
            price: Cena limit
        
        Returns:
            Order lub None
        """
        logger.info(f"[UPLOAD] Limit order: {side} {quantity} {symbol} @ {price}")
        
        if self.paper_trading_enabled:
            return self._paper_limit_order(symbol, side, quantity, price)
        else:
            return self._binance_limit_order(symbol, side, quantity, price)
    
    def place_stop_loss_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        limit_price: Optional[float] = None
    ) -> Optional[Order]:
        """
        Składa zlecenie stop loss
        
        Args:
            symbol: Para walutowa
            side: 'BUY' (dla short) lub 'SELL' (dla long)
            quantity: Ilość
            stop_price: Cena aktywacji
            limit_price: Cena limit (opcjonalnie)
        
        Returns:
            Order lub None
        """
        order_type = 'STOP_LOSS_LIMIT' if limit_price else 'STOP_LOSS'
        logger.info(f"[UPLOAD] Stop Loss order: {side} {quantity} {symbol} @ stop {stop_price}")
        
        if self.paper_trading_enabled:
            return self._paper_stop_order(symbol, side, quantity, stop_price, limit_price, 'SL')
        else:
            return self._binance_stop_order(symbol, side, quantity, stop_price, limit_price, 'SL')
    
    def place_take_profit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        limit_price: Optional[float] = None
    ) -> Optional[Order]:
        """
        Składa zlecenie take profit
        
        Args:
            symbol: Para walutowa
            side: 'BUY' (dla short) lub 'SELL' (dla long)
            quantity: Ilość
            stop_price: Cena aktywacji
            limit_price: Cena limit (opcjonalnie)
        
        Returns:
            Order lub None
        """
        logger.info(f"[UPLOAD] Take Profit order: {side} {quantity} {symbol} @ {stop_price}")
        
        if self.paper_trading_enabled:
            return self._paper_stop_order(symbol, side, quantity, stop_price, limit_price, 'TP')
        else:
            return self._binance_stop_order(symbol, side, quantity, stop_price, limit_price, 'TP')
    
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        Anuluje zlecenie
        
        Returns:
            True jeśli anulowano
        """
        logger.info(f"[ERROR] Anulowanie zlecenia {order_id}")
        
        if self.paper_trading_enabled:
            if order_id in self.orders:
                self.orders[order_id].status = OrderStatus.CANCELED.value
                self._save_state()
                return True
            return False
        else:
            try:
                self.client.cancel_order(symbol=symbol, orderId=order_id)
                if order_id in self.orders:
                    self.orders[order_id].status = OrderStatus.CANCELED.value
                self._save_state()
                return True
            except BinanceAPIException as e:
                logger.error(f"Błąd anulowania zlecenia: {e}")
                return False
    
    def open_position(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float
    ) -> Tuple[bool, Optional[Position], List[Order]]:
        """
        Otwiera pełną pozycję z SL i TP
        
        Args:
            symbol: Para walutowa
            direction: 'LONG' lub 'SHORT'
            quantity: Ilość
            entry_price: Cena wejścia (dla market = aktualna)
            stop_loss: Poziom SL
            take_profit: Poziom TP
        
        Returns:
            (success, Position, [orders])
        """
        logger.info(f"[TARGET] Opening {direction} position: {symbol}")
        
        orders = []
        
        try:
            # Walidacja entry_price
            if entry_price is None or entry_price <= 0:
                logger.error(f"[ERROR] Invalid entry_price: {entry_price} for {symbol}")
                return False, None, []
            
            logger.info(f"[DEBUG] open_position - entry_price: {entry_price}")
            
            # 1. Entry order (market)
            entry_side = 'BUY' if direction == 'LONG' else 'SELL'
            entry_order = self.place_market_order(symbol, entry_side, quantity, reference_price=entry_price)
            
            if not entry_order or entry_order.status != OrderStatus.FILLED.value:
                logger.error(f"[ERROR] Entry order failed for {symbol}")
                return False, None, []
            
            orders.append(entry_order)
            actual_entry_price = entry_order.avg_price
            
            # 2. Stop Loss order
            sl_side = 'SELL' if direction == 'LONG' else 'BUY'
            sl_order = self.place_stop_loss_order(symbol, sl_side, quantity, stop_loss)
            if sl_order:
                orders.append(sl_order)
            
            # 3. Take Profit order
            tp_order = self.place_take_profit_order(symbol, sl_side, quantity, take_profit)
            if tp_order:
                orders.append(tp_order)
            
            # 4. Utwórz pozycję
            position = Position(
                symbol=symbol,
                side=direction,
                quantity=quantity,
                entry_price=actual_entry_price,
                current_price=actual_entry_price,
                unrealized_pnl=0.0,
                stop_loss_order_id=sl_order.order_id if sl_order else None,
                take_profit_order_id=tp_order.order_id if tp_order else None,
                entry_order_id=entry_order.order_id,
                opened_at=datetime.now().isoformat()
            )
            
            self.positions[symbol] = position
            self._save_state()
            
            logger.info(
                f"[OK] Pozycja otwarta: {symbol} {direction} | "
                f"Entry: {actual_entry_price:.2f} | "
                f"SL: {stop_loss:.2f} | TP: {take_profit:.2f}"
            )
            
            return True, position, orders
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd otwierania pozycji: {e}")
            return False, None, orders
    
    def close_position(
        self,
        symbol: str,
        reason: str = "MANUAL"
    ) -> Tuple[bool, float, Optional[Order]]:
        """
        Zamyka pozycję
        
        Args:
            symbol: Para walutowa
            reason: Powód zamknięcia
        
        Returns:
            (success, realized_pnl, close_order)
        """
        if symbol not in self.positions:
            logger.warning(f"[WARNING] Brak otwartej pozycji dla {symbol}")
            return False, 0.0, None
        
        position = self.positions[symbol]
        logger.info(f"[LOCK] Closing position: {symbol} ({reason})")
        
        try:
            # Anuluj SL/TP orders
            if position.stop_loss_order_id:
                self.cancel_order(symbol, position.stop_loss_order_id)
            if position.take_profit_order_id:
                self.cancel_order(symbol, position.take_profit_order_id)
            
            # Close order
            close_side = 'SELL' if position.side == 'LONG' else 'BUY'
            close_order = self.place_market_order(
                symbol, close_side, position.quantity, reduce_only=True
            )
            
            if not close_order or close_order.status != OrderStatus.FILLED.value:
                logger.error(f"[ERROR] Close order failed for {symbol}")
                return False, 0.0, None
            
            # Oblicz PnL
            exit_price = close_order.avg_price
            if position.side == 'LONG':
                pnl = (exit_price - position.entry_price) * position.quantity
            else:
                pnl = (position.entry_price - exit_price) * position.quantity
            
            # Usuń pozycję
            del self.positions[symbol]
            self._save_state()
            
            logger.info(
                f"[OK] Pozycja zamknięta: {symbol} | "
                f"Exit: {exit_price:.2f} | PnL: {pnl:+.2f} USDC"
            )
            
            return True, pnl, close_order
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd zamykania pozycji: {e}")
            return False, 0.0, None
    
    def update_position_price(self, symbol: str, current_price: float):
        """Aktualizuje cenę i unrealized PnL"""
        if symbol in self.positions:
            position = self.positions[symbol]
            position.current_price = current_price
            
            if position.side == 'LONG':
                position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
            else:
                position.unrealized_pnl = (position.entry_price - current_price) * position.quantity
    
    def check_stop_orders(self, symbol: str, current_price: float) -> Optional[str]:
        """
        Sprawdza czy SL/TP został aktywowany (dla paper trading)
        
        Returns:
            'STOP_LOSS', 'TAKE_PROFIT' lub None
        """
        if symbol not in self.positions:
            return None
        
        position = self.positions[symbol]
        
        # Sprawdź SL
        if position.stop_loss_order_id and position.stop_loss_order_id in self.orders:
            sl_order = self.orders[position.stop_loss_order_id]
            if sl_order.status == OrderStatus.NEW.value:
                stop_price = sl_order.stop_price or 0
                
                if position.side == 'LONG' and current_price <= stop_price:
                    return 'STOP_LOSS'
                elif position.side == 'SHORT' and current_price >= stop_price:
                    return 'STOP_LOSS'
        
        # Sprawdź TP
        if position.take_profit_order_id and position.take_profit_order_id in self.orders:
            tp_order = self.orders[position.take_profit_order_id]
            if tp_order.status == OrderStatus.NEW.value:
                stop_price = tp_order.stop_price or 0
                
                if position.side == 'LONG' and current_price >= stop_price:
                    return 'TAKE_PROFIT'
                elif position.side == 'SHORT' and current_price <= stop_price:
                    return 'TAKE_PROFIT'
        
        return None
    
    def get_open_positions(self) -> Dict[str, Position]:
        """Zwraca otwarte pozycje"""
        return dict(self.positions)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Zwraca pozycję dla symbolu"""
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """Sprawdza czy jest otwarta pozycja"""
        return symbol in self.positions
    
    # ========================================
    # PAPER TRADING METHODS
    # ========================================
    
    def _paper_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reference_price: float = None
    ) -> Order:
        """Symulowane zlecenie market"""
        self.order_counter += 1
        order_id = f"PAPER_{self.order_counter}_{int(time.time())}"
        
        # Uzyj reference_price jesli podana, w przeciwnym razie symuluj
        if reference_price is not None and reference_price > 0:
            current_price = reference_price
            logger.debug(f"[DEBUG] Using reference_price: {reference_price}")
        else:
            current_price = self._get_simulated_price(symbol)
            logger.warning(f"[WARNING] No reference_price, using simulated: {current_price}")
        
        # Walidacja ceny
        if current_price <= 0 or current_price > 1000000:
            logger.error(f"[ERROR] Invalid price: {current_price} for {symbol}")
            current_price = self._get_simulated_price(symbol)
        
        # Dodaj slippage
        if side == 'BUY':
            exec_price = current_price * (1 + self.simulated_slippage_pct / 100)
        else:
            exec_price = current_price * (1 - self.simulated_slippage_pct / 100)
        
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET.value,
            quantity=quantity,
            price=None,
            stop_price=None,
            status=OrderStatus.FILLED.value,
            filled_qty=quantity,
            avg_price=exec_price,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            is_paper=True
        )
        
        self.orders[order_id] = order
        self._save_state()
        
        logger.info(f"[LOG] Paper Market: {side} {quantity} {symbol} @ {exec_price:.2f}")
        return order
    
    def _paper_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float
    ) -> Order:
        """Symulowane zlecenie limit"""
        self.order_counter += 1
        order_id = f"PAPER_{self.order_counter}_{int(time.time())}"
        
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT.value,
            quantity=quantity,
            price=price,
            stop_price=None,
            status=OrderStatus.NEW.value,
            filled_qty=0,
            avg_price=0,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            is_paper=True
        )
        
        self.orders[order_id] = order
        self._save_state()
        
        logger.info(f"[LOG] Paper Limit: {side} {quantity} {symbol} @ {price:.2f}")
        return order
    
    def _paper_stop_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        limit_price: Optional[float],
        order_type: str  # 'SL' or 'TP'
    ) -> Order:
        """Symulowane zlecenie stop"""
        self.order_counter += 1
        order_id = f"PAPER_{self.order_counter}_{int(time.time())}"
        
        ot = OrderType.STOP_LOSS if order_type == 'SL' else OrderType.TAKE_PROFIT
        if limit_price:
            ot = OrderType.STOP_LOSS_LIMIT if order_type == 'SL' else OrderType.TAKE_PROFIT_LIMIT
        
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=ot.value,
            quantity=quantity,
            price=limit_price,
            stop_price=stop_price,
            status=OrderStatus.NEW.value,
            filled_qty=0,
            avg_price=0,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            is_paper=True
        )
        
        self.orders[order_id] = order
        self._save_state()
        
        logger.info(f"[LOG] Paper {order_type}: {side} {quantity} {symbol} @ stop {stop_price:.2f}")
        return order
    
    def _get_simulated_price(self, symbol: str) -> float:
        """Pobiera symulowana cene (w prawdziwym bocie uzyj DataFetcher)"""
        # Domyslne ceny dla paper trading - ZAKTUALIZOWANE!
        default_prices = {
            # USDC pairs
            'BTCUSDC': 95000.0,
            'ETHUSDC': 2700.0,
            'SOLUSDC': 150.0,
            'XRPUSDC': 2.5,
            'DOGEUSDC': 0.25,
            'ADAUSDC': 0.75,
            'AVAXUSDC': 35.0,
            'MATICUSDC': 0.50,
            # USDT pairs (Testnet)
            'BTCUSDT': 95000.0,
            'ETHUSDT': 2700.0,
            'SOLUSDT': 150.0,
            'XRPUSDT': 2.5,
            'DOGEUSDT': 0.25,
            'ADAUSDT': 0.75,
            'AVAXUSDT': 35.0,
            'MATICUSDT': 0.50,
        }
        price = default_prices.get(symbol)
        if price is None:
            logger.warning(f"[WARNING] No default price for {symbol}, using 100.0 - THIS IS A BUG!")
            return 100.0
        return price
    
    # ========================================
    # BINANCE API METHODS
    # ========================================
    
    def _binance_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float
    ) -> Optional[Order]:
        """Rzeczywiste zlecenie market na Binance"""
        if not self.client:
            logger.error("Binance client nie zainicjalizowany")
            return None
        
        try:
            response = self.client.create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )
            
            order = Order(
                order_id=str(response['orderId']),
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET.value,
                quantity=float(response['origQty']),
                price=None,
                stop_price=None,
                status=response['status'],
                filled_qty=float(response.get('executedQty', 0)),
                avg_price=float(response.get('fills', [{}])[0].get('price', 0)) if response.get('fills') else 0,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                is_paper=False
            )
            
            self.orders[order.order_id] = order
            self._save_state()
            
            return order
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error: {e}")
            return None
    
    def _binance_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float
    ) -> Optional[Order]:
        """Rzeczywiste zlecenie limit na Binance"""
        if not self.client:
            return None
        
        try:
            response = self.client.create_order(
                symbol=symbol,
                side=side,
                type='LIMIT',
                timeInForce='GTC',
                quantity=quantity,
                price=price
            )
            
            order = Order(
                order_id=str(response['orderId']),
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT.value,
                quantity=float(response['origQty']),
                price=float(response['price']),
                stop_price=None,
                status=response['status'],
                filled_qty=float(response.get('executedQty', 0)),
                avg_price=0,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                is_paper=False
            )
            
            self.orders[order.order_id] = order
            self._save_state()
            
            return order
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error: {e}")
            return None
    
    def _binance_stop_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        limit_price: Optional[float],
        order_type: str
    ) -> Optional[Order]:
        """Rzeczywiste zlecenie stop na Binance"""
        if not self.client:
            return None
        
        try:
            ot = 'STOP_LOSS_LIMIT' if limit_price else 'STOP_LOSS'
            
            params = {
                'symbol': symbol,
                'side': side,
                'type': ot,
                'quantity': quantity,
                'stopPrice': stop_price
            }
            
            if limit_price:
                params['price'] = limit_price
                params['timeInForce'] = 'GTC'
            
            response = self.client.create_order(**params)
            
            order = Order(
                order_id=str(response['orderId']),
                symbol=symbol,
                side=side,
                order_type=ot,
                quantity=float(response['origQty']),
                price=float(response.get('price', 0)) if response.get('price') else None,
                stop_price=float(response['stopPrice']),
                status=response['status'],
                filled_qty=float(response.get('executedQty', 0)),
                avg_price=0,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                is_paper=False
            )
            
            self.orders[order.order_id] = order
            self._save_state()
            
            return order
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error: {e}")
            return None
    
    # ========================================
    # PERSISTENCE
    # ========================================
    
    # ========================================
    # SMART ORDER EXECUTION METHODS
    # ========================================
    
    def execute_order_smart(
        self,
        symbol: str,
        side: str,
        quantity: float,
        expected_price: float,
        bid: float = 0.0,
        ask: float = 0.0
    ) -> Tuple[Optional[Order], str]:
        """
        Wykonuje zlecenie używając smart execution.
        
        Strategia:
        1. Sprawdź spread
        2. Spróbuj LIMIT order (maker)
        3. Fallback do MARKET jeśli limit nie filled
        
        Args:
            symbol: Para walutowa
            side: 'BUY' lub 'SELL'
            quantity: Ilość
            expected_price: Oczekiwana cena
            bid: Best bid (opcjonalnie)
            ask: Best ask (opcjonalnie)
        
        Returns:
            (Order, order_type) gdzie order_type to 'maker' lub 'taker'
        """
        if not self.smart_execution or not self.smart_execution.enabled:
            # Fallback do market order - uzyj expected_price jako reference
            order = self.place_market_order(symbol, side, quantity, reference_price=expected_price)
            if order and self.smart_execution:
                self.smart_execution.record_order_execution(
                    symbol, side, quantity, expected_price, order.avg_price,
                    'taker', quantity * order.avg_price
                )
            return order, 'taker'
        
        # Sprawdź spread
        if bid > 0 and ask > 0:
            is_acceptable, spread_pct = self.smart_execution.check_spread(bid, ask)
            if not is_acceptable:
                logger.warning(f"[ERROR] {symbol}: Spread za wysoki ({spread_pct:.3f}%), skip trade")
                return None, 'spread_too_high'
        
        # Próbuj LIMIT order (maker)
        if bid > 0 and ask > 0:
            limit_price = self.smart_execution.get_optimal_limit_price(side, bid, ask)
            
            logger.info(f"[UPLOAD] Smart Limit: {side} {quantity} {symbol} @ {limit_price:.2f}")
            limit_order = self.place_limit_order(symbol, side, quantity, limit_price)
            
            if limit_order:
                # Czekaj na fill
                timeout = self.smart_execution.limit_order_timeout
                start_time = time.time()
                
                while time.time() - start_time < timeout:
                    # W paper trading, symulujemy natychmiastowy fill
                    if self.paper_trading_enabled:
                        # Symuluj fill z pewnym prawdopodobieństwem
                        limit_order.status = OrderStatus.FILLED.value
                        limit_order.filled_qty = quantity
                        limit_order.avg_price = limit_price
                        break
                    else:
                        # Sprawdź status na Binance
                        try:
                            status = self.client.get_order(symbol=symbol, orderId=limit_order.order_id)
                            if status['status'] == 'FILLED':
                                limit_order.status = OrderStatus.FILLED.value
                                limit_order.filled_qty = float(status['executedQty'])
                                limit_order.avg_price = float(status.get('avgPrice', limit_price))
                                break
                        except:
                            pass
                    
                    time.sleep(1)
                
                if limit_order.status == OrderStatus.FILLED.value:
                    # Sukces - maker order
                    self.smart_execution.record_order_execution(
                        symbol, side, quantity, expected_price, limit_order.avg_price,
                        'maker', quantity * limit_order.avg_price
                    )
                    logger.info(f"[OK] Maker order filled: {symbol} @ {limit_order.avg_price:.2f}")
                    return limit_order, 'maker'
                else:
                    # Timeout - cancel i fallback do market
                    self.cancel_order(symbol, limit_order.order_id)
                    logger.info(f"[TIMER] Limit timeout, fallback to market")
        
        # Fallback do market order - uzyj expected_price jako reference
        market_order = self.place_market_order(symbol, side, quantity, reference_price=expected_price)
        if market_order:
            self.smart_execution.record_order_execution(
                symbol, side, quantity, expected_price, market_order.avg_price,
                'taker', quantity * market_order.avg_price
            )
        return market_order, 'taker'
    
    def _handle_partial_close(self, symbol: str, level: 'ScaleOutLevel', current_price: float):
        """
        Handler dla partial close z ScaleOutManager.
        
        Args:
            symbol: Para walutowa
            level: Triggered level
            current_price: Aktualna cena
        """
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        # Wykonaj partial close
        close_side = 'SELL' if position.side == 'LONG' else 'BUY'
        close_order = self.place_market_order(symbol, close_side, level.quantity, reduce_only=True)
        
        if close_order and close_order.status == OrderStatus.FILLED.value:
            actual_price = close_order.avg_price
            
            # Zarejestruj w scale out manager
            if self.scale_out_manager:
                closed_qty, pnl = self.scale_out_manager.execute_partial_close(
                    symbol, level, actual_price
                )
                
                # Aktualizuj SL
                new_sl = self.scale_out_manager.update_stop_loss_after_tp(symbol, level.level_id)
                
                if new_sl and self.positions[symbol].stop_loss_order_id:
                    # Anuluj stary SL i utwórz nowy
                    self.cancel_order(symbol, self.positions[symbol].stop_loss_order_id)
                    
                    remaining_qty = self.scale_out_manager.get_remaining_quantity(symbol)
                    new_sl_order = self.place_stop_loss_order(
                        symbol, close_side, remaining_qty, new_sl
                    )
                    
                    if new_sl_order:
                        self.positions[symbol].stop_loss_order_id = new_sl_order.order_id
                
                # Aktualizuj quantity w pozycji
                self.positions[symbol].quantity = self.scale_out_manager.get_remaining_quantity(symbol)
                self._save_state()
    
    def open_position_with_scale_out(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        entry_price: float,
        stop_loss: float
    ) -> Tuple[bool, Optional[Position], List[Order]]:
        """
        Otwiera pozycję z scale out (bez pojedynczego TP).
        
        Args:
            symbol: Para walutowa
            direction: 'LONG' lub 'SHORT'
            quantity: Ilość
            entry_price: Cena wejścia
            stop_loss: Poziom SL
        
        Returns:
            (success, Position, [orders])
        """
        logger.info(f"[TARGET] Opening {direction} position with scale out: {symbol}")
        
        orders = []
        
        try:
            # 1. Entry order (market lub smart)
            entry_side = 'BUY' if direction == 'LONG' else 'SELL'
            entry_order, order_type = self.execute_order_smart(
                symbol, entry_side, quantity, entry_price
            )
            
            if not entry_order or entry_order.status != OrderStatus.FILLED.value:
                logger.error(f"[ERROR] Entry order failed for {symbol}")
                return False, None, []
            
            orders.append(entry_order)
            actual_entry_price = entry_order.avg_price
            
            # 2. Rejestruj w Scale Out Manager
            if self.scale_out_manager:
                self.scale_out_manager.register_position(
                    symbol=symbol,
                    entry_price=actual_entry_price,
                    stop_loss=stop_loss,
                    quantity=quantity,
                    direction=direction
                )
            
            # 3. Stop Loss order
            sl_side = 'SELL' if direction == 'LONG' else 'BUY'
            sl_order = self.place_stop_loss_order(symbol, sl_side, quantity, stop_loss)
            if sl_order:
                orders.append(sl_order)
            
            # 4. Utwórz pozycję (bez TP - scale out zarządza TP)
            position = Position(
                symbol=symbol,
                side=direction,
                quantity=quantity,
                entry_price=actual_entry_price,
                current_price=actual_entry_price,
                unrealized_pnl=0.0,
                stop_loss_order_id=sl_order.order_id if sl_order else None,
                take_profit_order_id=None,  # Scale out zarządza TP
                entry_order_id=entry_order.order_id,
                opened_at=datetime.now().isoformat()
            )
            
            self.positions[symbol] = position
            self._save_state()
            
            # Log scale out levels
            if self.scale_out_manager:
                stats = self.scale_out_manager.get_scale_out_stats(symbol)
                if stats:
                    logger.info(
                        f"[OK] Pozycja otwarta z scale out: {symbol} {direction} | "
                        f"Entry: {actual_entry_price:.2f} | SL: {stop_loss:.2f}"
                    )
            
            return True, position, orders
            
        except Exception as e:
            logger.error(f"[ERROR] Błąd otwierania pozycji: {e}")
            return False, None, orders
    
    def get_fee_stats(self) -> Optional[Dict]:
        """Zwraca statystyki fee"""
        if self.smart_execution:
            return self.smart_execution.get_fee_summary()
        return None
    
    def get_scale_out_stats(self, symbol: str = None) -> Optional[Dict]:
        """Zwraca statystyki scale out"""
        if not self.scale_out_manager:
            return None
        
        if symbol:
            return self.scale_out_manager.get_scale_out_stats(symbol)
        
        # Zwróć wszystkie
        return {
            s: self.scale_out_manager.get_scale_out_stats(s) 
            for s in self.scale_out_manager.active_scale_outs.keys()
        }
    
    def start_scale_out_monitoring(self, price_callback):
        """Uruchamia monitoring scale out"""
        if self.scale_out_manager:
            self.scale_out_manager.start_monitoring(price_callback)
    
    def stop_scale_out_monitoring(self):
        """Zatrzymuje monitoring scale out"""
        if self.scale_out_manager:
            self.scale_out_manager.stop_monitoring_thread()
    
    # ========================================
    # PERSISTENCE
    # ========================================
    
    def _save_state(self):
        """Zapisuje stan"""
        try:
            # Orders
            with open(self.orders_file, 'w') as f:
                json.dump(
                    {oid: o.to_dict() for oid, o in self.orders.items()},
                    f, indent=2
                )
            
            # Positions
            with open(self.positions_file, 'w') as f:
                json.dump(
                    {s: p.to_dict() for s, p in self.positions.items()},
                    f, indent=2
                )
                
        except Exception as e:
            logger.error(f"Błąd zapisu stanu: {e}")
    
    def _load_state(self):
        """Ładuje stan"""
        try:
            if os.path.exists(self.orders_file):
                with open(self.orders_file, 'r') as f:
                    data = json.load(f)
                    self.orders = {
                        oid: Order(**odata) for oid, odata in data.items()
                    }
                    # Aktualizuj counter
                    for oid in self.orders.keys():
                        if oid.startswith('PAPER_'):
                            parts = oid.split('_')
                            if len(parts) > 1:
                                try:
                                    num = int(parts[1])
                                    self.order_counter = max(self.order_counter, num)
                                except:
                                    pass
            
            if os.path.exists(self.positions_file):
                with open(self.positions_file, 'r') as f:
                    data = json.load(f)
                    self.positions = {
                        s: Position(**pdata) for s, pdata in data.items()
                    }
                    
        except Exception as e:
            logger.warning(f"Błąd ładowania stanu: {e}")


if __name__ == "__main__":
    # Test modułu
    import yaml
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Test Execution Layer (paper trading)
    executor = ExecutionLayer(config)
    
    # Test otwarcia pozycji
    success, position, orders = executor.open_position(
        symbol='BTCUSDC',
        direction='LONG',
        quantity=0.001,
        entry_price=50000,
        stop_loss=49000,
        take_profit=52000
    )
    
    print(f"\n[OK] Position opened: {success}")
    if position:
        print(f"   Symbol: {position.symbol}")
        print(f"   Side: {position.side}")
        print(f"   Entry: {position.entry_price}")
        print(f"   Quantity: {position.quantity}")
    
    print(f"\n[CLIPBOARD] Orders created: {len(orders)}")
    for order in orders:
        print(f"   - {order.order_type}: {order.side} @ {order.price or order.stop_price or order.avg_price}")
    
    # Symuluj zmianę ceny
    executor.update_position_price('BTCUSDC', 51000)
    pos = executor.get_position('BTCUSDC')
    if pos:
        print(f"\n[$] Unrealized PnL: {pos.unrealized_pnl:+.2f} USDC")
    
    # Zamknij pozycję
    success, pnl, close_order = executor.close_position('BTCUSDC', 'TEST')
    print(f"\n[LOCK] Position closed: PnL = {pnl:+.2f} USDC")
