import pytest
import ccxt
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from pathlib import Path
import json
import os

from src.exchanges.kraken_client import KrakenClient

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_exchange():
    mock_instance = AsyncMock()
    # Create async mock methods with their return values
    mock_instance.fetch_ohlcv = AsyncMock()
    mock_instance.fetch_ticker = AsyncMock()
    mock_instance.create_order = AsyncMock()
    mock_instance.fetch_balance = AsyncMock()
    
    with patch('ccxt.kraken', return_value=mock_instance) as mock_kraken:
        yield mock_instance

@pytest.fixture
def client(mock_exchange):
    # Initialize with enough balance to execute test trades
    return KrakenClient(
        api_key="test_key", 
        api_secret="test_secret", 
        paper_trading=True,
        paper_balance={'USD': 100000, 'BTC': 0}  # $100k USD starting balance
    )

class TestKrakenClient:
    """Test suite for KrakenClient"""

    async def test_fetch_market_data(self, client, mock_exchange):
        # Prepare mock data
        mock_data = [
            [1609459200000, 29000.0, 29100.0, 28900.0, 29050.0, 100.0],
            [1609459260000, 29050.0, 29150.0, 28950.0, 29100.0, 150.0]
        ]
        # Set the return value for the async mock
        mock_exchange.fetch_ohlcv.return_value = mock_data

        result = await client.fetch_market_data("BTC/USD")

        assert len(result) == 2
        assert result[0]['timestamp'] == 1609459200000
        assert result[0]['open'] == 29000.0
        mock_exchange.fetch_ohlcv.assert_called_once_with("BTC/USD", "1m", limit=100)

    async def test_paper_trading_order(self, client, mock_exchange):
        # Set up mock ticker response
        mock_exchange.fetch_ticker.return_value = {'last': 29000.0}

        # Verify initial balance
        initial_balance = await client.fetch_balance()
        assert initial_balance['USD']['free'] == 100000

        order = await client.create_order(
            symbol="BTC/USD",
            order_type="market",
            side="buy",
            amount=1.0
        )

        assert order['symbol'] == "BTC/USD"
        assert order['type'] == "market"
        assert order['side'] == "buy"
        assert order['amount'] == 1.0
        assert order['price'] == 29000.0
        assert order['status'] == "closed"

        # Verify balance updates
        final_balance = await client.fetch_balance()
        assert final_balance['BTC']['free'] == 1.0
        assert final_balance['USD']['free'] == pytest.approx(100000 - 29000.0)

        # Test selling the BTC
        mock_exchange.fetch_ticker.return_value = {'last': 30000.0}  # Price went up
        sell_order = await client.create_order(
            symbol="BTC/USD",
            order_type="market",
            side="sell",
            amount=1.0
        )

        assert sell_order['status'] == "closed"
        assert sell_order['price'] == 30000.0

        # Verify final balances after selling
        final_balance = await client.fetch_balance()
        assert final_balance['BTC']['free'] == pytest.approx(0.0)
        assert final_balance['USD']['free'] == pytest.approx(101000.0)  # Original 100k + 1k profit

    async def test_paper_trading_persistence(self, client):
        await client.fetch_balance()  # This will trigger state file creation
        
        assert Path('data/paper_trading_results/trading_state.json').exists()
        
        with open('data/paper_trading_results/trading_state.json', 'r') as f:
            state = json.load(f)
            assert 'balance' in state
            assert 'orders' in state

    def teardown_method(self, method):
        """Clean up after each test method"""
        if Path('data/paper_trading_results/trading_state.json').exists():
            os.remove('data/paper_trading_results/trading_state.json')