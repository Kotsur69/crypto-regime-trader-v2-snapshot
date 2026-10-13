#!/usr/bin/env python3
"""
main.py - Główny plik bota tradingowego

Uruchomienie:
    python main.py                  # Normalny tryb
    python main.py --backtest       # Tryb backtestingu
    python main.py --paper          # Paper trading (domyślnie)
    python main.py --status         # Pokaż status
    python main.py --optimize       # ML optimization
    python main.py --dashboard      # Uruchom tylko dashboard

Zaawansowane funkcje (v2.0):
- Discord Notifications
- Web Dashboard (Flask)
- Fibonacci & Support/Resistance
- Machine Learning Optimization
- Portfolio Rebalancing
- Order Book Analysis
- Market Regime Detection
"""

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import yaml
import pandas as pd

# Import modułów podstawowych
from data_fetcher import DataFetcher
from indicators import TechnicalIndicators
from pattern_analyzer import PatternAnalyzer
from decision_engine import DecisionEngine, Decision
from risk_manager import RiskManager
from learning_module import LearningModule
from execution_layer import ExecutionLayer
from backtester import Backtester

# Import modułów zaawansowanych (opcjonalne - graceful degradation)
try:
    from discord_notifier import DiscordNotifier, AlertType
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

try:
    from dashboard import Dashboard
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False

try:
    from technical_levels import TechnicalLevels
    TECHNICAL_LEVELS_AVAILABLE = True
except ImportError:
    TECHNICAL_LEVELS_AVAILABLE = False

try:
    from market_regime import MarketRegimeDetector, MarketRegime
    MARKET_REGIME_AVAILABLE = True
except ImportError:
    MARKET_REGIME_AVAILABLE = False

try:
    from orderbook_analyzer import OrderBookAnalyzer
    ORDERBOOK_AVAILABLE = True
except ImportError:
    ORDERBOOK_AVAILABLE = False

try:
    from portfolio_manager import PortfolioManager, RebalanceReason
    PORTFOLIO_AVAILABLE = True
except ImportError:
    PORTFOLIO_AVAILABLE = False

try:
    from ml_optimizer import MLOptimizer, optimize as ml_optimize
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

# ============================================
# KONFIGURACJA LOGGERA
# ============================================

def setup_logging(config: dict):
    """Konfiguruje system logowania"""
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO'))
    log_path = log_config.get('log_path', './logs/')
    
    os.makedirs(log_path, exist_ok=True)
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # File handler
    log_file = os.path.join(
        log_path,
        f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log"
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    return logging.getLogger(__name__)


# ============================================
# GŁÓWNA KLASA BOTA
# ============================================

class TradingBot:
    """Główna klasa koordynująca działanie bota"""
    
    def __init__(self, config_path: str = 'config.yaml'):
        """
        Inicjalizacja bota
        
        Args:
            config_path: Ścieżka do pliku konfiguracji
        """
        # Wczytaj konfigurację
        self.config = self._load_config(config_path)
        
        # Setup logging
        self.logger = setup_logging(self.config)
        self.logger.info("=" * 60)
        self.logger.info("[BOT] CRYPTO TRADING BOT - STARTING")
        self.logger.info("=" * 60)
        
        # Flagi kontrolne
        self.running = False
        self.shutdown_requested = False
        
        # Parametry z konfiguracji
        self.trading_config = self.config.get('trading', {})
        self.pairs = self.trading_config.get('pairs', ['BTCUSDC'])
        self.primary_timeframe = self.trading_config.get('primary_timeframe', '15m')
        self.trend_timeframe = self.trading_config.get('trend_timeframe', '1h')
        
        # Inicjalizacja modułów
        self._init_modules()
        
        # Rejestruj signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("[OK] Bot zainicjalizowany pomyślnie")
    
    def _load_config(self, config_path: str) -> dict:
        """Wczytuje konfigurację z pliku"""
        # Próbuj najpierw config_local.yaml
        local_config = config_path.replace('.yaml', '_local.yaml')
        
        if os.path.exists(local_config):
            config_path = local_config
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Plik konfiguracji nie znaleziony: {config_path}")
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _init_modules(self):
        """Inicjalizuje wszystkie moduły"""
        self.logger.info("[PACKAGE] Inicjalizacja modułów...")
        
        try:
            # Data Fetcher
            self.data_fetcher = DataFetcher(self.config)
            
            # Technical Indicators
            self.indicators = TechnicalIndicators(self.config)
            
            # Pattern Analyzer
            self.pattern_analyzer = PatternAnalyzer(self.config)
            
            # Decision Engine
            self.decision_engine = DecisionEngine(self.config)
            
            # Risk Manager
            self.risk_manager = RiskManager(self.config)
            self.risk_manager.initialize_capital(self.pairs)
            
            # Learning Module
            self.learning_module = LearningModule(self.config)
            
            # Execution Layer
            self.execution_layer = ExecutionLayer(self.config)
            
            self.logger.info("[OK] Moduły podstawowe zainicjalizowane")
            
            # ============================================
            # MODUŁY ZAAWANSOWANE (opcjonalne)
            # ============================================
            
            # Discord Notifier
            self.discord_notifier = None
            if DISCORD_AVAILABLE:
                self.discord_notifier = DiscordNotifier(self.config)
                if self.discord_notifier.enabled:
                    self.logger.info("[OK] Discord Notifier włączony")
            
            # Web Dashboard
            self.dashboard = None
            if DASHBOARD_AVAILABLE:
                self.dashboard = Dashboard(self.config, bot=self)
                if self.dashboard.enabled:
                    self.dashboard.start()
                    self.logger.info(f"[OK] Dashboard uruchomiony na porcie {self.dashboard.port}")
            
            # Technical Levels (Fibonacci, S/R)
            self.technical_levels = None
            if TECHNICAL_LEVELS_AVAILABLE:
                self.technical_levels = TechnicalLevels(self.config)
                self.logger.info("[OK] Technical Levels (Fib/S/R) włączone")
            
            # Market Regime Detector
            self.market_regime_detector = None
            if MARKET_REGIME_AVAILABLE:
                self.market_regime_detector = MarketRegimeDetector(self.config)
                self.logger.info("[OK] Market Regime Detector włączony")
            
            # Order Book Analyzer
            self.orderbook_analyzer = None
            if ORDERBOOK_AVAILABLE:
                self.orderbook_analyzer = OrderBookAnalyzer(self.config, self.data_fetcher)
                if self.orderbook_analyzer.enabled:
                    self.logger.info("[OK] Order Book Analyzer włączony")
            
            # Portfolio Manager
            self.portfolio_manager = None
            if PORTFOLIO_AVAILABLE:
                self.portfolio_manager = PortfolioManager(self.config)
                if self.portfolio_manager.enabled:
                    self.logger.info("[OK] Portfolio Manager włączony")
            
            # ML Optimizer (nie inicjalizujemy tutaj - używamy przez CLI)
            
            self.logger.info("[OK] Wszystkie moduły zainicjalizowane")
            
        except Exception as e:
            self.logger.critical(f"[ERROR] Błąd inicjalizacji modułów: {e}")
            raise
    
    def _signal_handler(self, signum, frame):
        """Obsługuje sygnały systemowe (CTRL+C)"""
        self.logger.warning(f"[WARNING] Otrzymano sygnał {signum} - zamykanie...")
        self.shutdown_requested = True
    
    def run(self):
        """Główna pętla bota"""
        self.running = True
        self.logger.info("[START] Bot uruchomiony - rozpoczynam trading loop")
        
        # Log testnet/mainnet info
        is_testnet = self.config.get('binance', {}).get('testnet', True)
        if is_testnet:
            self.logger.info("[INFO] Running on TESTNET (USDT pairs)")
        else:
            self.logger.info("[INFO] Running on MAINNET (USDC pairs)")
        
        # Interwał między iteracjami (w sekundach)
        # Dla 15m timeframe - sprawdzaj co 1 minutę
        check_interval = 60
        
        iteration = 0
        
        while self.running and not self.shutdown_requested:
            iteration += 1
            
            try:
                self.logger.info(f"\n{'='*50}")
                self.logger.info(f"[INFO] Iteracja #{iteration} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                self.logger.info(f"{'='*50}")
                
                # Sprawdź emergency stop
                if self.risk_manager.emergency_stop_active:
                    self.logger.critical("[ALERT] EMERGENCY STOP AKTYWNY - bot wstrzymany")
                    time.sleep(check_interval * 5)
                    continue
                
                # Sprawdź połączenie
                if not self.data_fetcher.check_connection():
                    self.logger.warning("[WARNING] Utrata połączenia - próba reconnect...")
                    if not self.data_fetcher.reconnect():
                        time.sleep(30)
                        continue
                
                # Procesuj każdą parę
                for pair in self.pairs:
                    try:
                        self._process_pair(pair)
                    except Exception as e:
                        self.logger.error(f"[ERROR] Błąd przetwarzania {pair}: {e}")
                
                # Pokaż status co 10 iteracji
                if iteration % 10 == 0:
                    self._show_status()
                
                # Czekaj
                self.logger.info(f"[WAIT] Następna iteracja za {check_interval}s...")
                
                # Podziel sleep na mniejsze interwały dla szybszego shutdown
                for _ in range(check_interval):
                    if self.shutdown_requested:
                        break
                    time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"[ERROR] Błąd w głównej pętli: {e}")
                time.sleep(10)
        
        self._shutdown()
    
    def _process_pair(self, pair: str):
        """Przetwarza pojedynczą parę walutową"""
        self.logger.info(f"\n[SCAN] Analizuję {pair}...")
        
        # 1. Pobierz dane
        df_primary = self.data_fetcher.get_klines(pair, self.primary_timeframe, limit=200)
        df_trend = self.data_fetcher.get_klines(pair, self.trend_timeframe, limit=100)
        
        if df_primary.empty:
            self.logger.warning(f"[WARNING] Brak danych dla {pair}")
            return
        
        # 2. Oblicz wskaźniki
        df_primary = self.indicators.calculate_all(df_primary)
        df_trend = self.indicators.calculate_all(df_trend)
        
        current_price = df_primary.iloc[-1]['close']
        self.logger.info(f"   [$] Cena: {current_price:.2f}")
        
        # 3. Sprawdź anomalie cenowe
        if self.risk_manager.check_price_anomaly(pair, current_price):
            self.logger.critical(f"[ALERT] Wykryto anomalię cenową dla {pair}!")
            if self.discord_notifier:
                self.discord_notifier.notify_emergency_stop(
                    f"Price anomaly detected for {pair}",
                    daily_pnl=self.risk_manager.daily_stats.pnl
                )
            return
        
        # 4. Analiza Market Regime (jeśli włączony)
        regime_analysis = None
        position_size_modifier = 1.0
        if self.market_regime_detector:
            regime_analysis = self.market_regime_detector.analyze_regime(df_primary, pair)
            position_size_modifier = self.market_regime_detector.get_position_size_modifier(regime_analysis.regime)
            self.logger.info(f"   [INFO] Regime: {regime_analysis.regime.value} ({regime_analysis.confidence:.0f}%)")
            
            # Cache for dashboard
            self._save_regime_cache(pair, regime_analysis)
        
        # 5. Analiza Technical Levels (jeśli włączony)
        level_bonus = 0
        if self.technical_levels:
            levels_analysis = self.technical_levels.analyze(df_primary, pair)
            if levels_analysis.get('near_level'):
                self.logger.info(f"   [LEVEL] Near level: {levels_analysis['near_level']} (+{levels_analysis['level_bonus']})")
            
            # Cache for dashboard
            self._save_levels_cache(pair, levels_analysis)
        
        # 6. Sprawdź czy jest otwarta pozycja
        if self.execution_layer.has_position(pair):
            self._manage_position(pair, df_primary, current_price)
            return
        
        # 7. Sprawdź czy możemy handlować
        can_trade, reason = self.risk_manager.can_trade(pair)
        if not can_trade:
            self.logger.info(f"   [PAUSE] {reason}")
            return
        
        # 8. Analiza Order Book (jeśli włączony)
        orderbook_bonus = 0
        if self.orderbook_analyzer and self.orderbook_analyzer.enabled:
            ob_analysis = self.orderbook_analyzer.analyze(pair, current_price)
            if ob_analysis:
                orderbook_bonus = ob_analysis.trade_score_bonus
                self.logger.info(f"   [DOCS] Order book: {ob_analysis.signal.value} (bonus: {orderbook_bonus:+.0f})")
        
        # 9. Analizuj patterny
        patterns = self.pattern_analyzer.analyze(df_primary, pair)
        
        # Filtruj przez learning module
        active_patterns = [
            p for p in patterns
            if self.learning_module.is_pattern_active(p.pattern_type.value)
        ]
        
        # Filtruj przez market regime (jeśli włączony)
        if self.market_regime_detector and regime_analysis:
            filtered_patterns = []
            for p in active_patterns:
                should_trade, regime_reason = self.market_regime_detector.should_trade(
                    regime_analysis.regime,
                    p.pattern_type.value
                )
                if should_trade:
                    filtered_patterns.append(p)
                else:
                    self.logger.debug(f"   Pattern {p.pattern_type.value} filtered by regime: {regime_reason}")
            active_patterns = filtered_patterns
        
        if not active_patterns:
            self.logger.info(f"   [DOWN] Brak aktywnych patternów")
            return
        
        # 10. Podejmij decyzję
        recommendation = self.decision_engine.evaluate(
            symbol=pair,
            patterns=active_patterns,
            df_primary=df_primary,
            df_trend=df_trend
        )
        
        # WAŻNE: Sprawdź czy recommendation nie jest None (nie powinno się zdarzyć, ale na wszelki wypadek)
        if recommendation is None:
            self.logger.info(f"   [INFO] Brak rekomendacji dla {pair}")
            return
        
        # Dodaj bonusy z modułów zaawansowanych (tylko gdy jest kierunek)
        if recommendation.direction and self.technical_levels:
            level_bonus = self.technical_levels.get_score_bonus(
                df_primary, pair, recommendation.direction, current_price
            )
            recommendation.score += level_bonus
        
        if recommendation.direction and orderbook_bonus != 0:
            # Adjust bonus based on direction
            if recommendation.direction == 'SHORT':
                orderbook_bonus = -orderbook_bonus
            recommendation.score += orderbook_bonus
        
        self.logger.info(f"   [TARGET] Decyzja: {recommendation.decision.value} (score: {recommendation.score:.0f})")
        for r in recommendation.reasoning[:5]:
            self.logger.info(f"      - {r}")
        
        # 11. Wykonaj trade jeśli TRADE
        if recommendation.decision == Decision.TRADE:
            self._execute_trade(pair, recommendation, current_price, position_size_modifier)
    
    def _manage_position(self, pair: str, df: pd.DataFrame, current_price: float):
        """Zarządza otwartą pozycją"""
        position = self.execution_layer.get_position(pair)
        if not position:
            return
        
        self.logger.info(f"   [INFO] Pozycja {position.side}: entry={position.entry_price:.2f}")
        
        # Aktualizuj cenę
        self.execution_layer.update_position_price(pair, current_price)
        self.logger.info(f"   [MONEY] Unrealized PnL: {position.unrealized_pnl:+.2f} USDC")
        
        # Aktualizuj trailing stop
        new_trailing = self.risk_manager.update_trailing_stop(pair, current_price)
        if new_trailing:
            self.logger.info(f"   [UP] Trailing stop: {new_trailing:.2f}")
        
        # Sprawdź stop orders
        stop_hit = self.execution_layer.check_stop_orders(pair, current_price)
        if stop_hit:
            self._close_position(pair, stop_hit, current_price)
            return
        
        # Sprawdź risk manager stop
        stop_hit_rm, reason = self.risk_manager.check_stop_hit(pair, current_price)
        if stop_hit_rm:
            self._close_position(pair, reason, current_price)
            return
        
        # Sprawdź early take profit
        # TODO: Pełna implementacja wymagałaby przechowywania oryginalnej rekomendacji
        # Na razie pomijamy (should_take_profit_early obsługuje None bezpiecznie)
    
    def _execute_trade(self, pair: str, recommendation, current_price: float, position_size_modifier: float = 1.0):
        """Wykonuje trade"""
        self.logger.info(f"\n[TARGET] WYKONUJĘ TRADE: {pair} {recommendation.direction}")
        
        # 1. Waliduj parametry
        is_valid, reason = self.risk_manager.validate_trade(
            symbol=pair,
            entry_price=current_price,
            stop_loss=recommendation.stop_loss,
            take_profit=recommendation.take_profit,
            direction=recommendation.direction
        )
        
        if not is_valid:
            self.logger.warning(f"   [ERROR] Trade odrzucony: {reason}")
            return
        
        # 2. Oblicz wielkość pozycji
        position_size = self.risk_manager.calculate_position_size(
            symbol=pair,
            entry_price=current_price,
            stop_loss=recommendation.stop_loss,
            direction=recommendation.direction
        )
        
        if not position_size:
            self.logger.warning(f"   [ERROR] Nie można obliczyć wielkości pozycji")
            return
        
        # Zastosuj modyfikator wielkości pozycji (z market regime)
        if position_size_modifier != 1.0:
            original_qty = position_size.quantity
            position_size.quantity = position_size.quantity * position_size_modifier
            position_size.value_usdc = position_size.value_usdc * position_size_modifier
            position_size.risk_amount = position_size.risk_amount * position_size_modifier
            self.logger.info(f"   [RULER] Position modifier: {position_size_modifier:.1f}x ({original_qty:.6f} -> {position_size.quantity:.6f})")
        
        self.logger.info(f"   [INFO] Position size: {position_size.quantity} ({position_size.value_usdc:.2f} USDC)")
        self.logger.info(f"   [WARNING] Risk: {position_size.risk_amount:.2f} USDC ({position_size.risk_pct:.1f}%)")
        
        # 3. Otwórz pozycję
        success, position, orders = self.execution_layer.open_position(
            symbol=pair,
            direction=recommendation.direction,
            quantity=position_size.quantity,
            entry_price=current_price,
            stop_loss=recommendation.stop_loss,
            take_profit=recommendation.take_profit
        )
        
        if success:
            # Zarejestruj w risk manager
            self.risk_manager.register_trade_open(
                symbol=pair,
                position=position_size,
                take_profit=recommendation.take_profit
            )
            
            self.logger.info(f"   [OK] POZYCJA OTWARTA!")
            self.logger.info(f"      Entry: {position.entry_price:.2f}")
            self.logger.info(f"      SL: {recommendation.stop_loss:.2f}")
            self.logger.info(f"      TP: {recommendation.take_profit:.2f}")
            
            # Discord notification
            if self.discord_notifier and self.discord_notifier.enabled:
                pattern_name = recommendation.pattern.pattern_type.value if hasattr(recommendation, 'pattern') and recommendation.pattern else 'Unknown'
                self.discord_notifier.notify_trade_entry(
                    symbol=pair,
                    direction=recommendation.direction,
                    entry_price=position.entry_price,
                    stop_loss=recommendation.stop_loss,
                    take_profit=recommendation.take_profit,
                    quantity=position_size.quantity,
                    value=position_size.value_usdc,
                    risk=position_size.risk_amount,
                    pattern=pattern_name,
                    score=recommendation.score
                )
        else:
            self.logger.error(f"   [ERROR] Nie udało się otworzyć pozycji")
    
    def _close_position(self, pair: str, reason: str, exit_price: float):
        """Zamyka pozycję"""
        self.logger.info(f"\n[LOCK] ZAMYKAM POZYCJĘ: {pair} ({reason})")
        
        position = self.execution_layer.get_position(pair)
        if not position:
            return
        
        entry_price = position.entry_price
        
        # Zamknij przez execution layer
        success, pnl, close_order = self.execution_layer.close_position(pair, reason)
        
        if success:
            # Zarejestruj w risk manager
            self.risk_manager.register_trade_close(pair, exit_price, reason)
            
            # Oblicz PnL %
            if position.side == 'BUY':
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - exit_price) / entry_price) * 100
            
            # Oblicz duration
            try:
                entry_time = datetime.fromisoformat(position.opened_at)
                duration = datetime.now() - entry_time
                duration_str = str(duration).split('.')[0]  # Remove microseconds
            except:
                duration_str = "unknown"
            
            # Zapisz w learning module
            pattern_type = 'unknown'  # W pełnej wersji przechowuj pattern z entry
            self.learning_module.record_trade(
                symbol=pair,
                direction=position.side,
                pattern_type=pattern_type,
                entry_price=entry_price,
                exit_price=exit_price,
                stop_loss=0,  # TODO: przechowuj z entry
                take_profit=0,
                quantity=position.quantity,
                entry_time=datetime.fromisoformat(position.opened_at) if position.opened_at else datetime.now(),
                exit_time=datetime.now(),
                exit_reason=reason,
                confidence=0
            )
            
            self.logger.info(f"   [OK] Pozycja zamknięta | PnL: {pnl:+.2f} USDC ({pnl_pct:+.2f}%)")
            
            # Discord notification
            if self.discord_notifier and self.discord_notifier.enabled:
                self.discord_notifier.notify_trade_exit(
                    symbol=pair,
                    direction=position.side,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    reason=reason,
                    duration=duration_str
                )
    
    def _show_status(self):
        """Pokazuje status bota"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("[INFO] STATUS BOTA")
        self.logger.info("=" * 60)
        
        # Portfolio
        portfolio = self.risk_manager.get_portfolio_summary()
        self.logger.info(f"[$] Kapitał: {portfolio['total_capital']:.2f} USDC")
        self.logger.info(f"[UP] PnL: {portfolio['pnl_total']:+.2f} USDC ({portfolio['pnl_pct']:+.2f}%)")
        self.logger.info(f"[INFO] Otwarte pozycje: {portfolio['open_positions']}")
        
        # Daily stats
        daily = portfolio['daily_stats']
        self.logger.info(f"[DATE] Dziś: {daily['trades_count']} trades, PnL: {daily['pnl']:+.2f}")
        
        # Performance
        perf = self.learning_module.get_performance_summary()
        if 'all_time' in perf:
            at = perf['all_time']
            self.logger.info(f"[UP] Win rate: {at.get('win_rate', 0):.1f}%")
        
        self.logger.info("=" * 60 + "\n")
    
    def _shutdown(self):
        """Graceful shutdown"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("[STOP] ZAMYKANIE BOTA")
        self.logger.info("=" * 60)
        
        self.running = False
        
        # Pokaż końcowy status
        self._show_status()
        
        # Zapisz raport
        report = self.learning_module.generate_report()
        self.logger.info(report)
        
        # Wyślij daily summary jeśli Discord włączony
        if self.discord_notifier and self.discord_notifier.enabled:
            daily_stats = self.risk_manager.daily_stats
            portfolio = self.risk_manager.get_portfolio_summary()
            self.discord_notifier.notify_daily_summary({
                'date': datetime.now().strftime('%Y-%m-%d'),
                'trades_count': daily_stats.trades_count,
                'wins': daily_stats.wins,
                'losses': daily_stats.losses,
                'daily_pnl': daily_stats.pnl,
                'daily_pnl_pct': (daily_stats.pnl / portfolio.get('initial_capital', 40000)) * 100 if portfolio.get('initial_capital') else 0,
                'total_capital': portfolio.get('total_capital', 0),
                'best_trade': daily_stats.largest_win,
                'worst_trade': daily_stats.largest_loss
            })
            self.discord_notifier.shutdown()
        
        # Zatrzymaj dashboard
        if self.dashboard and self.dashboard.running:
            self.dashboard.stop()
        
        self.logger.info("[WAVE] Bot zamknięty poprawnie")
    
    def _save_regime_cache(self, symbol: str, analysis):
        """Zapisuje analizę regime do cache dla dashboardu"""
        try:
            import json
            cache_file = f'./data/regime_{symbol}.json'
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(analysis.to_dict(), f)
        except Exception as e:
            self.logger.debug(f"Could not cache regime data: {e}")
    
    def _save_levels_cache(self, symbol: str, analysis: dict):
        """Zapisuje analizę levels do cache dla dashboardu"""
        try:
            import json
            cache_file = f'./data/levels_{symbol}.json'
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(analysis, f, default=str)
        except Exception as e:
            self.logger.debug(f"Could not cache levels data: {e}")
    
    def run_backtest(self, symbol: str = 'BTCUSDC', days: int = 30):
        """Uruchamia backtest"""
        self.logger.info(f"\n[RESEARCH] BACKTEST MODE: {symbol}, {days} dni")
        
        # Pobierz dane historyczne
        df = self.data_fetcher.get_historical_klines(symbol, self.primary_timeframe, days)
        
        if df.empty:
            self.logger.error("[ERROR] Nie udało się pobrać danych historycznych")
            return
        
        # Uruchom backtest
        backtester = Backtester(self.config)
        result = backtester.run(df, symbol, self.primary_timeframe)
        
        # Pokaż raport
        report = backtester.generate_report(result)
        print(report)
        
        # Zapisz
        backtester.save_report(result)
        backtester.plot_equity_curve(result)


# ============================================
# MAIN
# ============================================

def main():
    """Główna funkcja"""
    parser = argparse.ArgumentParser(
        description='Crypto Trading Bot v2.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady użycia:
  python main.py                    # Uruchom bota (paper trading)
  python main.py --backtest         # Uruchom backtest
  python main.py --backtest --days 60 --symbol ETHUSDC
  python main.py --status           # Pokaż status
  python main.py --optimize         # ML optimization (grid search)
  python main.py --optimize --method walk_forward
  python main.py --dashboard        # Uruchom tylko dashboard
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Ścieżka do pliku konfiguracji'
    )
    
    parser.add_argument(
        '--backtest', '-b',
        action='store_true',
        help='Uruchom w trybie backtestingu'
    )
    
    parser.add_argument(
        '--days', '-d',
        type=int,
        default=30,
        help='Liczba dni dla backtestingu/optymalizacji (domyślnie: 30)'
    )
    
    parser.add_argument(
        '--symbol', '-s',
        default='BTCUSDC',
        help='Symbol dla backtestingu/optymalizacji (domyślnie: BTCUSDC)'
    )
    
    parser.add_argument(
        '--status',
        action='store_true',
        help='Pokaż status i zakończ'
    )
    
    parser.add_argument(
        '--optimize', '-o',
        action='store_true',
        help='Uruchom ML optimization'
    )
    
    parser.add_argument(
        '--method', '-m',
        choices=['grid', 'walk_forward', 'ml'],
        default='grid',
        help='Metoda optymalizacji: grid, walk_forward, ml (domyślnie: grid)'
    )
    
    parser.add_argument(
        '--dashboard',
        action='store_true',
        help='Uruchom tylko dashboard (bez tradingu)'
    )
    
    args = parser.parse_args()
    
    try:
        # ML Optimization mode
        if args.optimize:
            if not ML_AVAILABLE:
                print("[ERROR] ML Optimizer niedostępny - zainstaluj scikit-learn")
                sys.exit(1)
            
            ml_optimize(
                symbol=args.symbol,
                days=args.days,
                method=args.method,
                config_path=args.config
            )
            return
        
        # Dashboard only mode
        if args.dashboard:
            if not DASHBOARD_AVAILABLE:
                print("[ERROR] Dashboard niedostępny - zainstaluj flask")
                sys.exit(1)
            
            import yaml
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f)
            
            config['dashboard']['enabled'] = True
            dashboard = Dashboard(config)
            dashboard.start()
            
            print(f"[WEB] Dashboard uruchomiony na http://localhost:{dashboard.port}")
            print("Naciśnij Ctrl+C aby zatrzymać")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                dashboard.stop()
            return
        
        # Utwórz bota
        bot = TradingBot(args.config)
        
        if args.status:
            bot._show_status()
            print(bot.learning_module.generate_report())
        elif args.backtest:
            bot.run_backtest(args.symbol, args.days)
        else:
            bot.run()
            
    except KeyboardInterrupt:
        print("\n\n[WAVE] Przerwano przez użytkownika")
    except Exception as e:
        print(f"\n[ERROR] Błąd krytyczny: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Import pandas tutaj dla backward compatibility
    import pandas as pd
    main()
