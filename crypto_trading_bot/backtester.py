"""
backtester.py - Moduł backtestingu

Odpowiedzialny za:
- Testowanie strategii na danych historycznych
- Generowanie metryk i statystyk
- Tworzenie raportów i wykresów
- Optymalizacja parametrów
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import json

from indicators import TechnicalIndicators
from pattern_analyzer import PatternAnalyzer, PatternSignal
from decision_engine import DecisionEngine, Decision, TradeRecommendation
from risk_manager import RiskManager, PositionSize

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """Trade w backteście"""
    entry_time: datetime
    exit_time: datetime
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
    exit_reason: str
    confidence: float
    bars_held: int


@dataclass 
class BacktestResult:
    """Wyniki backtestu"""
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    
    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # PnL metrics
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    
    # Performance metrics
    win_rate: float = 0.0
    profit_factor: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    expectancy: float = 0.0
    
    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    
    # Time metrics
    average_bars_held: float = 0.0
    max_bars_held: int = 0
    min_bars_held: int = 0
    
    # Pattern breakdown
    pattern_stats: Dict = field(default_factory=dict)
    
    # Trade list
    trades: List[BacktestTrade] = field(default_factory=list)
    
    # Equity curve
    equity_curve: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'initial_capital': self.initial_capital,
            'final_capital': self.final_capital,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_pnl': round(self.total_pnl, 2),
            'total_pnl_pct': round(self.total_pnl_pct, 2),
            'win_rate': round(self.win_rate, 2),
            'profit_factor': round(self.profit_factor, 2),
            'average_win': round(self.average_win, 2),
            'average_loss': round(self.average_loss, 2),
            'largest_win': round(self.largest_win, 2),
            'largest_loss': round(self.largest_loss, 2),
            'expectancy': round(self.expectancy, 2),
            'max_drawdown': round(self.max_drawdown, 2),
            'max_drawdown_pct': round(self.max_drawdown_pct, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 2),
            'average_bars_held': round(self.average_bars_held, 1),
            'pattern_stats': self.pattern_stats
        }


class Backtester:
    """Moduł backtestingu strategii"""
    
    def __init__(self, config: dict):
        """
        Inicjalizacja backtestera
        
        Args:
            config: Konfiguracja
        """
        self.config = config
        self.backtest_config = config.get('backtesting', {})
        
        # Komponenty
        self.indicators = TechnicalIndicators(config)
        self.pattern_analyzer = PatternAnalyzer(config)
        self.decision_engine = DecisionEngine(config)
        
        # Parametry
        self.default_period_days = self.backtest_config.get('default_period_days', 30)
        self.reports_path = self.backtest_config.get('reports_path', './reports/')
        self.generate_charts = self.backtest_config.get('generate_charts', True)
        
        # Paper trading params (dla symulacji)
        self.fee_pct = config.get('paper_trading', {}).get('simulated_fee_pct', 0.1)
        self.slippage_pct = config.get('paper_trading', {}).get('simulated_slippage_pct', 0.05)
        
        # Risk params
        self.initial_capital = config.get('trading', {}).get('initial_capital_per_pair', 10000)
        self.risk_per_trade_pct = config.get('risk', {}).get('max_risk_per_trade_pct', 2)
        self.min_rr = config.get('risk', {}).get('min_risk_reward', 1.5)
        
        os.makedirs(self.reports_path, exist_ok=True)
        logger.info("[OK] Backtester zainicjalizowany")
    
    def run(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str = '15m'
    ) -> BacktestResult:
        """
        Uruchamia backtest na danych
        
        Args:
            df: DataFrame z danymi OHLCV
            symbol: Symbol pary
            timeframe: Timeframe
        
        Returns:
            BacktestResult
        """
        logger.info(f"[SYNC] Starting backtest for {symbol} ({timeframe})")
        logger.info(f"   Period: {df.index[0]} to {df.index[-1]}")
        logger.info(f"   Bars: {len(df)}")
        
        # Oblicz wskaźniki dla całego zbioru
        df = self.indicators.calculate_all(df)
        
        # Stan backtestu
        capital = self.initial_capital
        equity_curve = [capital]
        trades: List[BacktestTrade] = []
        
        # Aktualna pozycja
        position = None
        entry_bar_idx = 0
        
        # Minimum danych dla wskaźników
        warmup_period = 150
        
        # Iteruj przez dane
        for i in range(warmup_period, len(df)):
            # Dane do tego momentu
            current_df = df.iloc[:i+1].copy()
            current_bar = df.iloc[i]
            current_price = current_bar['close']
            current_time = df.index[i]
            
            # ========== Sprawdź czy zamknąć pozycję ==========
            if position is not None:
                exit_reason = None
                exit_price = None
                
                # Stop Loss
                if position['direction'] == 'LONG':
                    if current_bar['low'] <= position['stop_loss']:
                        exit_reason = 'STOP_LOSS'
                        exit_price = position['stop_loss']
                    elif current_bar['high'] >= position['take_profit']:
                        exit_reason = 'TAKE_PROFIT'
                        exit_price = position['take_profit']
                else:  # SHORT
                    if current_bar['high'] >= position['stop_loss']:
                        exit_reason = 'STOP_LOSS'
                        exit_price = position['stop_loss']
                    elif current_bar['low'] <= position['take_profit']:
                        exit_reason = 'TAKE_PROFIT'
                        exit_price = position['take_profit']
                
                if exit_reason:
                    # Zamknij pozycję
                    trade = self._close_position(
                        position, exit_price, exit_reason,
                        current_time, i - entry_bar_idx
                    )
                    trades.append(trade)
                    capital += trade.pnl
                    equity_curve.append(capital)
                    position = None
            
            # ========== Szukaj nowych sygnałów ==========
            if position is None:
                # Analizuj patterny
                patterns = self.pattern_analyzer.analyze(current_df, symbol)
                
                if patterns:
                    # Oceń przez decision engine
                    recommendation = self.decision_engine.evaluate(
                        symbol=symbol,
                        patterns=patterns,
                        df_primary=current_df
                    )
                    
                    if recommendation.decision == Decision.TRADE:
                        # Waliduj i otwórz pozycję
                        position = self._open_position(
                            recommendation,
                            current_price,
                            capital
                        )
                        
                        if position:
                            entry_bar_idx = i
            
            # Aktualizuj equity curve
            if position is not None:
                unrealized_pnl = self._calculate_unrealized_pnl(position, current_price)
                equity_curve.append(capital + unrealized_pnl)
        
        # Zamknij otwartą pozycję na końcu
        if position is not None:
            trade = self._close_position(
                position,
                df.iloc[-1]['close'],
                'END_OF_DATA',
                df.index[-1],
                len(df) - 1 - entry_bar_idx
            )
            trades.append(trade)
            capital += trade.pnl
        
        # Oblicz metryki
        result = self._calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            symbol=symbol,
            timeframe=timeframe,
            start_date=df.index[warmup_period],
            end_date=df.index[-1],
            initial_capital=self.initial_capital
        )
        
        logger.info(f"[OK] Backtest completed: {result.total_trades} trades, PnL: {result.total_pnl:+.2f}")
        
        return result
    
    def _open_position(
        self,
        recommendation: TradeRecommendation,
        current_price: float,
        capital: float
    ) -> Optional[Dict]:
        """Otwiera pozycję w backteście"""
        if recommendation.entry_price is None:
            return None
        
        # Użyj aktualnej ceny + slippage
        if recommendation.direction == 'LONG':
            entry_price = current_price * (1 + self.slippage_pct / 100)
        else:
            entry_price = current_price * (1 - self.slippage_pct / 100)
        
        # Oblicz wielkość pozycji
        risk_per_unit = abs(entry_price - recommendation.stop_loss)
        if risk_per_unit <= 0:
            return None
        
        max_risk = capital * (self.risk_per_trade_pct / 100)
        quantity = max_risk / risk_per_unit
        
        # Limit wielkości pozycji
        max_position = capital * 0.2  # Max 20% kapitału
        if quantity * entry_price > max_position:
            quantity = max_position / entry_price
        
        return {
            'direction': recommendation.direction,
            'entry_price': entry_price,
            'stop_loss': recommendation.stop_loss,
            'take_profit': recommendation.take_profit,
            'quantity': quantity,
            'pattern_type': recommendation.patterns_used[0].value if recommendation.patterns_used else 'unknown',
            'confidence': recommendation.confidence,
            'entry_time': datetime.now()
        }
    
    def _close_position(
        self,
        position: Dict,
        exit_price: float,
        exit_reason: str,
        exit_time: datetime,
        bars_held: int
    ) -> BacktestTrade:
        """Zamyka pozycję i zwraca trade"""
        # Dodaj slippage do exit
        if position['direction'] == 'LONG':
            exit_price = exit_price * (1 - self.slippage_pct / 100)
            pnl = (exit_price - position['entry_price']) * position['quantity']
        else:
            exit_price = exit_price * (1 + self.slippage_pct / 100)
            pnl = (position['entry_price'] - exit_price) * position['quantity']
        
        # Odejmij fees
        fees = (position['entry_price'] + exit_price) * position['quantity'] * (self.fee_pct / 100)
        pnl -= fees
        
        pnl_pct = (pnl / (position['entry_price'] * position['quantity'])) * 100
        
        return BacktestTrade(
            entry_time=position.get('entry_time', datetime.now()),
            exit_time=exit_time,
            symbol='',
            direction=position['direction'],
            pattern_type=position['pattern_type'],
            entry_price=position['entry_price'],
            exit_price=exit_price,
            stop_loss=position['stop_loss'],
            take_profit=position['take_profit'],
            quantity=position['quantity'],
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            confidence=position['confidence'],
            bars_held=bars_held
        )
    
    def _calculate_unrealized_pnl(self, position: Dict, current_price: float) -> float:
        """Oblicza niezrealizowany PnL"""
        if position['direction'] == 'LONG':
            return (current_price - position['entry_price']) * position['quantity']
        else:
            return (position['entry_price'] - current_price) * position['quantity']
    
    def _calculate_metrics(
        self,
        trades: List[BacktestTrade],
        equity_curve: List[float],
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float
    ) -> BacktestResult:
        """Oblicza wszystkie metryki"""
        result = BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=equity_curve[-1] if equity_curve else initial_capital,
            trades=trades,
            equity_curve=equity_curve
        )
        
        if not trades:
            return result
        
        # Basic stats
        result.total_trades = len(trades)
        result.winning_trades = sum(1 for t in trades if t.pnl > 0)
        result.losing_trades = sum(1 for t in trades if t.pnl <= 0)
        
        # PnL
        result.total_pnl = sum(t.pnl for t in trades)
        result.total_pnl_pct = (result.total_pnl / initial_capital) * 100
        result.gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        result.gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        
        # Win rate
        result.win_rate = (result.winning_trades / result.total_trades * 100) if result.total_trades > 0 else 0
        
        # Profit factor
        result.profit_factor = (result.gross_profit / result.gross_loss) if result.gross_loss > 0 else float('inf')
        
        # Average win/loss
        winners = [t.pnl for t in trades if t.pnl > 0]
        losers = [t.pnl for t in trades if t.pnl < 0]
        
        result.average_win = np.mean(winners) if winners else 0
        result.average_loss = abs(np.mean(losers)) if losers else 0
        result.largest_win = max(winners) if winners else 0
        result.largest_loss = abs(min(losers)) if losers else 0
        
        # Expectancy
        result.expectancy = (
            (result.win_rate / 100 * result.average_win) -
            ((1 - result.win_rate / 100) * result.average_loss)
        )
        
        # Drawdown
        if equity_curve:
            equity_series = pd.Series(equity_curve)
            rolling_max = equity_series.expanding().max()
            drawdown = equity_series - rolling_max
            result.max_drawdown = abs(drawdown.min())
            result.max_drawdown_pct = (result.max_drawdown / rolling_max[drawdown.idxmin()]) * 100 if result.max_drawdown > 0 else 0
        
        # Sharpe ratio (simplified - annualized)
        if len(trades) > 1:
            returns = [t.pnl_pct for t in trades]
            if np.std(returns) > 0:
                result.sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252)  # Assuming daily
        
        # Bars held
        bars = [t.bars_held for t in trades]
        result.average_bars_held = np.mean(bars) if bars else 0
        result.max_bars_held = max(bars) if bars else 0
        result.min_bars_held = min(bars) if bars else 0
        
        # Pattern stats
        pattern_stats = {}
        for trade in trades:
            pt = trade.pattern_type
            if pt not in pattern_stats:
                pattern_stats[pt] = {'trades': 0, 'wins': 0, 'pnl': 0}
            pattern_stats[pt]['trades'] += 1
            pattern_stats[pt]['pnl'] += trade.pnl
            if trade.pnl > 0:
                pattern_stats[pt]['wins'] += 1
        
        for pt in pattern_stats:
            pattern_stats[pt]['win_rate'] = (
                pattern_stats[pt]['wins'] / pattern_stats[pt]['trades'] * 100
            ) if pattern_stats[pt]['trades'] > 0 else 0
        
        result.pattern_stats = pattern_stats
        
        return result
    
    def generate_report(self, result: BacktestResult) -> str:
        """Generuje raport tekstowy"""
        report = []
        report.append("=" * 70)
        report.append("[INFO] BACKTEST REPORT")
        report.append("=" * 70)
        
        report.append(f"\n[UP] OVERVIEW")
        report.append("-" * 50)
        report.append(f"Symbol:          {result.symbol}")
        report.append(f"Timeframe:       {result.timeframe}")
        report.append(f"Period:          {result.start_date} to {result.end_date}")
        report.append(f"Initial Capital: {result.initial_capital:,.2f} USDC")
        report.append(f"Final Capital:   {result.final_capital:,.2f} USDC")
        
        report.append(f"\n[$] PERFORMANCE")
        report.append("-" * 50)
        report.append(f"Total PnL:       {result.total_pnl:+,.2f} USDC ({result.total_pnl_pct:+.2f}%)")
        report.append(f"Win Rate:        {result.win_rate:.1f}%")
        report.append(f"Profit Factor:   {result.profit_factor:.2f}")
        report.append(f"Expectancy:      {result.expectancy:+.2f} USDC/trade")
        
        report.append(f"\n[INFO] TRADE STATISTICS")
        report.append("-" * 50)
        report.append(f"Total Trades:    {result.total_trades}")
        report.append(f"Winners:         {result.winning_trades}")
        report.append(f"Losers:          {result.losing_trades}")
        report.append(f"Average Win:     {result.average_win:+.2f} USDC")
        report.append(f"Average Loss:    {result.average_loss:.2f} USDC")
        report.append(f"Largest Win:     {result.largest_win:+.2f} USDC")
        report.append(f"Largest Loss:    {result.largest_loss:.2f} USDC")
        
        report.append(f"\n[WARNING] RISK METRICS")
        report.append("-" * 50)
        report.append(f"Max Drawdown:    {result.max_drawdown:.2f} USDC ({result.max_drawdown_pct:.2f}%)")
        report.append(f"Sharpe Ratio:    {result.sharpe_ratio:.2f}")
        
        report.append(f"\n[TIMER] TIME METRICS")
        report.append("-" * 50)
        report.append(f"Avg Bars Held:   {result.average_bars_held:.1f}")
        report.append(f"Max Bars Held:   {result.max_bars_held}")
        report.append(f"Min Bars Held:   {result.min_bars_held}")
        
        report.append(f"\n[TARGET] PATTERN BREAKDOWN")
        report.append("-" * 50)
        for pattern, stats in sorted(
            result.pattern_stats.items(),
            key=lambda x: x[1]['pnl'],
            reverse=True
        ):
            report.append(
                f"{pattern}:\n"
                f"    Trades: {stats['trades']} | "
                f"Win Rate: {stats['win_rate']:.1f}% | "
                f"PnL: {stats['pnl']:+.2f}"
            )
        
        report.append("\n" + "=" * 70)
        
        return "\n".join(report)
    
    def save_report(self, result: BacktestResult, filename: Optional[str] = None):
        """Zapisuje raport do pliku"""
        if filename is None:
            filename = f"backtest_{result.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Tekstowy raport
        report_text = self.generate_report(result)
        with open(os.path.join(self.reports_path, f"{filename}.txt"), 'w') as f:
            f.write(report_text)
        
        # JSON z pełnymi danymi
        with open(os.path.join(self.reports_path, f"{filename}.json"), 'w') as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        
        logger.info(f"[FILE] Raport zapisany: {self.reports_path}/{filename}")
    
    def plot_equity_curve(self, result: BacktestResult, save_path: Optional[str] = None):
        """Rysuje equity curve"""
        try:
            import matplotlib.pyplot as plt
            
            fig, axes = plt.subplots(2, 1, figsize=(14, 10))
            
            # Equity curve
            ax1 = axes[0]
            ax1.plot(result.equity_curve, label='Equity', color='blue', linewidth=1.5)
            ax1.axhline(y=result.initial_capital, color='gray', linestyle='--', label='Initial')
            ax1.fill_between(
                range(len(result.equity_curve)),
                result.initial_capital,
                result.equity_curve,
                where=[e > result.initial_capital for e in result.equity_curve],
                alpha=0.3,
                color='green'
            )
            ax1.fill_between(
                range(len(result.equity_curve)),
                result.initial_capital,
                result.equity_curve,
                where=[e < result.initial_capital for e in result.equity_curve],
                alpha=0.3,
                color='red'
            )
            ax1.set_title(f'Equity Curve - {result.symbol} ({result.timeframe})')
            ax1.set_xlabel('Bar')
            ax1.set_ylabel('Capital (USDC)')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Drawdown
            ax2 = axes[1]
            equity_series = pd.Series(result.equity_curve)
            rolling_max = equity_series.expanding().max()
            drawdown = ((equity_series - rolling_max) / rolling_max) * 100
            ax2.fill_between(range(len(drawdown)), 0, drawdown, color='red', alpha=0.5)
            ax2.set_title('Drawdown %')
            ax2.set_xlabel('Bar')
            ax2.set_ylabel('Drawdown %')
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=150)
                logger.info(f"[INFO] Wykres zapisany: {save_path}")
            else:
                plt.savefig(
                    os.path.join(
                        self.reports_path,
                        f"equity_{result.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    ),
                    dpi=150
                )
            
            plt.close()
            
        except ImportError:
            logger.warning("matplotlib nie zainstalowane - pomijam wykres")


if __name__ == "__main__":
    # Test modułu
    import yaml
    from data_fetcher import DataFetcher
    
    logging.basicConfig(level=logging.INFO)
    
    # Załaduj konfigurację
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Pobierz dane historyczne
    fetcher = DataFetcher(config)
    df = fetcher.get_historical_klines('BTCUSDC', '15m', days=30)
    
    if not df.empty:
        # Uruchom backtest
        backtester = Backtester(config)
        result = backtester.run(df, 'BTCUSDC', '15m')
        
        # Pokaż raport
        print(backtester.generate_report(result))
        
        # Zapisz raport
        backtester.save_report(result)
        
        # Rysuj wykres
        backtester.plot_equity_curve(result)
    else:
        print("Nie udało się pobrać danych historycznych")
