#!/usr/bin/env python3
"""
test_execution.py - Testy dla Smart Order Execution
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from execution_layer import SmartOrderExecution, FeeStats


class TestSmartOrderExecution(unittest.TestCase):
    """Testy dla SmartOrderExecution"""
    
    def setUp(self):
        """Setup przed każdym testem"""
        self.config = {
            'execution': {
                'prefer_maker_orders': True,
                'limit_order_timeout': 30,
                'max_spread_pct': 0.1,
                'track_slippage': True,
                'vip_tier': 0
            }
        }
        self.smart_exec = SmartOrderExecution(self.config)
    
    def test_initialization(self):
        """Test inicjalizacji"""
        self.assertTrue(self.smart_exec.enabled)
        self.assertEqual(self.smart_exec.limit_order_timeout, 30)
        self.assertEqual(self.smart_exec.max_spread_pct, 0.1)
        self.assertEqual(self.smart_exec.vip_tier, 0)
    
    def test_fee_rates_regular(self):
        """Test fee rates dla regular tier"""
        rates = self.smart_exec.fee_rates
        
        # Regular: -0.01% maker rebate, 0.04% taker
        self.assertEqual(rates['maker'], -0.0001)
        self.assertEqual(rates['taker'], 0.0004)
    
    def test_fee_rates_vip1(self):
        """Test fee rates dla VIP1"""
        config = {
            'execution': {
                'prefer_maker_orders': True,
                'vip_tier': 1
            }
        }
        smart_exec = SmartOrderExecution(config)
        
        # VIP1: -0.01% maker, 0.03% taker
        self.assertEqual(smart_exec.fee_rates['maker'], -0.0001)
        self.assertEqual(smart_exec.fee_rates['taker'], 0.0003)
    
    def test_fee_rates_vip2(self):
        """Test fee rates dla VIP2"""
        config = {
            'execution': {
                'prefer_maker_orders': True,
                'vip_tier': 2
            }
        }
        smart_exec = SmartOrderExecution(config)
        
        # VIP2: -0.02% maker, 0.02% taker
        self.assertEqual(smart_exec.fee_rates['maker'], -0.0002)
        self.assertEqual(smart_exec.fee_rates['taker'], 0.0002)
    
    def test_check_spread_acceptable(self):
        """Test sprawdzania akceptowalnego spreadu"""
        bid = 50000
        ask = 50040  # Spread = 40, 0.08%
        
        is_ok, spread_pct = self.smart_exec.check_spread(bid, ask)
        
        self.assertTrue(is_ok)
        self.assertLess(spread_pct, 0.1)
    
    def test_check_spread_too_high(self):
        """Test sprawdzania za wysokiego spreadu"""
        bid = 50000
        ask = 50100  # Spread = 100, 0.2%
        
        is_ok, spread_pct = self.smart_exec.check_spread(bid, ask)
        
        self.assertFalse(is_ok)
        self.assertGreater(spread_pct, 0.1)
    
    def test_check_spread_invalid(self):
        """Test sprawdzania nieprawidłowych wartości"""
        is_ok, spread_pct = self.smart_exec.check_spread(0, 50000)
        self.assertFalse(is_ok)
        
        is_ok, spread_pct = self.smart_exec.check_spread(50000, 0)
        self.assertFalse(is_ok)
    
    def test_estimate_total_cost_maker(self):
        """Test szacowania kosztu dla maker order"""
        quantity = 0.1
        price = 50000
        
        cost = self.smart_exec.estimate_total_cost(quantity, price, 'maker')
        
        self.assertEqual(cost['notional'], 5000)
        self.assertEqual(cost['fee_rate'], -0.0001)  # Rebate
        self.assertEqual(cost['fee'], -0.5)  # Negative = rebate
        self.assertEqual(cost['estimated_slippage_pct'], 0.0)  # Maker = no slippage
        self.assertEqual(cost['order_type'], 'maker')
    
    def test_estimate_total_cost_taker(self):
        """Test szacowania kosztu dla taker order"""
        quantity = 0.1
        price = 50000
        
        cost = self.smart_exec.estimate_total_cost(quantity, price, 'taker')
        
        self.assertEqual(cost['notional'], 5000)
        self.assertEqual(cost['fee_rate'], 0.0004)  # 0.04%
        self.assertEqual(cost['fee'], 2.0)  # 5000 * 0.0004
        self.assertEqual(cost['estimated_slippage_pct'], 0.02)  # ~0.02%
        self.assertEqual(cost['order_type'], 'taker')
    
    def test_calculate_slippage_buy(self):
        """Test kalkulacji slippage dla BUY"""
        expected = 50000
        actual = 50010  # Wyższa cena = niekorzystny
        
        slippage = self.smart_exec.calculate_slippage(expected, actual, 'BUY')
        
        # (50010 - 50000) / 50000 * 100 = 0.02%
        self.assertAlmostEqual(slippage, 0.02, places=2)
    
    def test_calculate_slippage_sell(self):
        """Test kalkulacji slippage dla SELL"""
        expected = 50000
        actual = 49990  # Niższa cena = niekorzystny
        
        slippage = self.smart_exec.calculate_slippage(expected, actual, 'SELL')
        
        # (50000 - 49990) / 50000 * 100 = 0.02%
        self.assertAlmostEqual(slippage, 0.02, places=2)
    
    def test_get_optimal_limit_price_buy(self):
        """Test optymalnej ceny limit dla BUY"""
        bid = 50000
        ask = 50010
        
        # Passive (aggression=0) - na best bid
        price = self.smart_exec.get_optimal_limit_price('BUY', bid, ask, 0.0)
        self.assertEqual(price, 50000)
        
        # Aggressive (aggression=1) - bliżej mid
        price = self.smart_exec.get_optimal_limit_price('BUY', bid, ask, 1.0)
        self.assertEqual(price, 50010)  # bid + full spread
    
    def test_get_optimal_limit_price_sell(self):
        """Test optymalnej ceny limit dla SELL"""
        bid = 50000
        ask = 50010
        
        # Passive (aggression=0) - na best ask
        price = self.smart_exec.get_optimal_limit_price('SELL', bid, ask, 0.0)
        self.assertEqual(price, 50010)
        
        # Aggressive (aggression=1) - bliżej mid
        price = self.smart_exec.get_optimal_limit_price('SELL', bid, ask, 1.0)
        self.assertEqual(price, 50000)  # ask - full spread
    
    def test_record_order_execution_maker(self):
        """Test zapisywania maker order"""
        initial_makers = self.smart_exec.fee_stats.total_maker_orders
        
        self.smart_exec.record_order_execution(
            symbol='BTCUSDC',
            side='BUY',
            quantity=0.1,
            expected_price=50000,
            actual_price=50000,
            order_type='maker',
            notional=5000
        )
        
        self.assertEqual(
            self.smart_exec.fee_stats.total_maker_orders,
            initial_makers + 1
        )
    
    def test_record_order_execution_taker(self):
        """Test zapisywania taker order"""
        initial_takers = self.smart_exec.fee_stats.total_taker_orders
        initial_fees = self.smart_exec.fee_stats.total_fees_paid
        
        self.smart_exec.record_order_execution(
            symbol='BTCUSDC',
            side='BUY',
            quantity=0.1,
            expected_price=50000,
            actual_price=50010,
            order_type='taker',
            notional=5001
        )
        
        self.assertEqual(
            self.smart_exec.fee_stats.total_taker_orders,
            initial_takers + 1
        )
        self.assertGreater(
            self.smart_exec.fee_stats.total_fees_paid,
            initial_fees
        )
    
    def test_detect_vip_tier(self):
        """Test wykrywania VIP tier"""
        # Regular < $1M
        self.assertEqual(self.smart_exec.detect_vip_tier(500_000), 0)
        
        # VIP1 >= $1M
        self.assertEqual(self.smart_exec.detect_vip_tier(1_000_000), 1)
        self.assertEqual(self.smart_exec.detect_vip_tier(5_000_000), 1)
        
        # VIP2 >= $10M
        self.assertEqual(self.smart_exec.detect_vip_tier(10_000_000), 2)
        self.assertEqual(self.smart_exec.detect_vip_tier(50_000_000), 2)
    
    def test_get_fee_summary(self):
        """Test pobierania podsumowania fee"""
        summary = self.smart_exec.get_fee_summary()
        
        self.assertIn('total_maker_orders', summary)
        self.assertIn('total_taker_orders', summary)
        self.assertIn('total_fees_paid', summary)
        self.assertIn('total_rebates_earned', summary)
        self.assertIn('net_fees', summary)
        self.assertIn('maker_ratio', summary)


class TestFeeStats(unittest.TestCase):
    """Testy dla FeeStats"""
    
    def test_fee_stats_to_dict(self):
        """Test serializacji FeeStats"""
        stats = FeeStats(
            total_maker_orders=50,
            total_taker_orders=50,
            total_fees_paid=100.0,
            total_rebates_earned=25.0,
            total_slippage=10.0,
            avg_slippage_pct=0.02,
            savings_vs_all_taker=125.0
        )
        
        d = stats.to_dict()
        
        self.assertEqual(d['total_maker_orders'], 50)
        self.assertEqual(d['total_taker_orders'], 50)
        self.assertEqual(d['net_fees'], 75.0)  # 100 - 25
        self.assertEqual(d['maker_ratio'], 50.0)  # 50%


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Smart Order Execution Tests")
    print("="*60 + "\n")
    
    unittest.main(verbosity=2)
