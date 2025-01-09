import pytest
from src.risk import StopLossManager, StopLossConfig

@pytest.fixture
def basic_config():
    return StopLossConfig(
        fixed_stop_loss_pct=2.0,
        trailing_stop_loss_pct=1.5,
        trailing_activation_pct=1.0,
        max_loss_pct=2.0
    )

@pytest.fixture
def stop_loss_manager(basic_config):
    return StopLossManager(basic_config)

def test_trailing_stop_loss(stop_loss_manager):
    """Test trailing stop loss behavior"""
    position = {'price': 1000.0, 'amount': 1.0}
    stop_loss_manager.start_position_tracking(position)
    
    # Price moves up 1.5% - should activate trailing stop
    status = stop_loss_manager.update(1015.0)
    assert status['trailing_active']
    assert status['stop_price'] == pytest.approx(999.775)
    
    # Price continues up - trailing stop should move up
    status = stop_loss_manager.update(1020.0)
    assert status['stop_price'] == pytest.approx(1004.7)
    
    # Price drops to trigger trailing stop
    status = stop_loss_manager.update(1004.0)
    assert status['stop_triggered']

def test_position_sizing(stop_loss_manager):
    """Test position size calculation based on risk"""
    current_price = 1000.0
    balance = 10000.0
    
    max_position = stop_loss_manager.calculate_max_position_size(
        balance=balance,
        current_price=current_price
    )
    
    # With 2% max loss on $10000 ($200) and 2% stop loss from $1000 ($20)
    # Maximum position should be $200/$20 = 10 units
    assert max_position == pytest.approx(10.0)

def test_no_trailing_stop():
    """Test behavior without trailing stop loss"""
    config = StopLossConfig(fixed_stop_loss_pct=2.0)
    manager = StopLossManager(config)
    
    position = {'price': 1000.0, 'amount': 1.0}
    manager.start_position_tracking(position)
    
    # Price moves up - should not activate trailing
    status = manager.update(1015.0)
    assert not status['trailing_active']
    assert status['stop_price'] == 980.0  # Fixed stop remains