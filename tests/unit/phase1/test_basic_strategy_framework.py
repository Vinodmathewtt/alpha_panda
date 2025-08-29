"""
Phase 1 Tests: Basic Strategy Framework Testing
Updated to use composition-based strategy architecture
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

from strategies.core.executor import StrategyExecutor
from strategies.core.protocols import StrategyProcessor, StrategyValidator, SignalResult
from strategies.core.config import StrategyConfig, ExecutionContext
from core.schemas.events import MarketTick as MarketData, SignalType


class MockStrategyProcessor:
    """Mock strategy processor for testing"""
    
    def __init__(self, strategy_name: str = "mock_strategy"):
        self.strategy_name = strategy_name
        self.signal_count = 0
        self.should_generate_signal = False
        
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """Mock processing implementation"""
        if self.should_generate_signal:
            self.signal_count += 1
            return SignalResult(
                signal_type="BUY",
                confidence=0.8,
                quantity=100,
                price=tick.last_price,
                reasoning="Mock signal generation",
                metadata={"test": "value"}
            )
        return None
    
    def get_required_history_length(self) -> int:
        return 10
    
    def supports_instrument(self, token: int) -> bool:
        return token in [256265]  # NIFTY token
    
    def get_strategy_name(self) -> str:
        return self.strategy_name


class MockStrategyValidator:
    """Mock strategy validator for testing"""
    
    def __init__(self, should_validate: bool = True):
        self.should_validate = should_validate
    
    def validate_signal(self, signal: SignalResult, market_data: MarketData) -> bool:
        return self.should_validate
    
    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        return True


def create_mock_strategy_executor(strategy_id: str = "test_strategy", should_generate: bool = False) -> StrategyExecutor:
    """Create mock strategy executor for testing"""
    processor = MockStrategyProcessor(strategy_id)
    processor.should_generate_signal = should_generate
    
    validator = MockStrategyValidator()
    
    config = StrategyConfig(
        strategy_id=strategy_id,
        strategy_type="mock",
        parameters={"test_param": "value"},
        active_brokers=["paper"],
        instrument_tokens=[256265],
        max_position_size=Decimal("10000"),
        risk_multiplier=Decimal("1.0"),
        enabled=True
    )
    
    context = ExecutionContext(
        broker="paper",
        portfolio_state={},
        market_session="regular",
        risk_limits={"max_loss": Decimal("1000")}
    )
    
    return StrategyExecutor(processor, validator, config, context)


class TestBasicStrategyInterface:
    """Test basic strategy interface using composition"""
    
    def test_strategy_initialization(self):
        """Test strategy executor initialization"""
        executor = create_mock_strategy_executor("test_strategy")
        
        assert executor.config.strategy_id == "test_strategy"
        assert executor.config.parameters["test_param"] == "value"
        assert executor.config.active_brokers == ["paper"]
        assert 256265 in executor.config.instrument_tokens
        
    def test_strategy_market_data_processing(self):
        """Test market data processing"""
        executor = create_mock_strategy_executor("test_processing", should_generate=False)
        
        market_data = MarketData(
            instrument_token=256265,
            last_price=Decimal("21500.50"),
            volume_traded=1000,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Test no signal generation by default
        signal = executor.process_tick(market_data)
        assert signal is None
        
        # Test signal generation when enabled
        executor._processor.should_generate_signal = True
        signal = executor.process_tick(market_data)
        assert signal is not None
        
        assert signal.signal_type == "BUY"
        assert signal.quantity == 100
        assert signal.confidence == 0.8
        assert signal.price == Decimal("21500.50")
        
    def test_strategy_can_process_tick(self):
        """Test tick processing eligibility"""
        executor = create_mock_strategy_executor("eligibility_test")
        
        # Valid tick for supported instrument
        valid_tick = MarketData(
            instrument_token=256265,  # Supported instrument
            last_price=Decimal("21600.00"),
            volume_traded=500,
            timestamp=datetime.now(timezone.utc)
        )
        
        assert executor.can_process_tick(valid_tick) is True
        
        # Invalid tick for unsupported instrument
        invalid_tick = MarketData(
            instrument_token=999999,  # Unsupported instrument
            last_price=Decimal("21600.00"),
            volume_traded=500,
            timestamp=datetime.now(timezone.utc)
        )
        
        assert executor.can_process_tick(invalid_tick) is False


class TestMultiStrategyExecution:
    """Test multiple strategy execution"""
    
    def test_multiple_strategy_isolation(self):
        """Test that multiple strategies operate independently"""
        executor1 = create_mock_strategy_executor("momentum", should_generate=True)
        executor2 = create_mock_strategy_executor("mean_reversion", should_generate=False)
        
        market_data = MarketData(
            instrument_token=256265,
            last_price=Decimal("21700.00"),
            volume_traded=1200,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Process through both strategies
        signal1 = executor1.process_tick(market_data)
        signal2 = executor2.process_tick(market_data)
        
        # Verify independent behavior
        assert signal1 is not None  # Strategy1 generates signal
        assert signal2 is None      # Strategy2 doesn't generate signal
        
        assert signal1.signal_type == "BUY"
        
    def test_strategy_configuration_validation(self):
        """Test strategy configuration validation"""
        config = StrategyConfig(
            strategy_id="valid_strategy",
            strategy_type="test",
            parameters={"lookback": 20, "threshold": 0.02},
            active_brokers=["paper", "zerodha"],
            instrument_tokens=[256265, 260105],
            max_position_size=Decimal("50000"),
            risk_multiplier=Decimal("1.5"),
            enabled=True
        )
        
        assert config.strategy_id == "valid_strategy"
        assert config.parameters["lookback"] == 20
        assert len(config.active_brokers) == 2
        assert len(config.instrument_tokens) == 2


class TestStrategyMarketDataHandling:
    """Test strategy market data handling patterns"""
    
    def test_market_data_validation(self):
        """Test market data structure validation"""
        market_data = MarketData(
            instrument_token=256265,
            last_price=Decimal("21500.50"),
            volume_traded=1000,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Verify required fields
        assert market_data.instrument_token == 256265
        assert market_data.last_price == Decimal("21500.50")
        assert market_data.volume_traded == 1000
        assert market_data.timestamp is not None
        
    def test_signal_result_validation(self):
        """Test signal result structure validation"""
        signal = SignalResult(
            signal_type="SELL",
            confidence=0.85,
            quantity=150,
            price=Decimal("21600.00"),
            reasoning="Test signal",
            metadata={"source": "test"}
        )
        
        # Verify required fields
        assert signal.signal_type == "SELL"
        assert signal.confidence == 0.85
        assert signal.quantity == 150
        assert signal.price == Decimal("21600.00")
        assert signal.reasoning == "Test signal"
        assert signal.metadata["source"] == "test"
        
    def test_strategy_error_handling(self):
        """Test strategy error handling"""
        
        class ErrorProneProcessor(MockStrategyProcessor):
            def __init__(self, should_error: bool = False):
                super().__init__("error_test")
                self.should_error = should_error
                
            def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
                if self.should_error:
                    raise ValueError("Strategy processing error")
                return None
        
        # Test error condition
        error_processor = ErrorProneProcessor(should_error=True)
        validator = MockStrategyValidator()
        
        config = StrategyConfig(
            strategy_id="error_test",
            strategy_type="error_prone",
            parameters={},
            active_brokers=["paper"],
            instrument_tokens=[256265],
            max_position_size=Decimal("10000"),
            risk_multiplier=Decimal("1.0"),
            enabled=True
        )
        
        context = ExecutionContext(
            broker="paper",
            portfolio_state={},
            market_session="regular",
            risk_limits={}
        )
        
        executor = StrategyExecutor(error_processor, validator, config, context)
        
        market_data = MarketData(
            instrument_token=256265,
            last_price=Decimal("21500.00"),
            volume_traded=1000,
            timestamp=datetime.now(timezone.utc)
        )
        
        with pytest.raises(ValueError, match="Strategy processing error"):
            executor.process_tick(market_data)


class TestStrategyHistoryManagement:
    """Test strategy history management"""
    
    def test_history_length_management(self):
        """Test that history is managed according to required length"""
        executor = create_mock_strategy_executor("history_test")
        
        # Process multiple ticks
        for i in range(15):  # More than required history length (10)
            tick = MarketData(
                instrument_token=256265,
                last_price=Decimal(f"2150{i}.00"),
                volume_traded=1000 + i,
                timestamp=datetime.now(timezone.utc)
            )
            executor.process_tick(tick)
        
        # Verify history is limited to required length
        assert len(executor._history) == 10  # Max history length
        
    def test_strategy_metrics(self):
        """Test strategy execution metrics"""
        executor = create_mock_strategy_executor("metrics_test")
        
        metrics = executor.get_metrics()
        
        assert metrics["strategy_id"] == "metrics_test"
        assert metrics["broker"] == "paper"
        assert metrics["history_length"] == 0  # No ticks processed yet
        assert metrics["supported_instruments"] == 1  # One instrument configured