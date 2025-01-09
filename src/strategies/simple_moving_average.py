# src/strategies/simple_moving_average.py

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from .base_strategy import BaseStrategy

class SimpleMovingAverageStrategy(BaseStrategy):
    def __init__(self, config: Dict):
        super().__init__(config)
        self.short_window = config['parameters']['short_window']
        self.long_window = config['parameters']['long_window']
        self.position_size_pct = config['risk_management']['max_position_size']
    
    def _calculate_indicators(self, market_data: List[Dict]) -> pd.DataFrame:
        """Calculate technical indicators for the strategy"""
        df = pd.DataFrame(market_data)
        
        # Calculate simple MAs
        df['short_ma'] = df['close'].rolling(window=self.short_window).mean()
        df['long_ma'] = df['close'].rolling(window=self.long_window).mean()
        
        # Calculate trend strength using the close price
        df['trend'] = df['close'].pct_change(periods=self.short_window)
        
        # Calculate MA crossover signal
        df['ma_diff'] = df['short_ma'] - df['long_ma']
        df['crossover'] = np.where(
            df['ma_diff'] * df['ma_diff'].shift(1) < 0,  # Detect sign change
            np.sign(df['ma_diff']),  # 1 for bullish crossover, -1 for bearish
            0  # No crossover
        )
        
        return df
    
    def _detect_signal(self, df: pd.DataFrame) -> str:
        """
        Detect trading signals based on MA crossover and trend
        """
        if len(df) < self.long_window + 1:  # Need at least long_window + 1 points
            return 'hold'
        
        # Get last row with all indicators
        df = df.dropna()
        if len(df) == 0:
            return 'hold'
            
        last_row = df.iloc[-1]
        
        # Check for crossover signal
        if last_row['crossover'] > 0:  # Bullish crossover
            return 'buy'
        elif last_row['crossover'] < 0:  # Bearish crossover
            return 'sell'
            
        # If no crossover, check trend direction
        strong_trend = abs(last_row['trend']) > 0.01  # 1% change threshold
        
        if strong_trend:
            if last_row['trend'] > 0 and last_row['ma_diff'] > 0:
                return 'buy'
            elif last_row['trend'] < 0 and last_row['ma_diff'] < 0:
                return 'sell'
        
        return 'hold'
    
    async def generate_signals(self, market_data: List[Dict]) -> Dict:
        """Generate trading signals"""
        if len(market_data) < self.long_window + 1:
            raise ValueError(f"Insufficient data. Need at least {self.long_window + 1} points")
            
        df = self._calculate_indicators(market_data)
        signal_type = self._detect_signal(df)
        
        last_row = df.iloc[-1]
        return {
            'timestamp': last_row['timestamp'],
            'type': signal_type,
            'price': last_row['close'],
            'short_ma': last_row['short_ma'],
            'long_ma': last_row['long_ma'],
            'trend': last_row['trend'],
            'ma_diff': last_row['ma_diff'],
            'crossover': last_row['crossover']
        }
    
    def calculate_position_size(self, signal: Dict, balance: float) -> float:
        """Calculate position size"""
        if signal['type'] != 'buy':
            return 0.0
        return (balance * self.position_size_pct) / signal['price']
    
    def should_exit(self, market_data: List[Dict]) -> bool:
        """Determine if position should be closed"""
        if not self.position:
            return False
            
        df = self._calculate_indicators(market_data)
        signal = self._detect_signal(df)
        
        return signal == 'sell'