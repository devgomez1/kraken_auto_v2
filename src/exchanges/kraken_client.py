import ccxt
import logging
import os
import json
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

class KrakenClient:
    """
    A wrapper class for interacting with the Kraken exchange using CCXT.
    Includes paper trading simulation capabilities.
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None, paper_trading: bool = True,
                 paper_balance: Dict[str, float] = None):
        """
        Initialize the Kraken client.
        
        Args:
            api_key: Kraken API key
            api_secret: Kraken API secret
            paper_trading: If True, use paper trading simulation
            paper_balance: Initial paper trading balance (e.g., {'USD': 10000, 'BTC': 1})
        """
        self.logger = logging.getLogger(__name__)
        self.paper_trading = paper_trading
        
        # Initialize the CCXT Kraken exchange
        self.exchange = ccxt.kraken({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True
        })
        
        # Setup paper trading
        if paper_trading:
            self.paper_balance = paper_balance or {'USD': 10000}
            self.paper_orders = []
            self._setup_paper_trading()
    
    def _setup_paper_trading(self):
        """Setup paper trading directory and state"""
        # Create paper trading results directory if it doesn't exist
        paper_trading_dir = Path('data/paper_trading_results')
        paper_trading_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = paper_trading_dir / 'trading_state.json'
        self._load_paper_trading_state()
    
    def _load_paper_trading_state(self):
        """Load paper trading state from file if it exists"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.paper_balance = state.get('balance', self.paper_balance)
                    self.paper_orders = state.get('orders', [])
                self.logger.info("Loaded paper trading state")
        except Exception as e:
            self.logger.error(f"Error loading paper trading state: {e}")
    
    def _save_paper_trading_state(self):
        """Save paper trading state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump({
                    'balance': self.paper_balance,
                    'orders': self.paper_orders
                }, f, indent=4)
            self.logger.debug("Saved paper trading state")
        except Exception as e:
            self.logger.error(f"Error saving paper trading state: {e}")

    async def fetch_market_data(self, symbol: str, timeframe: str = '1m', 
                              limit: int = 100) -> List[Dict]:
        """
        Fetch OHLCV market data for a given symbol.
        Works the same for both live and paper trading.
        """
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return [
                {
                    'timestamp': candle[0],
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5]
                }
                for candle in ohlcv
            ]
        except ccxt.NetworkError as e:
            self.logger.error(f"Network error fetching market data: {str(e)}")
            raise
        except ccxt.ExchangeError as e:
            self.logger.error(f"Exchange error fetching market data: {str(e)}")
            raise

    async def create_order(self, symbol: str, order_type: str, side: str, 
                         amount: float, price: Optional[float] = None) -> Dict:
        """
        Create a new order. Uses paper trading simulation if enabled.
        """
        if self.paper_trading:
            return await self._create_paper_order(symbol, order_type, side, amount, price)
        
        try:
            params = {}
            if order_type == 'limit' and price is None:
                raise ValueError("Price is required for limit orders")
                
            order = await self.exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=amount,
                price=price,
                params=params
            )
            self.logger.info(f"Created {order_type} {side} order for {amount} {symbol}")
            return order
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            self.logger.error(f"Error creating order: {str(e)}")
            raise

    async def _create_paper_order(self, symbol: str, order_type: str, side: str,
                                amount: float, price: Optional[float] = None) -> Dict:
        """
        Simulate order creation for paper trading.
        """
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            execution_price = price if order_type == 'limit' else ticker['last']
            
            # Parse the trading pair
            base, quote = symbol.split('/')
            
            # Check if we have enough balance
            if side == 'buy':
                required_quote = amount * execution_price
                if self.paper_balance.get(quote, 0) < required_quote:
                    raise ValueError(f"Insufficient paper trading balance in {quote}")
                
                # Update paper balances
                self.paper_balance[quote] = self.paper_balance.get(quote, 0) - required_quote
                self.paper_balance[base] = self.paper_balance.get(base, 0) + amount
            
            else:  # sell
                if self.paper_balance.get(base, 0) < amount:
                    raise ValueError(f"Insufficient paper trading balance in {base}")
                
                # Update paper balances
                self.paper_balance[base] = self.paper_balance.get(base, 0) - amount
                self.paper_balance[quote] = self.paper_balance.get(quote, 0) + (amount * execution_price)
            
            # Create paper order record
            order = {
                'id': f"paper_{len(self.paper_orders)}",
                'datetime': datetime.now().isoformat(),
                'symbol': symbol,
                'type': order_type,
                'side': side,
                'amount': amount,
                'price': execution_price,
                'status': 'closed'  # Paper orders are executed immediately
            }
            
            self.paper_orders.append(order)
            self._save_paper_trading_state()
            
            return order
            
        except Exception as e:
            self.logger.error(f"Error in paper trading order: {str(e)}")
            raise

    async def fetch_balance(self) -> Dict[str, float]:
        """
        Fetch account balances. Returns paper trading balance if enabled.
        """
        if self.paper_trading:
            return {
                currency: {
                    'free': amount,
                    'used': 0,
                    'total': amount
                }
                for currency, amount in self.paper_balance.items()
            }
        
        try:
            balance = await self.exchange.fetch_balance()
            return {
                currency: {
                    'free': float(balance['free'].get(currency, 0)),
                    'used': float(balance['used'].get(currency, 0)),
                    'total': float(balance['total'].get(currency, 0))
                }
                for currency in balance['total'].keys()
                if balance['total'].get(currency, 0) > 0
            }
        except ccxt.NetworkError as e:
            self.logger.error(f"Network error fetching balance: {str(e)}")
            raise
        except ccxt.ExchangeError as e:
            self.logger.error(f"Exchange error fetching balance: {str(e)}")
            raise

    async def fetch_order(self, order_id: str, symbol: str) -> Dict:
        """
        Fetch details of a specific order. Returns paper order if in paper trading mode.
        """
        if self.paper_trading:
            order = next((order for order in self.paper_orders if order['id'] == order_id), None)
            if order is None:
                raise ValueError(f"Paper order {order_id} not found")
            return order
        
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except ccxt.NetworkError as e:
            self.logger.error(f"Network error fetching order: {str(e)}")
            raise
        except ccxt.ExchangeError as e:
            self.logger.error(f"Exchange error fetching order: {str(e)}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """
        Cancel an existing order. Only available in live trading mode.
        """
        if self.paper_trading:
            raise NotImplementedError("Cancel order not implemented for paper trading (orders execute immediately)")
        
        try:
            return await self.exchange.cancel_order(order_id, symbol)
        except ccxt.NetworkError as e:
            self.logger.error(f"Network error canceling order: {str(e)}")
            raise
        except ccxt.ExchangeError as e:
            self.logger.error(f"Exchange error canceling order: {str(e)}")
            raise

    async def get_ticker(self, symbol: str) -> Dict:
        """
        Get current ticker information for a symbol.
        Works the same for both live and paper trading.
        """
        try:
            return await self.exchange.fetch_ticker(symbol)
        except (ccxt.NetworkError, ccxt.ExchangeError) as e:
            self.logger.error(f"Error fetching ticker: {str(e)}")
            raise