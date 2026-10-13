#!/usr/bin/env python3
"""
test_scale_out.py - Testy dla Scale Out (Partial Profit Taking)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from execution_layer import ScaleOutManager, ScaleOutLevel, ScaleOutState


class TestScaleOutManager(unittest.TestCase):
    """Testy dla ScaleOutManager"""
    
    def setUp(self):
        """Setup przed każdym testem"""
        self.config = {
            'profit_taking': {
                'scale_out': {
                    'enabled': True,
                    'levels': {
                        'tp1': {
                            'rr_multiplier': 1.0,
                            'close_percentage': 50
                        },
                        'tp2': {
                            'rr_multiplier': 1.5,
                            'close_percentage': 30
                        },
                        'tp3': {
                            'rr_multiplier': 2.5,
                            'close_percentage': 20
                        }
                    },
                    'move_sl_to_breakeven_after_tp1': True,
                    'move_sl_to_tp1_after_tp2': True
                }
            }
        }
        self.scale_out = ScaleOutManager(self.config)
    
    def test_initialization(self):
        """Test inicjalizacji"""
        self.assertTrue(self.scale_out.enabled)
        self.assertTrue(self.scale_out.move_sl_to_breakeven_after_tp1)
        self.assertTrue(self.scale_out.move_sl_to_tp1_after_tp2)
        self.assertEqual(self.scale_out.levels_config['tp1']['close_percentage'], 50)
    
    def test_calculate_scale_out_levels_long(self):
        """Test obliczania poziomów dla LONG"""
        entry_price = 50000
        stop_loss = 49000  # Risk = 1000
        quantity = 1.0
        
        levels = self.scale_out.calculate_scale_out_levels(
            entry_price, stop_loss, quantity, 'LONG'
        )
        
        # TP1: entry + risk * 1.0 = 51000
        self.assertAlmostEqual(levels['tp1'].price, 51000, places=2)
        self.assertAlmostEqual(levels['tp1'].quantity, 0.5, places=4)  # 50%
        
        # TP2: entry + risk * 1.5 = 51500
        self.assertAlmostEqual(levels['tp2'].price, 51500, places=2)
        self.assertAlmostEqual(levels['tp2'].quantity, 0.3, places=4)  # 30%
        
        # TP3: entry + risk * 2.5 = 52500
        self.assertAlmostEqual(levels['tp3'].price, 52500, places=2)
        self.assertAlmostEqual(levels['tp3'].quantity, 0.2, places=4)  # 20%
    
    def test_calculate_scale_out_levels_short(self):
        """Test obliczania poziomów dla SHORT"""
        entry_price = 50000
        stop_loss = 51000  # Risk = 1000
        quantity = 1.0
        
        levels = self.scale_out.calculate_scale_out_levels(
            entry_price, stop_loss, quantity, 'SHORT'
        )
        
        # TP1: entry - risk * 1.0 = 49000
        self.assertAlmostEqual(levels['tp1'].price, 49000, places=2)
        
        # TP2: entry - risk * 1.5 = 48500
        self.assertAlmostEqual(levels['tp2'].price, 48500, places=2)
        
        # TP3: entry - risk * 2.5 = 47500
        self.assertAlmostEqual(levels['tp3'].price, 47500, places=2)
    
    def test_register_position(self):
        """Test rejestracji pozycji"""
        state = self.scale_out.register_position(
            symbol='BTCUSDC',
            entry_price=50000,
            stop_loss=49000,
            quantity=1.0,
            direction='LONG'
        )
        
        self.assertEqual(state.symbol, 'BTCUSDC')
        self.assertEqual(state.entry_price, 50000)
        self.assertEqual(state.remaining_quantity, 1.0)
        self.assertIn('tp1', state.levels)
        self.assertIn('BTCUSDC', self.scale_out.active_scale_outs)
    
    def test_check_scale_out_triggers_long(self):
        """Test wykrywania triggerów dla LONG"""
        self.scale_out.register_position(
            symbol='BTCUSDC',
            entry_price=50000,
            stop_loss=49000,
            quantity=1.0,
            direction='LONG'
        )
        
        # Cena poniżej TP1 - brak triggera
        triggered = self.scale_out.check_scale_out_triggers('BTCUSDC', 50500)
        self.assertEqual(len(triggered), 0)
        
        # Cena >= TP1 (51000) - trigger TP1
        triggered = self.scale_out.check_scale_out_triggers('BTCUSDC', 51000)
        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0].level_id, 'tp1')
        
        # Cena >= TP2 (51500) - trigger TP2 (TP1 już triggered)
        triggered = self.scale_out.check_scale_out_triggers('BTCUSDC', 51500)
        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0].level_id, 'tp2')
    
    def test_check_scale_out_triggers_short(self):
        """Test wykrywania triggerów dla SHORT"""
        self.scale_out.register_position(
            symbol='ETHUSDC',
            entry_price=3000,
            stop_loss=3100,  # Risk = 100
            quantity=10.0,
            direction='SHORT'
        )
        
        # TP1: 3000 - 100*1.0 = 2900
        # Cena powyżej TP1 - brak triggera
        triggered = self.scale_out.check_scale_out_triggers('ETHUSDC', 2950)
        self.assertEqual(len(triggered), 0)
        
        # Cena <= TP1 (2900) - trigger TP1
        triggered = self.scale_out.check_scale_out_triggers('ETHUSDC', 2900)
        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0].level_id, 'tp1')
    
    def test_execute_partial_close(self):
        """Test wykonywania partial close"""
        self.scale_out.register_position(
            symbol='BTCUSDC',
            entry_price=50000,
            stop_loss=49000,
            quantity=1.0,
            direction='LONG'
        )
        
        state = self.scale_out.active_scale_outs['BTCUSDC']
        level = state.levels['tp1']
        level.triggered = True
        
        closed_qty, pnl = self.scale_out.execute_partial_close(
            symbol='BTCUSDC',
            level=level,
            actual_close_price=51000
        )
        
        # 50% of 1.0 = 0.5 closed
        self.assertAlmostEqual(closed_qty, 0.5, places=4)
        
        # PnL = (51000 - 50000) * 0.5 = 500
        self.assertAlmostEqual(pnl, 500, places=2)
        
        # Remaining = 1.0 - 0.5 = 0.5
        self.assertAlmostEqual(state.remaining_quantity, 0.5, places=4)
    
    def test_update_stop_loss_after_tp1(self):
        """Test aktualizacji SL po TP1"""
        self.scale_out.register_position(
            symbol='BTCUSDC',
            entry_price=50000,
            stop_loss=49000,
            quantity=1.0,
            direction='LONG'
        )
        
        new_sl = self.scale_out.update_stop_loss_after_tp('BTCUSDC', 'tp1')
        
        # SL powinno być na breakeven (entry price)
        self.assertEqual(new_sl, 50000)
        
        state = self.scale_out.active_scale_outs['BTCUSDC']
        self.assertEqual(state.current_sl, 50000)
    
    def test_update_stop_loss_after_tp2(self):
        """Test aktualizacji SL po TP2"""
        self.scale_out.register_position(
            symbol='BTCUSDC',
            entry_price=50000,
            stop_loss=49000,
            quantity=1.0,
            direction='LONG'
        )
        
        # Trigger TP1 first
        self.scale_out.update_stop_loss_after_tp('BTCUSDC', 'tp1')
        
        # Then TP2
        new_sl = self.scale_out.update_stop_loss_after_tp('BTCUSDC', 'tp2')
        
        # SL powinno być na TP1 price (51000)
        self.assertEqual(new_sl, 51000)
    
    def test_remove_position(self):
        """Test usuwania pozycji"""
        self.scale_out.register_position(
            symbol='BTCUSDC',
            entry_price=50000,
            stop_loss=49000,
            quantity=1.0,
            direction='LONG'
        )
        
        self.assertIn('BTCUSDC', self.scale_out.active_scale_outs)
        
        removed = self.scale_out.remove_position('BTCUSDC')
        
        self.assertIsNotNone(removed)
        self.assertNotIn('BTCUSDC', self.scale_out.active_scale_outs)
    
    def test_get_scale_out_stats(self):
        """Test pobierania statystyk"""
        self.scale_out.register_position(
            symbol='BTCUSDC',
            entry_price=50000,
            stop_loss=49000,
            quantity=1.0,
            direction='LONG'
        )
        
        stats = self.scale_out.get_scale_out_stats('BTCUSDC')
        
        self.assertIsNotNone(stats)
        self.assertEqual(stats['symbol'], 'BTCUSDC')
        self.assertEqual(stats['entry_price'], 50000)
        self.assertEqual(stats['original_quantity'], 1.0)
        self.assertIn('levels', stats)


class TestScaleOutState(unittest.TestCase):
    """Testy dla ScaleOutState"""
    
    def test_scale_out_state_to_dict(self):
        """Test serializacji ScaleOutState"""
        levels = {
            'tp1': ScaleOutLevel(
                level_id='tp1',
                rr_multiplier=1.0,
                close_percentage=50,
                price=51000,
                quantity=0.5
            )
        }
        
        state = ScaleOutState(
            symbol='BTCUSDC',
            entry_price=50000,
            stop_loss=49000,
            original_quantity=1.0,
            remaining_quantity=0.5,
            direction='LONG',
            levels=levels
        )
        
        d = state.to_dict()
        
        self.assertEqual(d['symbol'], 'BTCUSDC')
        self.assertEqual(d['entry_price'], 50000)
        self.assertIn('levels', d)
        self.assertIn('tp1', d['levels'])


if __name__ == '__main__':
    print("\n" + "="*60)
    print("Scale Out (Partial Profit Taking) Tests")
    print("="*60 + "\n")
    
    unittest.main(verbosity=2)
