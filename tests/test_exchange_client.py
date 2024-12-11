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
    print("\n[SETUP] Creating mock Kraken exchange...")
    mock_instance = AsyncMock()
    mock_instance.fetch_ohlcv = AsyncMock()
    mock_instance.fetch_ticker = AsyncMock()
    mock_instance.create_order = AsyncMock()
    mock_instance.fetch_balance = AsyncMock()
    
    with patch('ccxt.kraken', return_value=mock_instance) as mock_kraken:
        yield mock_instance
    print("[TEARDOWN] Mock exchange cleaned up")

@pytest.fixture
def client(mock_exchange):
    print("[SETUP] Initializing KrakenClient with $100k USD paper trading balance")
    return KrakenClient(
        api_key="test_key", 
        api_secret="test_secret", 
        paper_trading=True,
        paper_balance={'USD': 100000, 'BTC': 0}
    )

class TestKrakenClient:
    """Test suite for KrakenClient"""

    async def test_fetch_market_data(self, client, mock_exchange):
        print("\n[TEST] Testing market data fetching...")
        
        # Prepare mock data
        mock_data = [
            [1609459200000, 29000.0, 29100.0, 28900.0, 29050.0, 100.0],
            [1609459260000, 29050.0, 29150.0, 28950.0, 29100.0, 150.0]
        ]
        mock_exchange.fetch_ohlcv.return_value = mock_data

        print("  → Fetching BTC/USD market data...")
        result = await client.fetch_market_data("BTC/USD")

        print(f"  → Retrieved {len(result)} candles")
        print(f"  → First candle: Open=${result[0]['open']}, Close=${result[0]['close']}")
        
        assert len(result) == 2
        assert result[0]['timestamp'] == 1609459200000
        assert result[0]['open'] == 29000.0
        mock_exchange.fetch_ohlcv.assert_called_once_with("BTC/USD", "1m", limit=100)
        print("✓ Market data fetch test passed")

    async def test_paper_trading_order(self, client, mock_exchange):
        print("\n[TEST] Testing paper trading order execution...")
        
        # Set up mock ticker response
        mock_exchange.fetch_ticker.return_value = {'last': 29000.0}

        # Verify initial balance
        initial_balance = await client.fetch_balance()
        print(f"  → Initial USD balance: ${initial_balance['USD']['free']}")

        print("  → Executing buy order: 1 BTC @ $29,000")
        order = await client.create_order(
            symbol="BTC/USD",
            order_type="market",
            side="buy",
            amount=1.0
        )

        print(f"  → Order executed: {order['side']} {order['amount']} BTC @ ${order['price']}")
        
        # Verify balance updates
        balance_after_buy = await client.fetch_balance()
        print(f"  → Balance after buy: {balance_after_buy['BTC']['free']} BTC, ${balance_after_buy['USD']['free']} USD")

        # Test selling the BTC at a profit
        mock_exchange.fetch_ticker.return_value = {'last': 30000.0}
        print("\n  → Price increased to $30,000")
        print("  → Executing sell order: 1 BTC @ $30,000")
        
        sell_order = await client.create_order(
            symbol="BTC/USD",
            order_type="market",
            side="sell",
            amount=1.0
        )

        # Verify final balances after selling
        final_balance = await client.fetch_balance()
        profit = final_balance['USD']['free'] - initial_balance['USD']['free']
        print(f"  → Final balance: {final_balance['BTC']['free']} BTC, ${final_balance['USD']['free']} USD")
        print(f"  → Total profit: ${profit}")
        
        assert final_balance['BTC']['free'] == pytest.approx(0.0)
        assert final_balance['USD']['free'] == pytest.approx(101000.0)
        print("✓ Paper trading order test passed")

    async def test_paper_trading_persistence(self, client):
        print("\n[TEST] Testing paper trading state persistence...")
        
        await client.fetch_balance()
        
        state_file = Path('data/paper_trading_results/trading_state.json')
        print(f"  → Checking for state file at: {state_file}")
        assert state_file.exists()
        
        with open(state_file, 'r') as f:
            state = json.load(f)
            print("  → Loaded state file contains:")
            print(f"    - Balance data: {list(state['balance'].keys())}")
            print(f"    - Number of orders: {len(state['orders'])}")
            
        assert 'balance' in state
        assert 'orders' in state
        print("✓ Paper trading persistence test passed")

    def teardown_method(self, method):
        """Clean up after each test method"""
        state_file = Path('data/paper_trading_results/trading_state.json')
        if state_file.exists():
            print(f"\n[CLEANUP] Removing state file: {state_file}")
            os.remove(state_file)