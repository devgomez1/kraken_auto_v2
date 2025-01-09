from dataclasses import dataclass
from typing import Dict, Optional
import logging

@dataclass
class StopLossConfig:
    """Configuration for stop loss management"""
    fixed_stop_loss_pct: float  # Fixed stop loss percentage
    max_loss_pct: float = 2.0  # Maximum loss percentage per trade
    trailing_stop_loss_pct: Optional[float] = None  # Trailing stop loss percentage
    trailing_activation_pct: Optional[float] = None  # Profit % to activate trailing stop

class StopLossManager:
    """Manages stop loss calculations and tracking for trading positions"""
    
    def __init__(self, config: StopLossConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.position: Dict = {}
        self.highest_price = 0.0
        self.stop_loss_price = 0.0
        self.trailing_active = False
    
    def _calculate_fixed_stop_loss(self, price: Optional[float] = None) -> float:
        """Calculate fixed stop loss price"""
        if price is None and not self.position:
            raise ValueError("Need either a price or an active position")
            
        entry_price = price if price is not None else float(self.position['price'])
        stop_distance = entry_price * (self.config.fixed_stop_loss_pct / 100)
        return entry_price - stop_distance

    def _calculate_trailing_stop_loss(self) -> float:
        """Calculate trailing stop loss based on highest price"""
        if self.config.trailing_stop_loss_pct is None:
            raise ValueError("Trailing stop loss percentage not configured")
            
        trail_distance = self.highest_price * (self.config.trailing_stop_loss_pct / 100)
        return self.highest_price - trail_distance

    def start_position_tracking(self, position: Dict) -> float:
        """
        Start tracking a new position and calculate initial stop loss
        Returns the initial stop loss price
        """
        self.position = position
        self.highest_price = float(position['price'])
        
        # Calculate initial fixed stop loss
        self.stop_loss_price = self._calculate_fixed_stop_loss()
        self.trailing_active = False
        
        self.logger.info(f"Started position tracking - Entry: {self.highest_price}, Stop: {self.stop_loss_price}")
        return self.stop_loss_price

    def update(self, current_price: float) -> Dict[str, float]:
        """
        Update stop loss based on current price
        Returns dict with current stop price and status
        """
        if not self.position:
            return {'stop_price': 0.0, 'stop_triggered': False}

        # Update highest price if price has increased
        if current_price > self.highest_price:
            self.highest_price = current_price

            # Check if trailing stop should be activated
            if (not self.trailing_active and 
                self.config.trailing_stop_loss_pct is not None and
                self.config.trailing_activation_pct is not None):
                
                profit_pct = ((current_price - float(self.position['price'])) / 
                            float(self.position['price'])) * 100
                
                if profit_pct >= self.config.trailing_activation_pct:
                    self.trailing_active = True
                    self.logger.info(f"Trailing stop activated at price {current_price}")

        # Update stop loss price if trailing is active
        if self.trailing_active:
            new_stop = self._calculate_trailing_stop_loss()
            if new_stop > self.stop_loss_price:
                self.stop_loss_price = new_stop
                self.logger.info(f"Trailing stop updated to {self.stop_loss_price}")

        # Check if stop loss is triggered
        stop_triggered = current_price <= self.stop_loss_price

        return {
            'stop_price': self.stop_loss_price,
            'stop_triggered': stop_triggered,
            'trailing_active': self.trailing_active,
            'highest_price': self.highest_price
        }

    def calculate_max_position_size(self, balance: float, current_price: float) -> float:
        """
        Calculate maximum position size based on maximum loss percentage
        """
        max_loss = balance * (self.config.max_loss_pct / 100)
        stop_price = self._calculate_fixed_stop_loss(current_price)
        price_to_stop = current_price - stop_price
        
        if price_to_stop <= 0:
            return 0.0
            
        return max_loss / price_to_stop