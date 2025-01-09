# tests/test_strategy.py

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict

from src.strategies.simple_moving_average import SimpleMovingAverageStrategy

@pytest.fixture
def strategy_config():
    return {
        'parameters': {
            'short_window': 5,
            'long_window': 10
        },
        'risk_management': {
            'max_position_size': 0.1
        }
    }

def generate_trend_data(base_price: float, periods: int, trend: str = 'up') -> List[Dict]:
    """Generate price data with clear trend reversals"""
    data = []
    base_time = datetime(2024, 1, 1)
    
    for i in range(periods):
        if trend == 'up':
            # First third: sideways with slight upward bias
            if i < periods // 3:
                change = 0.001
            # Middle third: strong upward trend
            elif i < 2 * periods // 3:
                change = 0.05
            # Final third: continued but slower upward trend
            else:
                change = 0.02
        else:  # downtrend
            # First third: sideways with slight downward bias
            if i < periods // 3:
                change = -0.001
            # Middle third: strong downward trend
            elif i < 2 * periods // 3:
                change = -0.05
            # Final third: continued but slower downward trend
            else:
                change = -0.02
        
        # Calculate cumulative effect
        price = base_price * (1 + change * (i - periods // 3))
        
        # Add minimal noise
        noise = np.random.normal(0, 0.0001 * price)
        final_price = price + noise
        
        data.append({
            'timestamp': int((base_time + timedelta(hours=i)).timestamp() * 1000),
            'open': final_price * 0.999,
            'high': final_price * 1.001,
            'low': final_price * 0.998,
            'close': final_price,
            'volume': 1000 + i * 100
        })
    
    return data

def visualize_signals(market_data: List[Dict], strategy: SimpleMovingAverageStrategy) -> None:
    """Helper function to visualize signals for debugging"""
    df = strategy._calculate_indicators(market_data)
    print("\nSignal Analysis:")
    print(f"Last 5 rows of indicators:")
    print(df[['close', 'short_ma', 'long_ma', 'ma_diff', 'crossover', 'trend']].tail().round(4))
    
    df = df.dropna()
    if len(df) > 0:
        last_row = df.iloc[-1]
        print("\nSignal Conditions:")
        print(f"MA Difference: {last_row['ma_diff']:.4f}")
        print(f"Crossover Signal: {last_row['crossover']:.4f}")
        print(f"Trend: {last_row['trend']:.4%}")
        
        if last_row['crossover'] > 0:
            print("BULLISH CROSSOVER DETECTED")
        elif last_row['crossover'] < 0:
            print("BEARISH CROSSOVER DETECTED")
        elif abs(last_row['trend']) > 0.01:
            if last_row['trend'] > 0 and last_row['ma_diff'] > 0:
                print("STRONG UPTREND DETECTED")
            elif last_row['trend'] < 0 and last_row['ma_diff'] < 0:
                print("STRONG DOWNTREND DETECTED")
        else:
            print("NO SIGNAL DETECTED")

class TestSimpleMovingAverageStrategy:
    """Test suite for Simple Moving Average Strategy"""
    
    @pytest.mark.asyncio
    async def test_signal_generation(self, strategy_config):
        """Test that strategy generates correct signals"""
        strategy = SimpleMovingAverageStrategy(strategy_config)
        
        # Test buy signal during uptrend
        uptrend_data = generate_trend_data(1000, 20, 'up')
        signal = await strategy.generate_signals(uptrend_data)
        visualize_signals(uptrend_data, strategy)
        
        assert signal['type'] == 'buy', (
            f"Expected buy signal, got {signal['type']}\n"
            f"Short MA: {signal['short_ma']:.2f}, Long MA: {signal['long_ma']:.2f}\n"
            f"Trend: {signal['trend']:.2%}, Crossover: {signal['crossover']:.2f}"
        )
        
        # Test sell signal during downtrend
        downtrend_data = generate_trend_data(2000, 20, 'down')
        signal = await strategy.generate_signals(downtrend_data)
        visualize_signals(downtrend_data, strategy)
        
        assert signal['type'] == 'sell', (
            f"Expected sell signal, got {signal['type']}\n"
            f"Short MA: {signal['short_ma']:.2f}, Long MA: {signal['long_ma']:.2f}\n"
            f"Trend: {signal['trend']:.2%}, Crossover: {signal['crossover']:.2f}"
        )
    
    def test_position_size_calculation(self, strategy_config):
        """Test position sizing logic"""
        strategy = SimpleMovingAverageStrategy(strategy_config)
        signal = {'timestamp': 1000000, 'type': 'buy', 'price': 1000.0}
        
        balance = 10000.0
        position_size = strategy.calculate_position_size(signal, balance)
        expected_size = (balance * 0.1) / signal['price']
        assert position_size == pytest.approx(expected_size)
        
        signal['type'] = 'sell'
        position_size = strategy.calculate_position_size(signal, balance)
        assert position_size == 0.0
    
    def test_risk_metrics(self, strategy_config):
        """Test risk metrics calculation"""
        strategy = SimpleMovingAverageStrategy(strategy_config)
        
        # Test position entry
        entry_order = {
            'side': 'buy',
            'price': 1000.0,
            'amount': 1.0,
            'datetime': '2024-01-01T00:00:00'
        }
        strategy.update_position(entry_order)
        
        # Test profit scenario
        current_data = [{
            'timestamp': 1000000,
            'open': 1100.0,
            'high': 1110.0,
            'low': 1090.0,
            'close': 1100.0,
            'volume': 1000
        }]
        
        metrics = strategy.calculate_risk_metrics(current_data)
        assert metrics['unrealized_pnl'] == 100.0
        assert metrics['pnl_percentage'] == pytest.approx(10.0)
        
        # Test loss scenario
        current_data[0]['close'] = 900.0
        metrics = strategy.calculate_risk_metrics(current_data)
        assert metrics['unrealized_pnl'] == -100.0
        assert metrics['pnl_percentage'] == pytest.approx(-10.0)
    
    @pytest.mark.asyncio
    async def test_exit_signals(self, strategy_config):
        """Test exit signal generation"""
        strategy = SimpleMovingAverageStrategy(strategy_config)
        strategy.update_position({
            'side': 'buy',
            'price': 1000.0,
            'amount': 1.0,
            'datetime': '2024-01-01T00:00:00'
        })
        
        # Test no exit during uptrend
        uptrend_data = generate_trend_data(1000, 20, 'up')
        should_exit = strategy.should_exit(uptrend_data)
        visualize_signals(uptrend_data, strategy)
        assert not should_exit, "Should not exit during uptrend"
        
        # Test exit during downtrend
        downtrend_data = generate_trend_data(2000, 20, 'down')
        should_exit = strategy.should_exit(downtrend_data)
        visualize_signals(downtrend_data, strategy)
        assert should_exit, "Should exit during downtrend"