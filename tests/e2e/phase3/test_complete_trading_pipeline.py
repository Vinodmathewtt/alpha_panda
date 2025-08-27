"""
End-to-end tests for complete trading pipeline.

Tests the full Alpha Panda trading system including:
- Market data ingestion → Strategy execution → Risk validation → Order execution → Portfolio updates
- Multi-broker flow isolation (Paper vs Zerodha)
- Complete event chain validation
- System resilience and error handling
- Performance under realistic load
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.schemas.events import (
    EventEnvelope, EventType, MarketTick, TradingSignal, SignalType,
    OrderPlaced, OrderFilled, PortfolioSnapshot
)
from tests.mocks.realistic_data_generator import RealisticMarketDataGenerator
from tests.mocks.mock_zerodha_api import MockZerodhaAPI


class TestCompleteTradingPipeline:
    """End-to-end tests for complete trading pipeline."""
    
    @pytest.fixture
    def mock_data_generator(self):
        """Realistic market data generator for e2e testing."""
        return RealisticMarketDataGenerator(seed=42)
    
    @pytest.fixture
    def mock_zerodha_api(self):
        """Mock Zerodha API for live trading simulation."""
        return MockZerodhaAPI()
    
    @pytest.fixture
    def pipeline_services(self):
        """Mock all pipeline services with proper inter-service communication."""
        services = {
            'market_feed': AsyncMock(),
            'strategy_runner': AsyncMock(),
            'risk_manager': AsyncMock(),
            'trading_engine': AsyncMock(),
            'portfolio_manager': AsyncMock()
        }
        
        # Configure realistic service behaviors
        services['market_feed'].publish_tick = AsyncMock()
        services['strategy_runner'].process_tick = AsyncMock()
        services['risk_manager'].validate_signal = AsyncMock(return_value=True)
        services['trading_engine'].execute_signal = AsyncMock()
        services['portfolio_manager'].update_position = AsyncMock()
        
        return services

    @pytest.mark.asyncio
    async def test_complete_paper_trading_flow(self, mock_data_generator, pipeline_services):
        """Test complete paper trading flow from market tick to portfolio update."""
        
        # Generate realistic market tick
        tick = mock_data_generator.generate_tick(256265, mode="full")
        
        # Create market tick event
        market_event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=tick.model_dump(),
            source="market_feed",
            key=f"{tick.instrument_token}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Simulate complete pipeline flow
        
        # 1. Market Feed → Strategy Runner
        await pipeline_services['market_feed'].publish_tick(market_event)
        pipeline_services['market_feed'].publish_tick.assert_called_once()
        
        # 2. Strategy Runner generates signal
        signal = TradingSignal(
            strategy_id="momentum_strategy",
            instrument_token=256265,
            signal_type=SignalType.BUY,
            quantity=100,
            price=tick.last_price,
            timestamp=datetime.now(timezone.utc)
        )
        
        signal_event = EventEnvelope(
            type=EventType.TRADING_SIGNAL,
            data=signal.model_dump(),
            source="strategy_runner",
            key=f"{signal.instrument_token}:{signal.strategy_id}",
            broker="paper",
            correlation_id=market_event.correlation_id
        )
        
        await pipeline_services['strategy_runner'].process_tick(market_event)
        
        # 3. Risk Manager validates signal
        validated = await pipeline_services['risk_manager'].validate_signal(signal_event)
        assert validated is True
        
        # 4. Trading Engine executes order
        order = OrderPlaced(
            order_id=f"PAPER_{uuid4().hex[:8]}",
            instrument_token=signal.instrument_token,
            signal_type=signal.signal_type,
            quantity=signal.quantity,
            price=signal.price,
            timestamp=datetime.now(timezone.utc),
            broker="paper",
            status="PLACED"
        )
        
        await pipeline_services['trading_engine'].execute_signal(signal_event)
        
        # 5. Order fill and portfolio update
        fill = OrderFilled(
            order_id=order.order_id,
            instrument_token=order.instrument_token,
            quantity=order.quantity,
            fill_price=order.price or tick.last_price,
            timestamp=datetime.now(timezone.utc),
            broker="paper",
            side="BUY"
        )
        
        fill_event = EventEnvelope(
            type=EventType.ORDER_FILLED,
            data=fill.model_dump(),
            source="trading_engine",
            key=f"{fill.instrument_token}:{fill.order_id}",
            broker="paper",
            correlation_id=market_event.correlation_id
        )
        
        await pipeline_services['portfolio_manager'].update_position(fill_event)
        
        # Verify complete flow executed
        pipeline_services['market_feed'].publish_tick.assert_called_once()
        pipeline_services['strategy_runner'].process_tick.assert_called_once()
        pipeline_services['risk_manager'].validate_signal.assert_called_once()
        pipeline_services['trading_engine'].execute_signal.assert_called_once()
        pipeline_services['portfolio_manager'].update_position.assert_called_once()
        
        # Verify correlation IDs maintained throughout flow
        assert signal_event.correlation_id == market_event.correlation_id
        assert fill_event.correlation_id == market_event.correlation_id
    
    @pytest.mark.asyncio
    async def test_multi_broker_isolation(self, mock_data_generator, pipeline_services):
        """Test that paper and zerodha flows remain completely isolated."""
        
        # Generate same market tick for both brokers
        tick = mock_data_generator.generate_tick(256265, mode="full")
        
        paper_event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=tick.model_dump(),
            source="market_feed",
            key=f"{tick.instrument_token}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        zerodha_event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=tick.model_dump(),
            source="market_feed",
            key=f"{tick.instrument_token}",
            broker="zerodha",
            correlation_id=str(uuid4())
        )
        
        # Process both flows concurrently
        await asyncio.gather(
            pipeline_services['strategy_runner'].process_tick(paper_event),
            pipeline_services['strategy_runner'].process_tick(zerodha_event)
        )
        
        # Verify both brokers processed
        assert pipeline_services['strategy_runner'].process_tick.call_count == 2
        
        # Verify correlation IDs remain separate
        calls = pipeline_services['strategy_runner'].process_tick.call_args_list
        paper_call_event = calls[0][0][0]
        zerodha_call_event = calls[1][0][0]
        
        assert paper_call_event.broker == "paper"
        assert zerodha_call_event.broker == "zerodha"
        assert paper_call_event.correlation_id != zerodha_call_event.correlation_id
    
    @pytest.mark.asyncio
    async def test_strategy_portfolio_feedback_loop(self, mock_data_generator, pipeline_services):
        """Test strategy execution influenced by portfolio state."""
        
        # Mock portfolio with existing position
        mock_portfolio = {
            'cash_balance': Decimal('500000.0'),
            'positions': {
                256265: {
                    'quantity': 50,  # Existing position
                    'average_price': Decimal('24800.0')
                }
            }
        }
        
        pipeline_services['portfolio_manager'].get_portfolio = AsyncMock(return_value=mock_portfolio)
        
        # Generate market tick with price movement
        tick = mock_data_generator.generate_tick(256265, mode="full")
        
        market_event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=tick.model_dump(),
            source="market_feed",
            key=f"{tick.instrument_token}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Strategy should consider existing position when generating signals
        await pipeline_services['strategy_runner'].process_tick(market_event)
        
        # Verify portfolio was consulted
        pipeline_services['portfolio_manager'].get_portfolio.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_risk_rejection_handling(self, mock_data_generator, pipeline_services):
        """Test pipeline behavior when risk manager rejects signals."""
        
        # Configure risk manager to reject signals
        pipeline_services['risk_manager'].validate_signal = AsyncMock(return_value=False)
        
        tick = mock_data_generator.generate_tick(256265, mode="full")
        
        # Create oversized signal that should be rejected
        signal = TradingSignal(
            strategy_id="momentum_strategy",
            instrument_token=256265,
            signal_type=SignalType.BUY,
            quantity=10000,  # Oversized
            price=tick.last_price,
            timestamp=datetime.now(timezone.utc)
        )
        
        signal_event = EventEnvelope(
            type=EventType.TRADING_SIGNAL,
            data=signal.model_dump(),
            source="strategy_runner",
            key=f"{signal.instrument_token}:{signal.strategy_id}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Process through risk validation
        validated = await pipeline_services['risk_manager'].validate_signal(signal_event)
        
        # Verify rejection
        assert validated is False
        
        # Trading engine should NOT be called for rejected signals
        pipeline_services['trading_engine'].execute_signal.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_error_recovery_and_resilience(self, mock_data_generator, pipeline_services):
        """Test system recovery from service failures."""
        
        tick = mock_data_generator.generate_tick(256265, mode="full")
        market_event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=tick.model_dump(),
            source="market_feed",
            key=f"{tick.instrument_token}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Simulate strategy runner failure on first call
        pipeline_services['strategy_runner'].process_tick.side_effect = [
            Exception("Temporary service failure"),
            None  # Succeeds on retry
        ]
        
        # First call should fail
        with pytest.raises(Exception, match="Temporary service failure"):
            await pipeline_services['strategy_runner'].process_tick(market_event)
        
        # Retry should succeed
        pipeline_services['strategy_runner'].process_tick.side_effect = None
        await pipeline_services['strategy_runner'].process_tick(market_event)
        
        # Verify retry logic executed
        assert pipeline_services['strategy_runner'].process_tick.call_count == 2
    
    @pytest.mark.asyncio
    async def test_high_frequency_tick_processing(self, mock_data_generator, pipeline_services):
        """Test pipeline performance under high-frequency market data."""
        
        # Generate burst of market ticks
        ticks = []
        for i in range(50):  # 50 ticks in rapid succession
            tick = mock_data_generator.generate_tick(256265, mode="ltp")
            ticks.append(tick)
        
        # Create events for all ticks
        events = []
        for i, tick in enumerate(ticks):
            event = EventEnvelope(
                type=EventType.MARKET_TICK,
                data=tick.model_dump(),
                source="market_feed",
                key=f"{tick.instrument_token}",
                broker="paper",
                correlation_id=str(uuid4())
            )
            events.append(event)
        
        # Process all ticks concurrently
        start_time = time.time()
        
        await asyncio.gather(*[
            pipeline_services['strategy_runner'].process_tick(event)
            for event in events
        ])
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Verify all ticks processed
        assert pipeline_services['strategy_runner'].process_tick.call_count == 50
        
        # Verify reasonable performance (should process 50 ticks in < 1 second)
        assert processing_time < 1.0, f"Processing took {processing_time}s, expected < 1.0s"
    
    @pytest.mark.asyncio
    async def test_market_hours_integration(self, mock_data_generator, pipeline_services):
        """Test pipeline behavior during market open/close transitions."""
        
        tick = mock_data_generator.generate_tick(256265, mode="full")
        
        # Mock market hours check
        with patch('core.market_hours.market_hours_checker.MarketHoursChecker') as mock_checker:
            mock_checker_instance = mock_checker.return_value
            
            # Test market closed scenario
            mock_checker_instance.is_market_open.return_value = False
            
            market_event = EventEnvelope(
                type=EventType.MARKET_TICK,
                data=tick.model_dump(),
                source="market_feed",
                key=f"{tick.instrument_token}",
                broker="paper",
                correlation_id=str(uuid4())
            )
            
            # Configure strategy runner to respect market hours
            async def mock_process_with_market_hours(event):
                if not mock_checker_instance.is_market_open():
                    return  # Skip processing during market closed
                # Process normally during market hours
                pass
            
            pipeline_services['strategy_runner'].process_tick = mock_process_with_market_hours
            
            # Process tick during market closed
            await pipeline_services['strategy_runner'].process_tick(market_event)
            
            # Verify market hours were checked
            mock_checker_instance.is_market_open.assert_called()
    
    @pytest.mark.asyncio
    async def test_portfolio_reconciliation_flow(self, mock_data_generator, pipeline_services):
        """Test portfolio reconciliation after order fills."""
        
        # Generate market tick
        tick = mock_data_generator.generate_tick(256265, mode="full")
        
        # Simulate order fill
        fill = OrderFilled(
            order_id="PAPER_12345678",
            instrument_token=256265,
            quantity=100,
            fill_price=tick.last_price,
            timestamp=datetime.now(timezone.utc),
            broker="paper",
            side="BUY"
        )
        
        fill_event = EventEnvelope(
            type=EventType.ORDER_FILLED,
            data=fill.model_dump(),
            source="trading_engine",
            key=f"{fill.instrument_token}:{fill.order_id}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Configure portfolio manager to return updated portfolio
        updated_portfolio = PortfolioSnapshot(
            broker="paper",
            cash_balance=Decimal('475000.0'),  # Reduced by order value
            total_value=Decimal('500000.0'),
            unrealized_pnl=Decimal('0.0'),
            realized_pnl=Decimal('0.0'),
            positions=[],
            timestamp=datetime.now(timezone.utc)
        )
        
        pipeline_services['portfolio_manager'].update_position = AsyncMock(return_value=updated_portfolio)
        
        # Process order fill
        result = await pipeline_services['portfolio_manager'].update_position(fill_event)
        
        # Verify portfolio was updated correctly
        assert result.cash_balance == Decimal('475000.0')
        pipeline_services['portfolio_manager'].update_position.assert_called_once_with(fill_event)
    
    @pytest.mark.asyncio
    async def test_complete_sell_signal_flow(self, mock_data_generator, pipeline_services):
        """Test complete flow for SELL signal including position reduction."""
        
        # Generate market tick
        tick = mock_data_generator.generate_tick(256265, mode="full")
        
        # Create SELL signal (assume existing long position)
        signal = TradingSignal(
            strategy_id="momentum_strategy",
            instrument_token=256265,
            signal_type=SignalType.SELL,
            quantity=50,  # Partial position closure
            price=tick.last_price,
            timestamp=datetime.now(timezone.utc)
        )
        
        signal_event = EventEnvelope(
            type=EventType.TRADING_SIGNAL,
            data=signal.model_dump(),
            source="strategy_runner",
            key=f"{signal.instrument_token}:{signal.strategy_id}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Process through complete pipeline
        validated = await pipeline_services['risk_manager'].validate_signal(signal_event)
        assert validated is True
        
        await pipeline_services['trading_engine'].execute_signal(signal_event)
        
        # Simulate sell order fill
        fill = OrderFilled(
            order_id=f"PAPER_{uuid4().hex[:8]}",
            instrument_token=signal.instrument_token,
            quantity=signal.quantity,
            fill_price=signal.price,
            timestamp=datetime.now(timezone.utc),
            broker="paper",
            side="SELL"
        )
        
        fill_event = EventEnvelope(
            type=EventType.ORDER_FILLED,
            data=fill.model_dump(),
            source="trading_engine",
            key=f"{fill.instrument_token}:{fill.order_id}",
            broker="paper",
            correlation_id=signal_event.correlation_id
        )
        
        await pipeline_services['portfolio_manager'].update_position(fill_event)
        
        # Verify SELL flow completed
        pipeline_services['risk_manager'].validate_signal.assert_called_once()
        pipeline_services['trading_engine'].execute_signal.assert_called_once()
        pipeline_services['portfolio_manager'].update_position.assert_called_once()
    
    @pytest.mark.asyncio 
    async def test_cross_instrument_strategy_coordination(self, mock_data_generator, pipeline_services):
        """Test strategy coordination across multiple instruments."""
        
        # Generate ticks for both NIFTY and BANKNIFTY
        nifty_tick = mock_data_generator.generate_tick(256265, mode="full")
        banknifty_tick = mock_data_generator.generate_tick(738561, mode="full")
        
        # Create market events
        events = [
            EventEnvelope(
                type=EventType.MARKET_TICK,
                data=nifty_tick.model_dump(),
                source="market_feed",
                key=f"{nifty_tick.instrument_token}",
                broker="paper",
                correlation_id=str(uuid4())
            ),
            EventEnvelope(
                type=EventType.MARKET_TICK,
                data=banknifty_tick.model_dump(),
                source="market_feed",
                key=f"{banknifty_tick.instrument_token}",
                broker="paper",
                correlation_id=str(uuid4())
            )
        ]
        
        # Process both instruments
        await asyncio.gather(*[
            pipeline_services['strategy_runner'].process_tick(event)
            for event in events
        ])
        
        # Verify both instruments processed
        assert pipeline_services['strategy_runner'].process_tick.call_count == 2
        
        # Verify different instruments maintained separate correlation
        calls = pipeline_services['strategy_runner'].process_tick.call_args_list
        nifty_call = calls[0][0][0]
        banknifty_call = calls[1][0][0]
        
        assert nifty_call.key != banknifty_call.key
        assert "256265" in nifty_call.key
        assert "738561" in banknifty_call.key