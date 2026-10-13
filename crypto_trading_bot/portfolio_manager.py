#!/usr/bin/env python3
"""
portfolio_manager.py - Dynamic Portfolio Rebalancing

Funkcjonalności:
- Dynamiczna alokacja kapitału między pary
- Alokacja na podstawie recent performance, volatility, correlation
- Rebalancing co 24h lub przy drawdown
- Min/max limity alokacji per para
"""

import logging
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RebalanceReason(Enum):
    """Powód rebalancingu"""
    SCHEDULED = "scheduled"         # Co 24h
    DRAWDOWN = "drawdown"           # Przy dużym drawdown
    PERFORMANCE = "performance"     # Przy znaczącej różnicy w performance
    VOLATILITY = "volatility"       # Przy zmianie volatility
    MANUAL = "manual"               # Manualnie wywołany


@dataclass
class PairMetrics:
    """Metryki dla pary walutowej"""
    symbol: str
    current_allocation: float       # Aktualny % kapitału
    target_allocation: float        # Docelowy % kapitału
    recent_pnl: float              # PnL z ostatnich N dni
    win_rate: float                # Win rate z ostatnich N dni
    volatility: float              # Volatility (ATR/price)
    sharpe_ratio: float            # Sharpe ratio
    correlation_score: float       # Score korelacji z innymi parami (niższy = lepszy)
    performance_score: float       # Composite score
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'current_allocation': round(self.current_allocation, 2),
            'target_allocation': round(self.target_allocation, 2),
            'recent_pnl': round(self.recent_pnl, 2),
            'win_rate': round(self.win_rate, 2),
            'volatility': round(self.volatility, 4),
            'sharpe_ratio': round(self.sharpe_ratio, 3),
            'correlation_score': round(self.correlation_score, 3),
            'performance_score': round(self.performance_score, 2)
        }


@dataclass
class RebalanceAction:
    """Akcja rebalancingu"""
    symbol: str
    action: str                     # 'increase', 'decrease', 'maintain'
    current_capital: float
    new_capital: float
    change_amount: float
    change_pct: float
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'action': self.action,
            'current_capital': round(self.current_capital, 2),
            'new_capital': round(self.new_capital, 2),
            'change_amount': round(self.change_amount, 2),
            'change_pct': round(self.change_pct, 2)
        }


class PortfolioManager:
    """
    Zarządza alokacją kapitału między parami
    """
    
    def __init__(self, config: dict):
        """
        Inicjalizacja Portfolio Managera
        
        Args:
            config: Konfiguracja z sekcją 'portfolio'
        """
        self.config = config.get('portfolio', {})
        self.enabled = self.config.get('enabled', False)
        
        # Limity alokacji
        self.min_allocation_pct = self.config.get('min_allocation_pct', 15)  # Min 15%
        self.max_allocation_pct = self.config.get('max_allocation_pct', 35)  # Max 35%
        self.equal_weight = self.config.get('equal_weight', 25)  # Bazowo równe 25%
        
        # Rebalancing triggers
        self.rebalance_interval_hours = self.config.get('rebalance_interval_hours', 24)
        self.drawdown_trigger_pct = self.config.get('drawdown_trigger_pct', 5)  # Rebalance przy 5% DD
        self.allocation_drift_trigger_pct = self.config.get('allocation_drift_trigger_pct', 5)
        
        # Performance lookback
        self.performance_lookback_days = self.config.get('performance_lookback_days', 7)
        
        # Wagi dla composite score
        self.weights = {
            'recent_performance': self.config.get('weight_performance', 0.35),
            'win_rate': self.config.get('weight_win_rate', 0.25),
            'volatility': self.config.get('weight_volatility', 0.20),
            'correlation': self.config.get('weight_correlation', 0.10),
            'sharpe': self.config.get('weight_sharpe', 0.10)
        }
        
        # State
        self.last_rebalance = None
        self.pair_metrics: Dict[str, PairMetrics] = {}
        self.target_allocations: Dict[str, float] = {}
        self.rebalance_history: List[Dict] = []
        
        # Paths
        self.state_file = './data/portfolio_state.json'
        
        self._load_state()
        
        if self.enabled:
            logger.info("[OK] PortfolioManager zainicjalizowany")
        else:
            logger.info("[INFO] PortfolioManager wyłączony")
    
    def calculate_pair_metrics(
        self,
        symbol: str,
        trade_history: List[Dict],
        price_data: pd.DataFrame,
        current_capital: float,
        total_capital: float
    ) -> PairMetrics:
        """
        Oblicza metryki dla pary
        
        Args:
            symbol: Symbol pary
            trade_history: Historia trade'ów dla tej pary
            price_data: OHLCV dane
            current_capital: Aktualny kapitał dla pary
            total_capital: Całkowity kapitał
        
        Returns:
            PairMetrics
        """
        # Current allocation
        current_allocation = (current_capital / total_capital * 100) if total_capital > 0 else 0
        
        # Recent trades (last N days)
        cutoff_date = datetime.now() - timedelta(days=self.performance_lookback_days)
        recent_trades = [
            t for t in trade_history
            if datetime.fromisoformat(t.get('exit_time', datetime.now().isoformat())) >= cutoff_date
        ]
        
        # Recent PnL
        recent_pnl = sum(t.get('pnl', 0) for t in recent_trades)
        
        # Win rate
        if recent_trades:
            wins = sum(1 for t in recent_trades if t.get('pnl', 0) > 0)
            win_rate = (wins / len(recent_trades)) * 100
        else:
            win_rate = 50  # Neutral if no trades
        
        # Volatility (ATR / price)
        volatility = self._calculate_volatility(price_data)
        
        # Sharpe ratio
        sharpe = self._calculate_sharpe(recent_trades)
        
        # Correlation score (placeholder - needs multiple pairs)
        correlation_score = 0.5  # Will be calculated in analyze_portfolio
        
        # Performance score (will be recalculated)
        performance_score = 0
        
        return PairMetrics(
            symbol=symbol,
            current_allocation=current_allocation,
            target_allocation=current_allocation,  # Will be updated
            recent_pnl=recent_pnl,
            win_rate=win_rate,
            volatility=volatility,
            sharpe_ratio=sharpe,
            correlation_score=correlation_score,
            performance_score=performance_score
        )
    
    def _calculate_volatility(self, df: pd.DataFrame) -> float:
        """Oblicza volatility jako ATR/price"""
        if df.empty or len(df) < 14:
            return 0
        
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            atr = tr.rolling(14).mean().iloc[-1]
            current_price = close.iloc[-1]
            
            return (atr / current_price) if current_price > 0 else 0
        except:
            return 0
    
    def _calculate_sharpe(self, trades: List[Dict], risk_free_rate: float = 0) -> float:
        """Oblicza Sharpe ratio z trade'ów"""
        if not trades or len(trades) < 3:
            return 0
        
        try:
            returns = [t.get('pnl_pct', 0) for t in trades]
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            
            if std_return == 0:
                return 0
            
            sharpe = (mean_return - risk_free_rate) / std_return
            return sharpe
        except:
            return 0
    
    def analyze_portfolio(
        self,
        pairs: List[str],
        capital_per_pair: Dict[str, float],
        trade_histories: Dict[str, List[Dict]],
        price_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, PairMetrics]:
        """
        Analizuje całe portfolio
        
        Args:
            pairs: Lista par
            capital_per_pair: Kapitał dla każdej pary
            trade_histories: Historia trade'ów per para
            price_data: OHLCV dane per para
        
        Returns:
            Dict z metrykami per para
        """
        total_capital = sum(capital_per_pair.values())
        
        # Calculate metrics for each pair
        for symbol in pairs:
            trades = trade_histories.get(symbol, [])
            df = price_data.get(symbol, pd.DataFrame())
            capital = capital_per_pair.get(symbol, 10000)
            
            metrics = self.calculate_pair_metrics(
                symbol=symbol,
                trade_history=trades,
                price_data=df,
                current_capital=capital,
                total_capital=total_capital
            )
            self.pair_metrics[symbol] = metrics
        
        # Calculate correlations
        self._calculate_correlations(price_data)
        
        # Calculate performance scores
        self._calculate_performance_scores()
        
        return self.pair_metrics
    
    def _calculate_correlations(self, price_data: Dict[str, pd.DataFrame]):
        """Oblicza korelacje między parami"""
        if len(price_data) < 2:
            return
        
        try:
            # Create returns matrix
            returns_dict = {}
            for symbol, df in price_data.items():
                if not df.empty:
                    returns_dict[symbol] = df['close'].pct_change()
            
            if len(returns_dict) < 2:
                return
            
            returns_df = pd.DataFrame(returns_dict).dropna()
            
            if len(returns_df) < 20:
                return
            
            # Correlation matrix
            corr_matrix = returns_df.corr()
            
            # Update correlation scores
            for symbol in self.pair_metrics:
                if symbol in corr_matrix.columns:
                    # Average correlation with other pairs
                    other_corrs = corr_matrix[symbol].drop(symbol)
                    avg_corr = abs(other_corrs).mean()
                    self.pair_metrics[symbol].correlation_score = avg_corr
        except Exception as e:
            logger.warning(f"Error calculating correlations: {e}")
    
    def _calculate_performance_scores(self):
        """Oblicza composite performance scores"""
        if not self.pair_metrics:
            return
        
        # Normalize metrics
        pnls = [m.recent_pnl for m in self.pair_metrics.values()]
        win_rates = [m.win_rate for m in self.pair_metrics.values()]
        volatilities = [m.volatility for m in self.pair_metrics.values()]
        sharpes = [m.sharpe_ratio for m in self.pair_metrics.values()]
        correlations = [m.correlation_score for m in self.pair_metrics.values()]
        
        for symbol, metrics in self.pair_metrics.items():
            # Normalize each metric to 0-100 scale
            # Higher is better for performance, win_rate, sharpe
            # Lower is better for volatility, correlation
            
            # PnL score
            pnl_range = max(pnls) - min(pnls) if max(pnls) != min(pnls) else 1
            pnl_score = ((metrics.recent_pnl - min(pnls)) / pnl_range) * 100 if pnl_range else 50
            
            # Win rate is already in %
            wr_score = metrics.win_rate
            
            # Volatility (inverse - lower is better)
            vol_range = max(volatilities) - min(volatilities) if max(volatilities) != min(volatilities) else 1
            vol_score = 100 - ((metrics.volatility - min(volatilities)) / vol_range * 100) if vol_range else 50
            
            # Sharpe
            sharpe_range = max(sharpes) - min(sharpes) if max(sharpes) != min(sharpes) else 1
            sharpe_score = ((metrics.sharpe_ratio - min(sharpes)) / sharpe_range) * 100 if sharpe_range else 50
            
            # Correlation (inverse - lower is better)
            corr_range = max(correlations) - min(correlations) if max(correlations) != min(correlations) else 1
            corr_score = 100 - ((metrics.correlation_score - min(correlations)) / corr_range * 100) if corr_range else 50
            
            # Composite score
            composite = (
                self.weights['recent_performance'] * pnl_score +
                self.weights['win_rate'] * wr_score +
                self.weights['volatility'] * vol_score +
                self.weights['sharpe'] * sharpe_score +
                self.weights['correlation'] * corr_score
            )
            
            metrics.performance_score = composite
    
    def calculate_target_allocations(self) -> Dict[str, float]:
        """
        Oblicza docelowe alokacje na podstawie performance scores
        
        Returns:
            Dict z target allocation % per para
        """
        if not self.pair_metrics:
            return {}
        
        # Get performance scores
        scores = {symbol: m.performance_score for symbol, m in self.pair_metrics.items()}
        total_score = sum(scores.values())
        
        if total_score == 0:
            # Equal weight if no scores
            equal_pct = 100 / len(scores)
            return {symbol: equal_pct for symbol in scores}
        
        # Calculate raw allocations based on score
        raw_allocations = {}
        for symbol, score in scores.items():
            raw_pct = (score / total_score) * 100
            raw_allocations[symbol] = raw_pct
        
        # Apply min/max constraints
        constrained = {}
        excess = 0
        
        for symbol, pct in raw_allocations.items():
            if pct < self.min_allocation_pct:
                constrained[symbol] = self.min_allocation_pct
                excess -= (self.min_allocation_pct - pct)
            elif pct > self.max_allocation_pct:
                constrained[symbol] = self.max_allocation_pct
                excess += (pct - self.max_allocation_pct)
            else:
                constrained[symbol] = pct
        
        # Redistribute excess proportionally to unconstrained pairs
        unconstrained = [
            s for s, p in constrained.items()
            if self.min_allocation_pct < p < self.max_allocation_pct
        ]
        
        if unconstrained and excess != 0:
            adjustment = excess / len(unconstrained)
            for symbol in unconstrained:
                new_pct = constrained[symbol] + adjustment
                new_pct = max(self.min_allocation_pct, min(self.max_allocation_pct, new_pct))
                constrained[symbol] = new_pct
        
        # Update metrics with target allocations
        for symbol, pct in constrained.items():
            if symbol in self.pair_metrics:
                self.pair_metrics[symbol].target_allocation = pct
        
        self.target_allocations = constrained
        return constrained
    
    def should_rebalance(
        self,
        current_allocations: Dict[str, float],
        daily_drawdown_pct: float = 0
    ) -> Tuple[bool, RebalanceReason]:
        """
        Sprawdza czy powinien nastąpić rebalancing
        
        Args:
            current_allocations: Aktualne alokacje % per para
            daily_drawdown_pct: Aktualny dzienny drawdown
        
        Returns:
            (should_rebalance, reason)
        """
        if not self.enabled:
            return False, RebalanceReason.SCHEDULED
        
        # Check scheduled rebalance
        if self.last_rebalance is None:
            return True, RebalanceReason.SCHEDULED
        
        hours_since_rebalance = (datetime.now() - self.last_rebalance).total_seconds() / 3600
        if hours_since_rebalance >= self.rebalance_interval_hours:
            return True, RebalanceReason.SCHEDULED
        
        # Check drawdown trigger
        if daily_drawdown_pct >= self.drawdown_trigger_pct:
            return True, RebalanceReason.DRAWDOWN
        
        # Check allocation drift
        if self.target_allocations and current_allocations:
            for symbol in current_allocations:
                current = current_allocations.get(symbol, 0)
                target = self.target_allocations.get(symbol, current)
                drift = abs(current - target)
                
                if drift >= self.allocation_drift_trigger_pct:
                    return True, RebalanceReason.PERFORMANCE
        
        return False, RebalanceReason.SCHEDULED
    
    def rebalance(
        self,
        capital_per_pair: Dict[str, float],
        reason: RebalanceReason = RebalanceReason.MANUAL
    ) -> List[RebalanceAction]:
        """
        Wykonuje rebalancing portfolio
        
        Args:
            capital_per_pair: Aktualny kapitał per para
            reason: Powód rebalancingu
        
        Returns:
            Lista akcji rebalancingu
        """
        if not self.target_allocations:
            logger.warning("No target allocations calculated")
            return []
        
        total_capital = sum(capital_per_pair.values())
        actions = []
        
        logger.info(f"[SYNC] Rebalancing portfolio (reason: {reason.value})")
        
        for symbol in capital_per_pair:
            current = capital_per_pair[symbol]
            current_pct = (current / total_capital) * 100
            target_pct = self.target_allocations.get(symbol, current_pct)
            target_capital = total_capital * (target_pct / 100)
            
            change = target_capital - current
            change_pct = target_pct - current_pct
            
            if abs(change_pct) < 1:  # Ignore small changes (<1%)
                action_type = 'maintain'
            elif change > 0:
                action_type = 'increase'
            else:
                action_type = 'decrease'
            
            action = RebalanceAction(
                symbol=symbol,
                action=action_type,
                current_capital=current,
                new_capital=target_capital,
                change_amount=change,
                change_pct=change_pct
            )
            actions.append(action)
            
            if action_type != 'maintain':
                logger.info(f"   {symbol}: {current:.0f} -> {target_capital:.0f} ({change_pct:+.1f}%)")
        
        # Record rebalance
        self.last_rebalance = datetime.now()
        self.rebalance_history.append({
            'timestamp': self.last_rebalance.isoformat(),
            'reason': reason.value,
            'actions': [a.to_dict() for a in actions]
        })
        
        self._save_state()
        
        return actions
    
    def apply_rebalance(
        self,
        capital_per_pair: Dict[str, float],
        actions: List[RebalanceAction]
    ) -> Dict[str, float]:
        """
        Aplikuje akcje rebalancingu do kapitału
        
        Args:
            capital_per_pair: Aktualny kapitał
            actions: Akcje do wykonania
        
        Returns:
            Nowy kapitał per para
        """
        new_capital = dict(capital_per_pair)
        
        for action in actions:
            if action.symbol in new_capital:
                new_capital[action.symbol] = action.new_capital
        
        return new_capital
    
    def get_portfolio_summary(self) -> Dict:
        """Zwraca podsumowanie portfolio"""
        return {
            'enabled': self.enabled,
            'pair_metrics': {s: m.to_dict() for s, m in self.pair_metrics.items()},
            'target_allocations': self.target_allocations,
            'last_rebalance': self.last_rebalance.isoformat() if self.last_rebalance else None,
            'rebalance_count': len(self.rebalance_history)
        }
    
    def _save_state(self):
        """Zapisuje stan portfolio"""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            state = {
                'last_rebalance': self.last_rebalance.isoformat() if self.last_rebalance else None,
                'target_allocations': self.target_allocations,
                'rebalance_history': self.rebalance_history[-50:],  # Last 50
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving portfolio state: {e}")
    
    def _load_state(self):
        """Ładuje stan portfolio"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                if state.get('last_rebalance'):
                    self.last_rebalance = datetime.fromisoformat(state['last_rebalance'])
                
                self.target_allocations = state.get('target_allocations', {})
                self.rebalance_history = state.get('rebalance_history', [])
                
                logger.info(f"[FOLDER] Portfolio state loaded")
                
        except Exception as e:
            logger.warning(f"Could not load portfolio state: {e}")


if __name__ == "__main__":
    # Test modułu
    import yaml
    
    logging.basicConfig(level=logging.INFO)
    
    # Przykładowa konfiguracja
    config = {
        'portfolio': {
            'enabled': True,
            'min_allocation_pct': 15,
            'max_allocation_pct': 35,
            'rebalance_interval_hours': 24
        }
    }
    
    pm = PortfolioManager(config)
    
    # Test z przykładowymi danymi
    pairs = ['BTCUSDC', 'ETHUSDC', 'XRPUSDC', 'DOGEUSDC']
    capital = {
        'BTCUSDC': 10500,
        'ETHUSDC': 9800,
        'XRPUSDC': 10200,
        'DOGEUSDC': 9500
    }
    
    # Przykładowe trade histories
    trade_histories = {
        'BTCUSDC': [{'pnl': 100, 'pnl_pct': 1, 'exit_time': datetime.now().isoformat()}],
        'ETHUSDC': [{'pnl': -50, 'pnl_pct': -0.5, 'exit_time': datetime.now().isoformat()}],
        'XRPUSDC': [{'pnl': 80, 'pnl_pct': 0.8, 'exit_time': datetime.now().isoformat()}],
        'DOGEUSDC': [{'pnl': -100, 'pnl_pct': -1, 'exit_time': datetime.now().isoformat()}]
    }
    
    # Przykładowe dane cenowe (uproszczone)
    price_data = {}
    for pair in pairs:
        dates = pd.date_range(end=datetime.now(), periods=100, freq='15min')
        price_data[pair] = pd.DataFrame({
            'open': np.random.uniform(100, 110, 100),
            'high': np.random.uniform(110, 115, 100),
            'low': np.random.uniform(95, 100, 100),
            'close': np.random.uniform(100, 110, 100),
            'volume': np.random.uniform(1000, 5000, 100)
        }, index=dates)
    
    # Analiza portfolio
    metrics = pm.analyze_portfolio(pairs, capital, trade_histories, price_data)
    
    print("\n[INFO] Portfolio Metrics:")
    for symbol, m in metrics.items():
        print(f"   {symbol}: score={m.performance_score:.1f}, pnl={m.recent_pnl:.2f}, wr={m.win_rate:.1f}%")
    
    # Calculate target allocations
    targets = pm.calculate_target_allocations()
    
    print("\n[TARGET] Target Allocations:")
    for symbol, pct in targets.items():
        print(f"   {symbol}: {pct:.1f}%")
    
    # Check if should rebalance
    current_alloc = {s: c/sum(capital.values())*100 for s, c in capital.items()}
    should, reason = pm.should_rebalance(current_alloc, daily_drawdown_pct=0)
    
    print(f"\n[SYNC] Should rebalance: {should} ({reason.value})")
    
    if should:
        actions = pm.rebalance(capital, reason)
        print("\n[LOG] Rebalance Actions:")
        for action in actions:
            print(f"   {action.symbol}: {action.action} ({action.change_pct:+.1f}%)")
