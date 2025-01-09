# src/strategies/base_strategy.py

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd

class BaseStrategy(ABC):
    """Abstract base class for all trading strategies"""
    
    def __init__(self, config: Dict):
        """
        Initialize strategy with configuration parameters
        
        Args:
            config: Strategy configuration dictionary
        """
        self.config = config
        self.position = None
        self.signals = []
    
    @abstractmethod
    async def generate_signals(self, market_data: List[Dict]) -> Dict:
        """
        Generate trading signals from market data
        
        Args:
            market_data: List of OHLCV dictionaries
            
        Returns:
            Dict containing signal information
        """
        pass
    
    @abstractmethod
    def calculate_position_size(self, signal: Dict, balance: float) -> float:
        """
        Calculate the position size for a trade
        
        Args:
            signal: Signal dictionary containing trade information
            balance: Current account balance
            
        Returns:
            Position size in base currency
        """
        pass
    
    @abstractmethod
    def should_exit(self, market_data: List[Dict]) -> bool:
        """
        Determine if current position should be closed
        
        Args:
            market_data: List of OHLCV dictionaries
            
        Returns:
            True if position should be closed, False otherwise
        """
        pass

    def validate_signal(self, signal: Dict) -> bool:
        """
        Validate a trading signal
        
        Args:
            signal: Signal dictionary to validate
            
        Returns:
            True if signal is valid, False otherwise
        """
        required_fields = ['timestamp', 'type', 'price']
        return all(field in signal for field in required_fields)
    
    def update_position(self, order: Dict):
        """
        Update the current position based on executed order
        
        Args:
            order: Executed order information
        """
        if order['side'] == 'buy':
            self.position = {
                'entry_price': order['price'],
                'size': order['amount'],
                'timestamp': order['datetime']
            }
        else:
            self.position = None
    
    def calculate_risk_metrics(self, market_data: List[Dict]) -> Dict:
        """
        Calculate risk metrics for current position
        
        Args:
            market_data: List of OHLCV dictionaries
            
        Returns:
            Dictionary containing risk metrics
        """
        if not self.position:
            return {}
            
        current_price = market_data[-1]['close']
        entry_price = self.position['entry_price']
        position_size = self.position['size']
        
        unrealized_pnl = (current_price - entry_price) * position_size
        return {
            'unrealized_pnl': unrealized_pnl,
            'pnl_percentage': (unrealized_pnl / (entry_price * position_size)) * 100,
            'position_value': current_price * position_size
        }