#!/usr/bin/env python3
"""
test_kelly.py - Testy dla Kelly Criterion Position Sizing
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from risk_manager import KellyCalculator, KellyResult


class TestKellyCalculator(unittest.TestCase):
    """Testy dla KellyCalculator"""
    
    def setUp(self):
        """Setup przed każdym testem"""
        self.config = {
            'position_sizing': {
                'method': 'kelly',
                'kelly': {
                    'enabled': True,
                    'use_half_kelly': True,
                    'min_trades_required': 20,
                    'update_frequency': 50,
                    'min_position_pct': 0.5,
                    'max_position_pct': 5.0
                },
                'fixed': {
                    'risk_per_trade': 2.0
                }
            }
        }
        self.kelly = KellyCalculator(self.config)
    
    def test_kelly_initialization(self):
        """Test inicjalizacji"""
        self.assertTrue(self.kelly.enabled)
        self.assertTrue(self.kelly.use_half_kelly)
        self.assertEqual(self.kelly.min_trades_required, 20)
        self.assertEqual(self.kelly.min_position_pct, 0.5)
        self.assertEqual(self.kelly.max_position_pct, 5.0)
    
    def test_kelly_fallback_insufficient_trades(self):
        """Test fallback gdy za mało trade'ów"""
        # 10 trade'ów < 20 required
        trades = [
            {'pnl': 100, 'risk_amount': 50} for _ in range(10)
        ]
        
        result = self.kelly.calculate_kelly_fraction(trades)
        
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.optimal_position_pct, 2.0)  # Fixed fallback
        self.assertEqual(result.confidence, 'LOW')
    
    def test_kelly_calculation_winning_strategy(self):
        """Test kalkulacji Kelly dla wygrywającej strategii"""
        # 70% win rate, avg win = 2R, avg loss = 1R
        trades = []
        for i in range(70):
            trades.append({'pnl': 200, 'risk_amount': 100})  # Winners
        for i in range(30):
            trades.append({'pnl': -100, 'risk_amount': 100})  # Losers
        
        result = self.kelly.calculate_kelly_fraction(trades)
        
        self.assertFalse(result.fallback_used)
        self.assertGreater(result.kelly_fraction, 0)
        self.assertGreater(result.optimal_position_pct, 0.5)
        self.assertLessEqual(result.optimal_position_pct, 5.0)
        self.assertAlmostEqual(result.win_rate, 70.0, delta=1)
    
    def test_kelly_calculation_losing_strategy(self):
        """Test kalkulacji Kelly dla przegrywającej strategii"""
        # 30% win rate, avg win = 1R, avg loss = 1R
        trades = []
        for i in range(30):
            trades.append({'pnl': 100, 'risk_amount': 100})  # Winners
        for i in range(70):
            trades.append({'pnl': -100, 'risk_amount': 100})  # Losers
        
        result = self.kelly.calculate_kelly_fraction(trades)
        
        # Dla przegrywającej strategii Kelly powinno być niskie lub min
        self.assertLessEqual(result.optimal_position_pct, 2.0)
    
    def test_kelly_half_kelly_applied(self):
        """Test czy Half-Kelly jest stosowane"""
        trades = [
            {'pnl': 200, 'risk_amount': 100} for _ in range(60)
        ] + [
            {'pnl': -100, 'risk_amount': 100} for _ in range(40)
        ]
        
        result = self.kelly.calculate_kelly_fraction(trades)
        
        # Half-Kelly powinno być połową pełnego Kelly
        self.assertAlmostEqual(result.half_kelly, result.kelly_fraction * 0.5, places=4)
    
    def test_kelly_position_limits(self):
        """Test czy limity pozycji są przestrzegane"""
        # Stwórz ekstremalnie dobrą strategię
        trades = [
            {'pnl': 500, 'risk_amount': 50} for _ in range(100)  # 100% win, 10R avg
        ]
        
        result = self.kelly.calculate_kelly_fraction(trades)
        
        # Powinno być ograniczone do max 5%
        self.assertLessEqual(result.optimal_position_pct, 5.0)
        self.assertGreaterEqual(result.optimal_position_pct, 0.5)
    
    def test_get_optimal_position_size(self):
        """Test obliczania optymalnej wielkości pozycji"""
        # Najpierw oblicz Kelly
        trades = [
            {'pnl': 200, 'risk_amount': 100} for _ in range(60)
        ] + [
            {'pnl': -100, 'risk_amount': 100} for _ in range(40)
        ]
        kelly_result = self.kelly.calculate_kelly_fraction(trades)
        
        # Oblicz position size
        capital = 10000
        entry_price = 50000
        stop_loss = 49000  # 1000 USDC risk per BTC
        
        quantity, risk_pct = self.kelly.get_optimal_position_size(
            capital=capital,
            entry_price=entry_price,
            stop_loss=stop_loss,
            direction='LONG'
        )
        
        self.assertGreater(quantity, 0)
        self.assertEqual(risk_pct, kelly_result.optimal_position_pct)
    
    def test_should_update(self):
        """Test logiki aktualizacji Kelly"""
        # Pierwszy raz - powinno wymagać update
        self.assertTrue(self.kelly.should_update(0))
        
        # Po update
        self.kelly.mark_updated(50)
        self.assertFalse(self.kelly.should_update(60))  # 10 < 50
        self.assertTrue(self.kelly.should_update(100))  # 50 >= 50
    
    def test_kelly_confidence_levels(self):
        """Test poziomów confidence"""
        # 25 trades = LOW confidence
        trades_25 = [{'pnl': 100, 'risk_amount': 50} for _ in range(25)]
        result = self.kelly.calculate_kelly_fraction(trades_25)
        self.assertEqual(result.confidence, 'LOW')
        
        # 35 trades = MEDIUM confidence
        trades_35 = [{'pnl': 100, 'risk_amount': 50} for _ in range(35)]
        result = self.kelly.calculate_kelly_fraction(trades_35)
        self.assertEqual(result.confidence, 'MEDIUM')
        
        # 60 trades = HIGH confidence
        trades_60 = [{'pnl': 100, 'risk_amount': 50} for _ in range(60)]
        result = self.kelly.calculate_kelly_fraction(trades_60)
        self.assertEqual(result.confidence, 'HIGH')


class TestKellyResult(unittest.TestCase):
    """Testy dla KellyResult dataclass"""
    
    def test_kelly_result_to_dict(self):
        """Test serializacji KellyResult"""
        result = KellyResult(
            kelly_fraction=0.15,
            half_kelly=0.075,
            optimal_position_pct=3.5,
            win_rate=65.0,
            avg_win_rr=2.1,
            avg_loss_rr=1.0,
            trades_analyzed=50,
            confidence='HIGH',
            fallback_used=False
        )
        
        d = result.to_dict()
        
        self.assertIn('kelly_fraction', d)
        self.assertIn('optimal_position_pct', d)
        self.assertIn('confidence', d)
        self.assertEqual(d['trades_analyzed'], 50)


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Kelly Criterion Position Sizing Tests")
    print("="*60 + "\n")
    
    unittest.main(verbosity=2)
