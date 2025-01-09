import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional
from .base_strategy import BaseStrategy
from ..risk import StopLossManager, StopLossConfig

class SimpleMovingAverageStrategy(BaseStrategy):
    def __init__(self, config: Dict):
        """
        Initialize the strategy with configuration parameters.
        
        Args:
            config: Dictionary containing strategy parameters and risk management settings
        """
        super().__init__(config)
        self.logger = logging.getLogger(__name__)
        
        # Strategy parameters
        self.short_window = config['parameters']['short_window']
        self.long_window = config['parameters']['long_window']
        self.position_size_pct = config['risk_management']['max_position_size']
        
        # Extract risk management parameters with defaults
        risk_config = config.get('risk_management', {})
        
        # Initialize stop loss manager with proper configuration
        stop_loss_config = StopLossConfig(
            fixed_stop_loss_pct=risk_config.get('fixed_stop_loss_pct', 2.0),
            max_loss_pct=risk_config.get('max_loss_pct', 2.0),
            # Optional parameters can be None
            trailing_stop_loss_pct=risk_config.get('trailing_stop_loss_pct'),
            trailing_activation_pct=risk_config.get('trailing_activation_pct')
        )
        self.stop_loss_manager = StopLossManager(stop_loss_config)
    
    def _calculate_indicators(self, market_data: List[Dict]) -> pd.DataFrame:
        """
        Calculate technical indicators for the strategy.
        
        Args:
            market_data: List of dictionaries containing OHLCV data
            
        Returns:
            DataFrame with calculated indicators
        """
        df = pd.DataFrame(market_data)
        
        # Calculate simple Moving Averages
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
        Detect trading signals based on MA crossover and trend.
        
        Args:
            df: DataFrame with calculated indicators
            
        Returns:
            Signal type: 'buy', 'sell', or 'hold'
        """
        if len(df) < self.long_window + 1:
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
        """
        Generate trading signals and manage risk.
        
        Args:
            market_data: List of dictionaries containing OHLCV data
            
        Returns:
            Dictionary containing signal information and risk metrics
        """
        if len(market_data) < self.long_window + 1:
            raise ValueError(f"Insufficient data. Need at least {self.long_window + 1} points")
            
        df = self._calculate_indicators(market_data)
        signal_type = self._detect_signal(df)
        current_price = float(df.iloc[-1]['close'])
        
        # Get stop loss status if we have a position
        stop_loss_status = None
        if self.position:
            stop_loss_status = self.stop_loss_manager.update(current_price)
            
            # Check for stop loss trigger
            if stop_loss_status['stop_triggered']:
                signal_type = 'sell'
                self.logger.info(f"Stop loss triggered at {current_price}")
        
        last_row = df.iloc[-1]
        signal = {
            'timestamp': last_row['timestamp'],
            'type': signal_type,
            'price': current_price,
            'short_ma': last_row['short_ma'],
            'long_ma': last_row['long_ma'],
            'trend': last_row['trend'],
            'ma_diff': last_row['ma_diff'],
            'crossover': last_row['crossover']
        }
        
        # Add stop loss information if available
        if stop_loss_status:
            signal.update({
                'stop_loss_price': stop_loss_status['stop_price'],
                'trailing_active': stop_loss_status['trailing_active'],
                'highest_price': stop_loss_status['highest_price']
            })
            
        return signal
    
    def calculate_position_size(self, signal: Dict, balance: float) -> float:
        """
        Calculate position size considering both strategy and risk parameters.
        
        Args:
            signal: Signal dictionary containing price information
            balance: Available balance for trading
            
        Returns:
            Position size in base currency
        """
        if signal['type'] != 'buy':
            return 0.0
            
        # Calculate position size based on strategy parameters
        strategy_size = (balance * self.position_size_pct) / signal['price']
        
        # Calculate maximum position size based on stop loss
        risk_size = self.stop_loss_manager.calculate_max_position_size(
            balance=balance,
            current_price=signal['price']
        )
        
        # Use the smaller of the two sizes
        return min(strategy_size, risk_size)
    
    def should_exit(self, market_data: List[Dict]) -> bool:
        """
        Determine if position should be closed based on signals or stop loss.
        
        Args:
            market_data: List of dictionaries containing OHLCV data
            
        Returns:
            Boolean indicating whether to exit position
        """
        if not self.position:
            return False
            
        current_price = float(market_data[-1]['close'])
        
        # Check stop loss first
        stop_loss_status = self.stop_loss_manager.update(current_price)
        if stop_loss_status['stop_triggered']:
            self.logger.info("Exit signal: Stop loss triggered")
            return True
            
        # Check strategy signals
        df = self._calculate_indicators(market_data)
        signal = self._detect_signal(df)
        
        if signal == 'sell':
            self.logger.info("Exit signal: Strategy sell signal")
            return True
            
        return False
    
    def update_position(self, order: Dict):
        """
        Update position tracking and stop loss management.
        
        Args:
            order: Dictionary containing order details
        """
        super().update_position(order)
        
        # Initialize stop loss tracking for new positions
        if order['side'] == 'buy':
            self.stop_loss_manager.start_position_tracking(order)
            self.logger.info(f"Started stop loss tracking for position at {order['price']}")