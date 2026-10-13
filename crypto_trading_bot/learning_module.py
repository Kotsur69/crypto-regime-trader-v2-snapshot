"""
learning_module.py - Moduł uczenia się i adaptacji

Odpowiedzialny za:
- Zapisywanie wszystkich trade'ów
- Tracking skuteczności patternów
- Automatyczne wyłączanie nieskutecznych strategii
- Analiza performance per symbol/timeframe
- Generowanie raportów
"""

import logging
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
from collections import defaultdict

from pattern_analyzer import PatternType

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Rekord pojedynczego trade'a"""
    trade_id: str
    symbol: str
    direction: str
    pattern_type: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    pnl: float
    pnl_pct: float
    entry_time: str
    exit_time: str
    exit_reason: str  # 'STOP_LOSS', 'TAKE_PROFIT', 'TRAILING_STOP', 'MANUAL'
    holding_time_minutes: int
    confidence_at_entry: float
    indicators_at_entry: Dict = field(default_factory=dict)
    
    def was_winner(self) -> bool:
        return self.pnl > 0


@dataclass
class PatternStats:
    """Statystyki patternu"""
    pattern_type: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    average_pnl: float = 0.0
    win_rate: float = 0.0
    average_winner: float = 0.0
    average_loser: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_consecutive_losses: int = 0
    current_consecutive_losses: int = 0
    is_active: bool = True
    last_updated: str = ""
    
    def update(self, trade: TradeRecord):
        """Aktualizuje statystyki po trade'zie"""
        self.total_trades += 1
        self.total_pnl += trade.pnl
        
        if trade.was_winner():
            self.wins += 1
            self.current_consecutive_losses = 0
        else:
            self.losses += 1
            self.current_consecutive_losses += 1
            self.max_consecutive_losses = max(
                self.max_consecutive_losses,
                self.current_consecutive_losses
            )
        
        # Oblicz metryki
        self.win_rate = (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0
        self.average_pnl = self.total_pnl / self.total_trades if self.total_trades > 0 else 0
        
        # Średnie winners/losers
        # (uproszczone - w pełnej wersji potrzeba historii wszystkich trade'ów)
        if self.wins > 0:
            self.average_winner = self.total_pnl / self.wins if self.total_pnl > 0 else 0
        if self.losses > 0:
            self.average_loser = abs(self.total_pnl) / self.losses if self.total_pnl < 0 else 0
        
        # Profit factor
        gross_profit = self.wins * self.average_winner if self.average_winner > 0 else 0
        gross_loss = self.losses * self.average_loser if self.average_loser > 0 else 1
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Expectancy
        self.expectancy = (
            (self.win_rate / 100 * self.average_winner) -
            ((1 - self.win_rate / 100) * self.average_loser)
        )
        
        self.last_updated = datetime.now().isoformat()


@dataclass
class SymbolStats:
    """Statystyki per symbol"""
    symbol: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    best_pattern: str = ""
    worst_pattern: str = ""
    average_holding_time: float = 0.0
    
    def to_dict(self) -> Dict:
        return asdict(self)


class LearningModule:
    """Moduł uczenia się i adaptacji strategii"""
    
    def __init__(self, config: dict):
        """
        Inicjalizacja modułu
        
        Args:
            config: Konfiguracja
        """
        self.config = config.get('learning', {})
        self.patterns_config = config.get('patterns', {})
        
        # Parametry
        self.adaptive_patterns = self.config.get('adaptive_patterns', True)
        self.evaluation_period_days = self.config.get('evaluation_period_days', 7)
        self.data_path = self.config.get('data_path', './data/learning/')
        self.log_all_trades = self.config.get('log_all_trades', True)
        
        # Minimalna skuteczność do aktywności patternu
        self.min_pattern_win_rate = self.patterns_config.get('min_pattern_win_rate', 40)
        self.min_samples_for_evaluation = self.patterns_config.get('min_samples_for_evaluation', 10)
        
        # Stan
        self.trade_history: List[TradeRecord] = []
        self.pattern_stats: Dict[str, PatternStats] = {}
        self.symbol_stats: Dict[str, SymbolStats] = {}
        self.disabled_patterns: List[str] = []
        
        # Inicjalizuj statystyki dla wszystkich patternów
        for pattern_type in PatternType:
            if pattern_type != PatternType.NO_PATTERN:
                self.pattern_stats[pattern_type.value] = PatternStats(
                    pattern_type=pattern_type.value
                )
        
        # Ścieżki plików
        os.makedirs(self.data_path, exist_ok=True)
        self.trades_file = os.path.join(self.data_path, 'trade_history.json')
        self.stats_file = os.path.join(self.data_path, 'pattern_stats.json')
        
        self._load_data()
        logger.info("[OK] LearningModule zainicjalizowany")
    
    def record_trade(
        self,
        symbol: str,
        direction: str,
        pattern_type: str,
        entry_price: float,
        exit_price: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
        entry_time: datetime,
        exit_time: datetime,
        exit_reason: str,
        confidence: float,
        indicators: Optional[Dict] = None
    ) -> TradeRecord:
        """
        Rejestruje zakończony trade
        
        Returns:
            TradeRecord
        """
        # Oblicz PnL
        if direction == 'LONG':
            pnl = (exit_price - entry_price) * quantity
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        else:
            pnl = (entry_price - exit_price) * quantity
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100
        
        # Czas trzymania
        holding_time = (exit_time - entry_time).total_seconds() / 60
        
        # Utwórz rekord
        trade = TradeRecord(
            trade_id=f"{symbol}_{entry_time.strftime('%Y%m%d%H%M%S')}",
            symbol=symbol,
            direction=direction,
            pattern_type=pattern_type,
            entry_price=entry_price,
            exit_price=exit_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            quantity=quantity,
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            entry_time=entry_time.isoformat(),
            exit_time=exit_time.isoformat(),
            exit_reason=exit_reason,
            holding_time_minutes=int(holding_time),
            confidence_at_entry=confidence,
            indicators_at_entry=indicators or {}
        )
        
        # Zapisz
        self.trade_history.append(trade)
        
        # Aktualizuj statystyki
        self._update_pattern_stats(trade)
        self._update_symbol_stats(trade)
        
        # Sprawdź czy wyłączyć pattern
        if self.adaptive_patterns:
            self._evaluate_pattern_effectiveness(pattern_type)
        
        # Zapisz do pliku
        if self.log_all_trades:
            self._save_data()
        
        logger.info(
            f"[LOG] Trade zapisany: {symbol} {direction} | "
            f"PnL: {pnl:+.2f} USDC ({pnl_pct:+.2f}%) | "
            f"Pattern: {pattern_type}"
        )
        
        return trade
    
    def _update_pattern_stats(self, trade: TradeRecord):
        """Aktualizuje statystyki patternu"""
        pattern_type = trade.pattern_type
        
        if pattern_type not in self.pattern_stats:
            self.pattern_stats[pattern_type] = PatternStats(pattern_type=pattern_type)
        
        self.pattern_stats[pattern_type].update(trade)
    
    def _update_symbol_stats(self, trade: TradeRecord):
        """Aktualizuje statystyki symbolu"""
        symbol = trade.symbol
        
        if symbol not in self.symbol_stats:
            self.symbol_stats[symbol] = SymbolStats(symbol=symbol)
        
        stats = self.symbol_stats[symbol]
        stats.total_trades += 1
        stats.total_pnl += trade.pnl
        
        if trade.was_winner():
            stats.wins += 1
        else:
            stats.losses += 1
        
        stats.win_rate = (stats.wins / stats.total_trades * 100) if stats.total_trades > 0 else 0
        
        # Średni czas trzymania
        all_holding_times = [
            t.holding_time_minutes for t in self.trade_history
            if t.symbol == symbol
        ]
        if all_holding_times:
            stats.average_holding_time = sum(all_holding_times) / len(all_holding_times)
    
    def _evaluate_pattern_effectiveness(self, pattern_type: str):
        """Ocenia i ewentualnie wyłącza pattern"""
        if pattern_type not in self.pattern_stats:
            return
        
        stats = self.pattern_stats[pattern_type]
        
        # Potrzeba minimum samples
        if stats.total_trades < self.min_samples_for_evaluation:
            return
        
        # Sprawdź win rate
        if stats.win_rate < self.min_pattern_win_rate:
            if stats.is_active:
                stats.is_active = False
                self.disabled_patterns.append(pattern_type)
                logger.warning(
                    f"[WARNING] Pattern {pattern_type} WYŁĄCZONY | "
                    f"Win rate: {stats.win_rate:.1f}% < {self.min_pattern_win_rate}%"
                )
        else:
            # Reaktywuj jeśli się poprawił
            if not stats.is_active and stats.win_rate >= self.min_pattern_win_rate + 5:
                stats.is_active = True
                if pattern_type in self.disabled_patterns:
                    self.disabled_patterns.remove(pattern_type)
                logger.info(
                    f"[OK] Pattern {pattern_type} REAKTYWOWANY | "
                    f"Win rate: {stats.win_rate:.1f}%"
                )
    
    def is_pattern_active(self, pattern_type: str) -> bool:
        """Sprawdza czy pattern jest aktywny"""
        if pattern_type in self.pattern_stats:
            return self.pattern_stats[pattern_type].is_active
        return True
    
    def get_pattern_stats(self, pattern_type: str) -> Optional[PatternStats]:
        """Zwraca statystyki patternu"""
        return self.pattern_stats.get(pattern_type)
    
    def get_all_pattern_stats(self) -> Dict[str, Dict]:
        """Zwraca statystyki wszystkich patternów"""
        return {
            name: asdict(stats)
            for name, stats in self.pattern_stats.items()
        }
    
    def get_symbol_stats(self, symbol: str) -> Optional[SymbolStats]:
        """Zwraca statystyki symbolu"""
        return self.symbol_stats.get(symbol)
    
    def get_recent_trades(self, limit: int = 20) -> List[Dict]:
        """Zwraca ostatnie trade'y"""
        trades = self.trade_history[-limit:]
        return [asdict(t) for t in reversed(trades)]
    
    def get_performance_summary(self) -> Dict:
        """Zwraca podsumowanie performance"""
        if not self.trade_history:
            return {'message': 'Brak historii trade\'ów'}
        
        total_trades = len(self.trade_history)
        wins = sum(1 for t in self.trade_history if t.was_winner())
        total_pnl = sum(t.pnl for t in self.trade_history)
        
        # Filtruj po okresie
        cutoff = datetime.now() - timedelta(days=self.evaluation_period_days)
        recent_trades = [
            t for t in self.trade_history
            if datetime.fromisoformat(t.entry_time) > cutoff
        ]
        
        recent_wins = sum(1 for t in recent_trades if t.was_winner())
        recent_pnl = sum(t.pnl for t in recent_trades)
        
        # Najlepsze/najgorsze patterny
        pattern_pnl = defaultdict(float)
        for t in self.trade_history:
            pattern_pnl[t.pattern_type] += t.pnl
        
        best_pattern = max(pattern_pnl.items(), key=lambda x: x[1]) if pattern_pnl else ('N/A', 0)
        worst_pattern = min(pattern_pnl.items(), key=lambda x: x[1]) if pattern_pnl else ('N/A', 0)
        
        return {
            'all_time': {
                'total_trades': total_trades,
                'wins': wins,
                'losses': total_trades - wins,
                'win_rate': round(wins / total_trades * 100, 1) if total_trades > 0 else 0,
                'total_pnl': round(total_pnl, 2),
                'average_pnl': round(total_pnl / total_trades, 2) if total_trades > 0 else 0
            },
            'recent': {
                'period_days': self.evaluation_period_days,
                'total_trades': len(recent_trades),
                'wins': recent_wins,
                'win_rate': round(recent_wins / len(recent_trades) * 100, 1) if recent_trades else 0,
                'total_pnl': round(recent_pnl, 2)
            },
            'best_pattern': {
                'name': best_pattern[0],
                'total_pnl': round(best_pattern[1], 2)
            },
            'worst_pattern': {
                'name': worst_pattern[0],
                'total_pnl': round(worst_pattern[1], 2)
            },
            'disabled_patterns': self.disabled_patterns,
            'active_patterns': [
                name for name, stats in self.pattern_stats.items()
                if stats.is_active
            ]
        }
    
    def generate_report(self) -> str:
        """Generuje raport tekstowy"""
        summary = self.get_performance_summary()
        
        report = []
        report.append("=" * 60)
        report.append("[INFO] TRADING BOT - PERFORMANCE REPORT")
        report.append("=" * 60)
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # All-time stats
        report.append("\n[UP] ALL-TIME STATISTICS:")
        report.append("-" * 40)
        at = summary.get('all_time', {})
        report.append(f"  Total trades: {at.get('total_trades', 0)}")
        report.append(f"  Win rate: {at.get('win_rate', 0)}%")
        report.append(f"  Wins/Losses: {at.get('wins', 0)}/{at.get('losses', 0)}")
        report.append(f"  Total PnL: {at.get('total_pnl', 0):+.2f} USDC")
        report.append(f"  Average PnL: {at.get('average_pnl', 0):+.2f} USDC")
        
        # Recent stats
        report.append(f"\n[DATE] RECENT ({summary.get('recent', {}).get('period_days', 7)} DAYS):")
        report.append("-" * 40)
        rc = summary.get('recent', {})
        report.append(f"  Trades: {rc.get('total_trades', 0)}")
        report.append(f"  Win rate: {rc.get('win_rate', 0)}%")
        report.append(f"  PnL: {rc.get('total_pnl', 0):+.2f} USDC")
        
        # Pattern stats
        report.append("\n[TARGET] PATTERN PERFORMANCE:")
        report.append("-" * 40)
        for name, stats in sorted(
            self.pattern_stats.items(),
            key=lambda x: x[1].total_pnl,
            reverse=True
        ):
            if stats.total_trades > 0:
                status = "[GREEN]" if stats.is_active else "[RED]"
                report.append(
                    f"  {status} {name}:\n"
                    f"      Trades: {stats.total_trades} | "
                    f"Win rate: {stats.win_rate:.1f}% | "
                    f"PnL: {stats.total_pnl:+.2f}"
                )
        
        # Symbol stats
        report.append("\n[$] SYMBOL PERFORMANCE:")
        report.append("-" * 40)
        for symbol, stats in self.symbol_stats.items():
            report.append(
                f"  {symbol}: "
                f"Trades: {stats.total_trades} | "
                f"Win rate: {stats.win_rate:.1f}% | "
                f"PnL: {stats.total_pnl:+.2f}"
            )
        
        # Disabled patterns
        if self.disabled_patterns:
            report.append("\n[WARNING] DISABLED PATTERNS:")
            report.append("-" * 40)
            for pattern in self.disabled_patterns:
                stats = self.pattern_stats.get(pattern)
                if stats:
                    report.append(f"  - {pattern} (win rate: {stats.win_rate:.1f}%)")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)
    
    def export_trades_to_csv(self, filepath: Optional[str] = None) -> str:
        """Eksportuje trade'y do CSV"""
        if not self.trade_history:
            return ""
        
        filepath = filepath or os.path.join(self.data_path, 'trades_export.csv')
        
        df = pd.DataFrame([asdict(t) for t in self.trade_history])
        df.to_csv(filepath, index=False)
        
        logger.info(f"[FILE] Eksportowano {len(df)} trade'ów do {filepath}")
        return filepath
    
    def _save_data(self):
        """Zapisuje dane do plików"""
        try:
            # Trade history
            with open(self.trades_file, 'w') as f:
                json.dump(
                    [asdict(t) for t in self.trade_history],
                    f,
                    indent=2
                )
            
            # Pattern stats
            with open(self.stats_file, 'w') as f:
                json.dump(
                    {name: asdict(stats) for name, stats in self.pattern_stats.items()},
                    f,
                    indent=2
                )
            
        except Exception as e:
            logger.error(f"Błąd zapisu danych: {e}")
    
    def _load_data(self):
        """Ładuje dane z plików"""
        try:
            # Trade history
            if os.path.exists(self.trades_file):
                with open(self.trades_file, 'r') as f:
                    data = json.load(f)
                    self.trade_history = [
                        TradeRecord(**t) for t in data
                    ]
                logger.info(f"[FOLDER] Załadowano {len(self.trade_history)} trade'ów")
            
            # Pattern stats
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                    for name, stats_dict in data.items():
                        self.pattern_stats[name] = PatternStats(**stats_dict)
                    
                    # Aktualizuj disabled patterns
                    self.disabled_patterns = [
                        name for name, stats in self.pattern_stats.items()
                        if not stats.is_active
                    ]
                    
        except Exception as e:
            logger.warning(f"Błąd ładowania danych: {e}")


if __name__ == "__main__":
    # Test modułu
    import yaml
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Test Learning Module
    lm = LearningModule(config)
    
    # Symuluj kilka trade'ów
    from datetime import datetime, timedelta
    
    trades_data = [
        ('BTCUSDC', 'LONG', 'ema_pullback_bullish', 50000, 51500, 49000, 53000, True),
        ('BTCUSDC', 'LONG', 'ema_pullback_bullish', 51000, 50000, 50000, 53000, False),
        ('ETHUSDC', 'SHORT', 'momentum_shift_bearish', 3000, 2850, 3100, 2800, True),
        ('BTCUSDC', 'LONG', 'trend_continuation', 52000, 54000, 51000, 55000, True),
    ]
    
    for i, (symbol, direction, pattern, entry, exit_p, sl, tp, is_win) in enumerate(trades_data):
        entry_time = datetime.now() - timedelta(hours=10-i)
        exit_time = entry_time + timedelta(hours=2)
        
        lm.record_trade(
            symbol=symbol,
            direction=direction,
            pattern_type=pattern,
            entry_price=entry,
            exit_price=exit_p,
            stop_loss=sl,
            take_profit=tp,
            quantity=0.1,
            entry_time=entry_time,
            exit_time=exit_time,
            exit_reason='TAKE_PROFIT' if is_win else 'STOP_LOSS',
            confidence=75.0
        )
    
    # Pokaż raport
    print(lm.generate_report())
    
    # Pokaż summary
    print("\n[INFO] Performance Summary:")
    summary = lm.get_performance_summary()
    print(json.dumps(summary, indent=2))
