import pytest
import ccxt
from unittest.mock import Mock, patch
from datetime import datetime
from pathlib import Path
import json
import os

from src.exchanges.kraken_client import KrakenClient

@pytest.fixture
def mock_exchange():
    with patch('ccxt.kraken') as mock_kraken:
        mock_instance = Mock()
        mock_kraken.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def client(mock_exchange):
    return KrakenClient(api_key="test_key", api_secret="test_secret", paper_trading=True)

@pytest.fixture
def live_client(mock_exchange):
    return KrakenClient(api_key="test_key", api_secret="test_secret", paper_trading=False)

class TestKrakenClient:
    """Test suite for KrakenClient"""

    @pytest.mark.asyncio
    async def test_fetch_market_data(self, client, mock_exchange):
        # Prepare mock data
        mock_data = [
            [1609459200000, 29000.0, 29100.0, 28900.0, 29050.0, 100.0],  # timestamp, open, high, low, close, volume
            [1609459260000, 29050.0, 29150.0, 28950.0, 29100.0, 150.0]
        ]
        mock_exchange.fetch_ohlcv.return_value = mock_data

        # Test the method
        result = await client.fetch_market_data("BTC/USD")

        # Verify results
        assert len(result) == 2
        assert result[0]['timestamp'] == 1609459200000
        assert result[0]['open'] == 29000.0
        mock_exchange.fetch_ohlcv.assert_called_once_with("BTC/USD", "1m", limit=100)

    @pytest.mark.asyncio
    async def test_paper_trading_order(self, client, mock_exchange):
        # Mock ticker data
        mock_exchange.fetch_ticker.return_value = {'last': 29000.0}

        # Test buy order
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
        balance = await client.fetch_balance()
        assert balance['BTC']['free'] == 1.0
        assert balance['USD']['free'] == 10000 - 29000.0

    @pytest.mark.asyncio
    async def test_live_trading_order(self, live_client, mock_exchange):
        mock_exchange.create_order.return_value = {
            'id': 'test_order',
            'symbol': 'BTC/USD',
            'type': 'limit',
            'side': 'buy',
            'amount': 1.0,
            'price': 29000.0
        }

        order = await live_client.create_order(
            symbol="BTC/USD",
            order_type="limit",
            side="buy",
            amount=1.0,
            price=29000.0
        )

        assert order['symbol'] == "BTC/USD"
        mock_exchange.create_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling(self, client, mock_exchange):
        # Test network error
        mock_exchange.fetch_ticker.side_effect = ccxt.NetworkError("Network error")
        
        with pytest.raises(ccxt.NetworkError):
            await client.get_ticker("BTC/USD")

        # Test exchange error
        mock_exchange.fetch_ticker.side_effect = ccxt.ExchangeError("Exchange error")
        
        with pytest.raises(ccxt.ExchangeError):
            await client.get_ticker("BTC/USD")

    @pytest.mark.asyncio
    async def test_balance_queries(self, live_client, mock_exchange):
        mock_exchange.fetch_balance.return_value = {
            'free': {'BTC': 1.0, 'USD': 10000.0},
            'used': {'BTC': 0.0, 'USD': 0.0},
            'total': {'BTC': 1.0, 'USD': 10000.0}
        }

        balance = await live_client.fetch_balance()
        assert balance['BTC']['free'] == 1.0
        assert balance['USD']['free'] == 10000.0
        mock_exchange.fetch_balance.assert_called_once()

    def test_paper_trading_persistence(self, client):
        # Ensure paper trading state file is created
        assert Path('data/paper_trading_results/trading_state.json').exists()

        # Verify state can be loaded
        with open('data/paper_trading_results/trading_state.json', 'r') as f:
            state = json.load(f)
            assert 'balance' in state
            assert 'orders' in state