"""
Phase 1 Tests: Basic Strategy Framework Testing
Simplified tests for strategy framework and patterns.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Generator

from strategies.base import BaseStrategy, MarketData, TradingSignal
from core.schemas.events import SignalType


class MockStrategy(BaseStrategy):
    """Mock strategy for testing"""
    
    def __init__(self, strategy_id: str = "mock_strategy"):
        super().__init__(
            strategy_id=strategy_id,
            parameters={"test_param": "value"},
            brokers=["paper"],
            instrument_tokens=[256265]  # NIFTY token
        )
        self.signal_count = 0
        self.should_generate_signal = False
        
    def on_market_data(self, data: MarketData) -> Generator[TradingSignal, None, None]:
        """Mock implementation"""
        if self.should_generate_signal:
            self.signal_count += 1
            yield TradingSignal(
                strategy_id=self.strategy_id,
                instrument_token=data.instrument_token,
                signal_type=SignalType.BUY,
                quantity=100,
                timestamp=datetime.now(timezone.utc)
            )


class TestBasicStrategyInterface:
    """Test basic strategy interface"""
    
    def test_strategy_initialization(self):
        """Test strategy initialization"""
        strategy = MockStrategy("test_strategy")
        
        assert strategy.strategy_id == "test_strategy"
        assert strategy.parameters["test_param"] == "value"
        assert strategy.brokers == ["paper"]
        assert 256265 in strategy.instrument_tokens
        
    def test_strategy_market_data_processing(self):
        """Test market data processing"""
        strategy = MockStrategy("test_processing")
        
        market_data = MarketData(
            instrument_token=256265,
            last_price=Decimal("21500.50"),
            volume=1000,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Test no signal generation by default
        signals = list(strategy.on_market_data(market_data))
        assert len(signals) == 0
        
        # Test signal generation when enabled
        strategy.should_generate_signal = True
        signals = list(strategy.on_market_data(market_data))
        assert len(signals) == 1
        
        signal = signals[0]
        assert signal.strategy_id == "test_processing"
        assert signal.instrument_token == 256265
        assert signal.signal_type == SignalType.BUY
        assert signal.quantity == 100
        
    def test_strategy_stateless_processing(self):
        """Test that strategies can process data in stateless manner"""
        strategy = MockStrategy("stateless_test")
        strategy.should_generate_signal = True
        
        market_data = MarketData(
            instrument_token=256265,
            last_price=Decimal("21600.00"),
            volume=500,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Process same data multiple times
        signals1 = list(strategy.on_market_data(market_data))
        signals2 = list(strategy.on_market_data(market_data))
        
        # Should get consistent results
        assert len(signals1) == len(signals2) == 1
        assert signals1[0].signal_type == signals2[0].signal_type
        assert signals1[0].quantity == signals2[0].quantity


class TestMultiStrategyExecution:
    """Test multiple strategy execution"""
    
    def test_multiple_strategy_isolation(self):
        """Test that multiple strategies operate independently"""
        strategy1 = MockStrategy("momentum")
        strategy2 = MockStrategy("mean_reversion")
        
        # Configure strategies differently
        strategy1.should_generate_signal = True
        strategy2.should_generate_signal = False
        
        market_data = MarketData(
            instrument_token=256265,
            last_price=Decimal("21700.00"),
            volume=1200,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Process through both strategies
        signals1 = list(strategy1.on_market_data(market_data))
        signals2 = list(strategy2.on_market_data(market_data))
        
        # Verify independent behavior
        assert len(signals1) == 1  # Strategy1 generates signal
        assert len(signals2) == 0  # Strategy2 doesn't generate signal
        
        assert signals1[0].strategy_id == "momentum"
        
    def test_strategy_configuration_validation(self):
        """Test strategy configuration validation"""
        # Test valid configuration using MockStrategy
        strategy = MockStrategy("valid_strategy")
        strategy.parameters = {"lookback": 20, "threshold": 0.02}
        strategy.brokers = ["paper", "zerodha"]
        strategy.instrument_tokens = [256265, 260105]
        
        assert strategy.strategy_id == "valid_strategy"
        assert strategy.parameters["lookback"] == 20
        assert len(strategy.brokers) == 2
        assert len(strategy.instrument_tokens) == 2


class TestStrategyMarketDataHandling:
    """Test strategy market data handling patterns"""
    
    def test_market_data_validation(self):
        """Test market data structure validation"""
        market_data = MarketData(
            instrument_token=256265,
            last_price=Decimal("21500.50"),
            volume=1000,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Verify required fields
        assert market_data.instrument_token == 256265
        assert market_data.last_price == Decimal("21500.50")
        assert market_data.volume == 1000
        assert market_data.timestamp is not None
        
    def test_trading_signal_validation(self):
        """Test trading signal structure validation"""
        signal = TradingSignal(
            strategy_id="test_signal",
            instrument_token=256265,
            signal_type=SignalType.SELL,
            quantity=150,
            price=Decimal("21600.00"),
            timestamp=datetime.now(timezone.utc),
            confidence=0.85
        )
        
        # Verify required fields
        assert signal.strategy_id == "test_signal"
        assert signal.instrument_token == 256265
        assert signal.signal_type == SignalType.SELL
        assert signal.quantity == 150
        assert signal.price == Decimal("21600.00")
        assert signal.confidence == 0.85
        
    def test_strategy_error_handling(self):
        """Test strategy error handling"""
        
        class ErrorProneStrategy(BaseStrategy):
            def __init__(self, should_error: bool = False):
                super().__init__(
                    strategy_id="error_test",
                    parameters={},
                    brokers=["paper"]
                )
                self.should_error = should_error
                
            def on_market_data(self, data: MarketData):
                if self.should_error:
                    raise ValueError("Strategy processing error")
                return
                yield  # Make it a generator
        
        # Test normal operation
        stable_strategy = ErrorProneStrategy(should_error=False)
        market_data = MarketData(
            instrument_token=256265,
            last_price=Decimal("21500.00"),
            volume=1000,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Should not raise
        signals = list(stable_strategy.on_market_data(market_data))
        assert len(signals) == 0
        
        # Test error condition
        error_strategy = ErrorProneStrategy(should_error=True)
        
        with pytest.raises(ValueError, match="Strategy processing error"):
            list(error_strategy.on_market_data(market_data))