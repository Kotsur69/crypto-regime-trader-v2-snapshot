#!/usr/bin/env python3
"""
ml_optimizer.py - Machine Learning Parameter Optimization

Funkcjonalności:
- Grid search dla parametrów (EMA periods, RSI thresholds, R:R ratio)
- Walk-forward optimization
- Random Forest/XGBoost dla feature importance
- Funkcja optimize() do uruchomienia z CLI
"""

import logging
import os
import json
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
import itertools
import numpy as np
import pandas as pd

try:
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("scikit-learn nie zainstalowany - ML optimization niedostępna")

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Wyniki optymalizacji"""
    best_params: Dict
    best_score: float
    all_results: List[Dict]
    feature_importance: Dict[str, float] = field(default_factory=dict)
    model_accuracy: float = 0
    optimization_time: float = 0
    
    def to_dict(self) -> Dict:
        return {
            'best_params': self.best_params,
            'best_score': self.best_score,
            'all_results': self.all_results[:20],  # Top 20
            'feature_importance': self.feature_importance,
            'model_accuracy': self.model_accuracy,
            'optimization_time': self.optimization_time
        }


@dataclass
class WalkForwardResult:
    """Wyniki walk-forward analysis"""
    folds: List[Dict]
    average_score: float
    std_score: float
    best_fold_params: Dict
    robustness_score: float  # Jak stabilne są wyniki
    
    def to_dict(self) -> Dict:
        return {
            'folds': self.folds,
            'average_score': self.average_score,
            'std_score': self.std_score,
            'best_fold_params': self.best_fold_params,
            'robustness_score': self.robustness_score
        }


class MLOptimizer:
    """
    Optymalizacja parametrów tradingowych z użyciem ML
    """
    
    def __init__(self, config: dict):
        """
        Inicjalizacja optymalizatora
        
        Args:
            config: Konfiguracja z sekcją 'ml_optimizer'
        """
        self.config = config.get('ml_optimizer', {})
        self.enabled = self.config.get('enabled', False) and SKLEARN_AVAILABLE
        
        # Parametry do optymalizacji
        self.param_grid = self.config.get('param_grid', {
            'ema_fast': [5, 9, 12],
            'ema_medium': [15, 21, 26],
            'ema_slow': [40, 50, 60],
            'rsi_period': [10, 14, 20],
            'rsi_oversold': [25, 30, 35],
            'rsi_overbought': [65, 70, 75],
            'min_risk_reward': [1.2, 1.5, 2.0, 2.5],
            'min_trade_score': [50, 60, 70]
        })
        
        # Walk-forward settings
        self.n_splits = self.config.get('n_splits', 5)
        self.train_pct = self.config.get('train_pct', 0.7)
        
        # ML settings
        self.use_xgboost = self.config.get('use_xgboost', True) and XGBOOST_AVAILABLE
        
        # Paths
        self.results_path = self.config.get('results_path', './data/ml/')
        os.makedirs(self.results_path, exist_ok=True)
        
        if self.enabled:
            logger.info("[OK] MLOptimizer zainicjalizowany")
        else:
            logger.info("[INFO] MLOptimizer wyłączony (brak sklearn)")
    
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Przygotowuje features dla ML
        
        Args:
            df: DataFrame z OHLCV i wskaźnikami
        
        Returns:
            DataFrame z features
        """
        features = pd.DataFrame(index=df.index)
        
        # Price features
        features['returns_1'] = df['close'].pct_change(1)
        features['returns_5'] = df['close'].pct_change(5)
        features['returns_10'] = df['close'].pct_change(10)
        
        # Volatility
        features['volatility_10'] = df['close'].rolling(10).std() / df['close'].rolling(10).mean()
        features['volatility_20'] = df['close'].rolling(20).std() / df['close'].rolling(20).mean()
        
        # Volume features
        if 'volume' in df.columns:
            features['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
            features['volume_trend'] = df['volume'].rolling(5).mean() / df['volume'].rolling(20).mean()
        
        # Technical indicators (if available)
        indicator_cols = ['rsi', 'macd', 'macd_signal', 'stoch_k', 'stoch_d']
        for col in indicator_cols:
            if col in df.columns:
                features[col] = df[col]
        
        # EMA features
        for ema_col in ['ema_9', 'ema_21', 'ema_50', 'ema_100']:
            if ema_col in df.columns:
                features[f'{ema_col}_dist'] = (df['close'] - df[ema_col]) / df[ema_col]
        
        # Trend features
        features['higher_highs'] = (df['high'] > df['high'].shift(1)).astype(int).rolling(5).sum()
        features['lower_lows'] = (df['low'] < df['low'].shift(1)).astype(int).rolling(5).sum()
        
        # Price position in range
        features['price_position'] = (df['close'] - df['low'].rolling(20).min()) / \
                                     (df['high'].rolling(20).max() - df['low'].rolling(20).min() + 1e-10)
        
        # Clean NaN
        features = features.dropna()
        
        return features
    
    def prepare_labels(self, df: pd.DataFrame, lookahead: int = 10, threshold: float = 0.01) -> pd.Series:
        """
        Przygotowuje labels (czy trade był profitable)
        
        Args:
            df: DataFrame z OHLCV
            lookahead: Ile świec do przodu patrzymy
            threshold: Minimalny % move do uznania za profitable
        
        Returns:
            Series z labels (1 = profitable long, -1 = profitable short, 0 = no trade)
        """
        future_returns = df['close'].shift(-lookahead) / df['close'] - 1
        
        labels = pd.Series(0, index=df.index)
        labels[future_returns > threshold] = 1   # Profitable long
        labels[future_returns < -threshold] = -1  # Profitable short
        
        return labels
    
    def grid_search(
        self,
        df: pd.DataFrame,
        backtester,
        param_grid: Dict = None,
        metric: str = 'total_pnl'
    ) -> OptimizationResult:
        """
        Grid search po parametrach
        
        Args:
            df: DataFrame z danymi historycznymi
            backtester: Instancja Backtester
            param_grid: Grid parametrów do przeszukania
            metric: Metryka do optymalizacji
        
        Returns:
            OptimizationResult
        """
        if param_grid is None:
            param_grid = self.param_grid
        
        start_time = datetime.now()
        results = []
        
        # Generate all combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))
        
        logger.info(f"[SCAN] Grid search: {len(combinations)} kombinacji do przetestowania")
        
        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            
            try:
                # Update config with these params
                test_config = self._create_test_config(params)
                
                # Run backtest
                result = backtester.run_with_config(df, test_config)
                
                # Extract metric
                score = self._extract_metric(result, metric)
                
                results.append({
                    'params': params,
                    'score': score,
                    'total_pnl': result.get('total_pnl', 0),
                    'win_rate': result.get('win_rate', 0),
                    'profit_factor': result.get('profit_factor', 0),
                    'max_drawdown': result.get('max_drawdown_pct', 0),
                    'total_trades': result.get('total_trades', 0)
                })
                
                if (i + 1) % 10 == 0:
                    logger.info(f"   Progress: {i+1}/{len(combinations)}")
                    
            except Exception as e:
                logger.warning(f"   Error with params {params}: {e}")
                continue
        
        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        best = results[0] if results else {'params': {}, 'score': 0}
        
        optimization_time = (datetime.now() - start_time).total_seconds()
        
        opt_result = OptimizationResult(
            best_params=best['params'],
            best_score=best['score'],
            all_results=results,
            optimization_time=optimization_time
        )
        
        # Save results
        self._save_results(opt_result, 'grid_search')
        
        logger.info(f"[OK] Grid search complete: best score = {best['score']:.4f}")
        logger.info(f"   Best params: {best['params']}")
        
        return opt_result
    
    def walk_forward_optimization(
        self,
        df: pd.DataFrame,
        backtester,
        param_grid: Dict = None,
        n_splits: int = None
    ) -> WalkForwardResult:
        """
        Walk-forward optimization
        
        Trenuje na danych historycznych, waliduje na out-of-sample
        
        Args:
            df: DataFrame z danymi
            backtester: Instancja Backtester
            param_grid: Grid parametrów
            n_splits: Liczba foldów
        
        Returns:
            WalkForwardResult
        """
        if n_splits is None:
            n_splits = self.n_splits
        
        if param_grid is None:
            param_grid = {
                'ema_fast': [9, 12],
                'ema_medium': [21, 26],
                'min_risk_reward': [1.5, 2.0],
                'min_trade_score': [55, 65]
            }
        
        logger.info(f"[SYNC] Walk-forward optimization: {n_splits} folds")
        
        folds = []
        tscv = TimeSeriesSplit(n_splits=n_splits)
        
        for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(df)):
            logger.info(f"   Fold {fold_idx + 1}/{n_splits}")
            
            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx]
            
            # Optimize on train data
            train_best_params = self._quick_optimize(train_df, backtester, param_grid)
            
            # Validate on test data
            test_config = self._create_test_config(train_best_params)
            test_result = backtester.run_with_config(test_df, test_config)
            
            fold_result = {
                'fold': fold_idx + 1,
                'train_size': len(train_df),
                'test_size': len(test_df),
                'best_params': train_best_params,
                'test_pnl': test_result.get('total_pnl', 0),
                'test_win_rate': test_result.get('win_rate', 0),
                'test_trades': test_result.get('total_trades', 0)
            }
            folds.append(fold_result)
            
            logger.info(f"      Test PnL: {fold_result['test_pnl']:.2f}, Win Rate: {fold_result['test_win_rate']:.1f}%")
        
        # Aggregate results
        scores = [f['test_pnl'] for f in folds]
        avg_score = np.mean(scores)
        std_score = np.std(scores)
        
        # Robustness: how consistent are the results
        positive_folds = sum(1 for s in scores if s > 0)
        robustness = positive_folds / len(scores) * 100
        
        # Most common best params
        param_counts = {}
        for f in folds:
            for k, v in f['best_params'].items():
                key = f"{k}={v}"
                param_counts[key] = param_counts.get(key, 0) + 1
        
        # Use params from best fold
        best_fold = max(folds, key=lambda x: x['test_pnl'])
        
        result = WalkForwardResult(
            folds=folds,
            average_score=avg_score,
            std_score=std_score,
            best_fold_params=best_fold['best_params'],
            robustness_score=robustness
        )
        
        self._save_results(result, 'walk_forward')
        
        logger.info(f"[OK] Walk-forward complete: avg PnL = {avg_score:.2f} (+/- {std_score:.2f})")
        logger.info(f"   Robustness: {robustness:.1f}% positive folds")
        
        return result
    
    def train_prediction_model(
        self,
        df: pd.DataFrame,
        lookahead: int = 10
    ) -> Tuple[Any, float, Dict[str, float]]:
        """
        Trenuje model ML do predykcji kierunku rynku
        
        Args:
            df: DataFrame z OHLCV i wskaźnikami
            lookahead: Ile świec do przodu predykujemy
        
        Returns:
            (model, accuracy, feature_importance)
        """
        if not SKLEARN_AVAILABLE:
            logger.warning("sklearn nie dostępny")
            return None, 0, {}
        
        logger.info("[BOT] Training prediction model...")
        
        # Prepare data
        features = self.prepare_features(df)
        labels = self.prepare_labels(df, lookahead=lookahead)
        
        # Align indices
        common_idx = features.index.intersection(labels.index)
        features = features.loc[common_idx]
        labels = labels.loc[common_idx]
        
        # Remove unknown labels
        mask = labels != 0
        features = features[mask]
        labels = labels[mask]
        
        # Convert to binary (profitable vs not)
        labels = (labels > 0).astype(int)
        
        if len(features) < 100:
            logger.warning("Za mało danych do treningu")
            return None, 0, {}
        
        # Time series split
        train_size = int(len(features) * 0.8)
        X_train = features.iloc[:train_size]
        X_test = features.iloc[train_size:]
        y_train = labels.iloc[:train_size]
        y_test = labels.iloc[train_size:]
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Train model
        if self.use_xgboost and XGBOOST_AVAILABLE:
            model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                use_label_encoder=False,
                eval_metric='logloss',
                random_state=42
            )
        else:
            model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
        
        model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        
        logger.info(f"   Accuracy: {accuracy:.3f}")
        logger.info(f"   Precision: {precision:.3f}")
        logger.info(f"   Recall: {recall:.3f}")
        logger.info(f"   F1: {f1:.3f}")
        
        # Feature importance
        importance = dict(zip(features.columns, model.feature_importances_))
        importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
        
        logger.info("   Top features:")
        for feat, imp in list(importance.items())[:5]:
            logger.info(f"      {feat}: {imp:.4f}")
        
        # Save model
        model_path = os.path.join(self.results_path, 'prediction_model.pkl')
        with open(model_path, 'wb') as f:
            pickle.dump({'model': model, 'scaler': scaler, 'features': list(features.columns)}, f)
        
        return model, accuracy, importance
    
    def _quick_optimize(
        self,
        df: pd.DataFrame,
        backtester,
        param_grid: Dict
    ) -> Dict:
        """
        Quick optimization dla pojedynczego foldu
        """
        best_params = {}
        best_score = float('-inf')
        
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))
        
        for combo in combinations:
            params = dict(zip(param_names, combo))
            
            try:
                test_config = self._create_test_config(params)
                result = backtester.run_with_config(df, test_config)
                score = result.get('total_pnl', 0)
                
                if score > best_score:
                    best_score = score
                    best_params = params
            except:
                continue
        
        return best_params
    
    def _create_test_config(self, params: Dict) -> Dict:
        """Tworzy konfigurację testową z podanych parametrów"""
        config = {
            'indicators': {},
            'risk': {},
            'decision': {}
        }
        
        # Map params to config sections
        indicator_params = ['ema_fast', 'ema_medium', 'ema_slow', 'rsi_period', 
                           'rsi_oversold', 'rsi_overbought', 'macd_fast', 'macd_slow']
        risk_params = ['min_risk_reward', 'max_risk_per_trade_pct', 'max_daily_drawdown_pct']
        decision_params = ['min_trade_score']
        
        for key, value in params.items():
            if key in indicator_params:
                config['indicators'][key] = value
            elif key in risk_params:
                config['risk'][key] = value
            elif key in decision_params:
                config['decision'][key] = value
        
        return config
    
    def _extract_metric(self, result: Dict, metric: str) -> float:
        """Wydobywa metrykę z wyniku backtestu"""
        if metric == 'total_pnl':
            return result.get('total_pnl', 0)
        elif metric == 'sharpe':
            return result.get('sharpe_ratio', 0)
        elif metric == 'profit_factor':
            return result.get('profit_factor', 0)
        elif metric == 'win_rate':
            return result.get('win_rate', 0)
        elif metric == 'combined':
            # Composite score
            pnl = result.get('total_pnl', 0)
            wr = result.get('win_rate', 0) / 100
            pf = result.get('profit_factor', 0)
            dd = result.get('max_drawdown_pct', 100)
            
            return pnl * wr * min(pf, 3) / max(dd, 1)
        else:
            return result.get(metric, 0)
    
    def _save_results(self, result, name: str):
        """Zapisuje wyniki optymalizacji"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(self.results_path, f'{name}_{timestamp}.json')
        
        with open(filename, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
        
        logger.info(f"   Results saved to {filename}")


def optimize(
    symbol: str = 'BTCUSDC',
    days: int = 60,
    method: str = 'grid',
    config_path: str = 'config.yaml'
):
    """
    CLI function do uruchomienia optymalizacji
    
    Args:
        symbol: Symbol do optymalizacji
        days: Dni danych historycznych
        method: 'grid', 'walk_forward', lub 'ml'
        config_path: Ścieżka do konfiguracji
    """
    import yaml
    from data_fetcher import DataFetcher
    from backtester import Backtester
    
    print(f"\n[CONFIG] Starting {method} optimization for {symbol}...")
    print(f"   Data: {days} days\n")
    
    # Load config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize
    fetcher = DataFetcher(config)
    backtester = Backtester(config)
    optimizer = MLOptimizer(config)
    
    # Fetch data
    print("[DOWNLOAD] Fetching historical data...")
    df = fetcher.get_historical_klines(symbol, '15m', days)
    
    if df.empty:
        print("[ERROR] Could not fetch data")
        return
    
    print(f"   Got {len(df)} candles\n")
    
    # Run optimization
    if method == 'grid':
        result = optimizer.grid_search(df, backtester)
        
        print("\n" + "="*50)
        print("[INFO] GRID SEARCH RESULTS")
        print("="*50)
        print(f"Best Score: {result.best_score:.2f}")
        print(f"Best Params:")
        for k, v in result.best_params.items():
            print(f"   {k}: {v}")
        print(f"\nTime: {result.optimization_time:.1f}s")
        
    elif method == 'walk_forward':
        result = optimizer.walk_forward_optimization(df, backtester)
        
        print("\n" + "="*50)
        print("[INFO] WALK-FORWARD RESULTS")
        print("="*50)
        print(f"Average PnL: {result.average_score:.2f} (+/- {result.std_score:.2f})")
        print(f"Robustness: {result.robustness_score:.1f}%")
        print(f"Best Params:")
        for k, v in result.best_fold_params.items():
            print(f"   {k}: {v}")
        
    elif method == 'ml':
        model, accuracy, importance = optimizer.train_prediction_model(df)
        
        print("\n" + "="*50)
        print("[INFO] ML MODEL RESULTS")
        print("="*50)
        print(f"Accuracy: {accuracy:.3f}")
        print(f"\nTop Features:")
        for feat, imp in list(importance.items())[:10]:
            print(f"   {feat}: {imp:.4f}")
    
    print("\n[OK] Optimization complete!")


if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='ML Parameter Optimizer')
    parser.add_argument('--symbol', '-s', default='BTCUSDC', help='Symbol to optimize')
    parser.add_argument('--days', '-d', type=int, default=60, help='Days of data')
    parser.add_argument('--method', '-m', choices=['grid', 'walk_forward', 'ml'], default='grid')
    parser.add_argument('--config', '-c', default='config.yaml', help='Config file')
    
    args = parser.parse_args()
    
    optimize(
        symbol=args.symbol,
        days=args.days,
        method=args.method,
        config_path=args.config
    )
