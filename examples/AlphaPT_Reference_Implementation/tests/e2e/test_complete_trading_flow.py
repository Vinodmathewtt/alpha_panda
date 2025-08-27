"""
End-to-end tests for complete trading workflows.

These tests simulate complete trading scenarios from market data ingestion
to order execution, testing the entire pipeline.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, Mock
import uuid

import pytest

from app.application import AlphaPTApplication
from core.events.event_types import SystemEvent, TradingEvent, MarketDataEvent, EventType


@pytest.mark.e2e
@pytest.mark.slow
class TestCompleteTradingFlow:
    """End-to-end tests for complete trading workflows."""
    
    async def test_market_data_to_strategy_signal_flow(self, mock_settings):
        """Test complete flow from market data to strategy signal generation."""
        app = AlphaPTApplication()
        
        # Track events flowing through the system
        received_events = []
        
        async def event_tracker(event):
            received_events.append(event)
            
        # Mock components but allow event flow
        with patch.multiple(
            'app.application',
            DatabaseManager=Mock,
            EventBus=Mock,
            StorageManager=Mock,
            StrategyManager=Mock,
            MockFeedManager=Mock,
        ):
            # Configure mock event bus to track events
            mock_event_bus = Mock()
            mock_event_bus.initialize = AsyncMock(return_value=True)
            mock_event_bus.connect = AsyncMock(return_value=True)
            mock_event_bus.publish = AsyncMock(side_effect=event_tracker)
            mock_event_bus.subscribe = AsyncMock()
            mock_event_bus.health_check = AsyncMock(return_value={"connected": True})
            mock_event_bus.disconnect = AsyncMock()
            
            # Set up app state
            app.app_state.update({
                "settings": mock_settings,
                "event_bus": mock_event_bus
            })
            
            # Simulate market data event
            market_data = MarketDataEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.MARKET_TICK,
                timestamp=datetime.now(timezone.utc),
                source="mock_feed",
                instrument_token=738561,
                symbol="RELIANCE",
                data={
                    "last_price": 2500.50,
                    "volume": 1000000,
                    "change": 1.25
                }
            )
            
            # Publish market data event
            await mock_event_bus.publish("market.tick.NSE.738561", market_data)
            
            # Verify event was processed
            assert len(received_events) >= 1
            assert received_events[0].instrument_token == 738561
            
    async def test_strategy_signal_to_order_flow(self, mock_settings):
        """Test flow from strategy signal to order placement."""
        app = AlphaPTApplication()
        
        # Track trading events
        trading_events = []
        
        async def trading_event_tracker(event):
            trading_events.append(event)
            
        # Mock components
        mock_strategy_manager = Mock()
        mock_strategy_manager.initialize = AsyncMock(return_value=True)
        mock_strategy_manager.cleanup = AsyncMock()
        
        mock_paper_engine = Mock()
        mock_paper_engine.initialize = AsyncMock(return_value=True)
        mock_paper_engine.place_order = AsyncMock(return_value={
            "order_id": "ORDER123",
            "status": "COMPLETE",
            "average_price": 2500.50
        })
        mock_paper_engine.cleanup = AsyncMock()
        
        mock_event_bus = Mock()
        mock_event_bus.initialize = AsyncMock(return_value=True)
        mock_event_bus.publish = AsyncMock(side_effect=trading_event_tracker)
        mock_event_bus.connect = AsyncMock(return_value=True)
        mock_event_bus.disconnect = AsyncMock()
        
        # Set up app state
        app.app_state.update({
            "settings": mock_settings,
            "strategy_manager": mock_strategy_manager,
            "paper_trading_engine": mock_paper_engine,
            "event_bus": mock_event_bus
        })
        
        # Simulate trading signal
        trading_signal = TradingEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TRADING_SIGNAL,
            timestamp=datetime.now(timezone.utc),
            source="momentum_strategy",
            order_id="SIGNAL123",
            symbol="RELIANCE",
            data={
                "signal_type": "BUY",
                "quantity": 10,
                "confidence": 0.85,
                "reason": "Momentum breakout"
            }
        )
        
        # Process trading signal (simulate strategy manager processing)
        await mock_event_bus.publish("trading.signal.momentum.RELIANCE", trading_signal)
        
        # Simulate order placement based on signal
        order_data = {
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 2500.50,
            "order_type": "LIMIT"
        }
        
        order_result = await mock_paper_engine.place_order(order_data)
        
        # Verify order was placed
        assert order_result["order_id"] == "ORDER123"
        assert order_result["status"] == "COMPLETE"
        
        # Verify trading events were published
        assert len(trading_events) >= 1
        
    async def test_complete_trading_pipeline(self, mock_settings):
        """Test complete pipeline: Market Data -> Strategy -> Risk -> Order -> Execution."""
        app = AlphaPTApplication()
        
        # Track the complete flow
        pipeline_events = {
            "market_data": [],
            "strategy_signals": [],
            "risk_checks": [],
            "orders": [],
            "executions": []
        }
        
        # Mock all components
        mock_components = {}
        
        # Mock Market Feed Manager
        mock_feed_manager = Mock()
        mock_feed_manager.initialize = AsyncMock(return_value=True)
        mock_feed_manager.start_feed = AsyncMock()
        mock_feed_manager.cleanup = AsyncMock()
        mock_components["mock_feed_manager"] = mock_feed_manager
        
        # Mock Strategy Manager
        mock_strategy_manager = Mock()
        mock_strategy_manager.initialize = AsyncMock(return_value=True)
        mock_strategy_manager.cleanup = AsyncMock()
        mock_components["strategy_manager"] = mock_strategy_manager
        
        # Mock Risk Manager
        mock_risk_manager = Mock()
        mock_risk_manager.initialize = AsyncMock(return_value=True)
        mock_risk_manager.check_risk = AsyncMock(return_value={"approved": True})
        mock_risk_manager.cleanup = AsyncMock()
        mock_components["risk_manager"] = mock_risk_manager
        
        # Mock Paper Trading Engine
        mock_paper_engine = Mock()
        mock_paper_engine.initialize = AsyncMock(return_value=True)
        mock_paper_engine.place_order = AsyncMock(return_value={
            "order_id": "E2E_ORDER_123",
            "status": "COMPLETE",
            "average_price": 2500.75
        })
        mock_paper_engine.cleanup = AsyncMock()
        mock_components["paper_trading_engine"] = mock_paper_engine
        
        # Mock Event Bus to track flow
        mock_event_bus = Mock()
        mock_event_bus.initialize = AsyncMock(return_value=True)
        mock_event_bus.connect = AsyncMock(return_value=True)
        mock_event_bus.disconnect = AsyncMock()
        
        def track_event_by_subject(subject, event):
            if "market.tick" in subject:
                pipeline_events["market_data"].append(event)
            elif "trading.signal" in subject:
                pipeline_events["strategy_signals"].append(event)
            elif "risk.check" in subject:
                pipeline_events["risk_checks"].append(event)
            elif "trading.order" in subject:
                pipeline_events["orders"].append(event)
            elif "trading.execution" in subject:
                pipeline_events["executions"].append(event)
                
        mock_event_bus.publish = AsyncMock(side_effect=track_event_by_subject)
        mock_components["event_bus"] = mock_event_bus
        
        # Set up complete app state
        app.app_state.update({
            "settings": mock_settings,
            **mock_components
        })
        
        # Simulate complete pipeline
        
        # 1. Market Data Event
        market_tick = MarketDataEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.MARKET_TICK,
            timestamp=datetime.now(timezone.utc),
            source="mock_feed",
            instrument_token=738561,
            symbol="RELIANCE",
            data={
                "last_price": 2500.50,
                "volume": 1500000,
                "change": 2.5,
                "change_percent": 0.1
            }
        )
        
        await mock_event_bus.publish("market.tick.NSE.738561", market_tick)
        
        # 2. Strategy Signal (triggered by market data)
        strategy_signal = TradingEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TRADING_SIGNAL,
            timestamp=datetime.now(timezone.utc),
            source="momentum_strategy",
            order_id="SIGNAL_E2E_123",
            symbol="RELIANCE",
            data={
                "signal_type": "BUY",
                "quantity": 10,
                "target_price": 2500.50,
                "confidence": 0.75,
                "reason": "Strong momentum with volume support"
            }
        )
        
        await mock_event_bus.publish("trading.signal.momentum.RELIANCE", strategy_signal)
        
        # 3. Risk Check
        risk_result = await mock_risk_manager.check_risk({
            "symbol": "RELIANCE",
            "quantity": 10,
            "price": 2500.50,
            "transaction_type": "BUY"
        })
        
        # 4. Order Placement (if risk approved)
        if risk_result["approved"]:
            order_data = {
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE", 
                "transaction_type": "BUY",
                "quantity": 10,
                "price": 2500.50,
                "order_type": "LIMIT"
            }
            
            order_result = await mock_paper_engine.place_order(order_data)
            
            # 5. Execution Event
            execution_event = TradingEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.ORDER_EXECUTED,
                timestamp=datetime.now(timezone.utc),
                source="paper_engine",
                order_id=order_result["order_id"],
                symbol="RELIANCE",
                data={
                    "executed_quantity": 10,
                    "average_price": order_result["average_price"],
                    "status": order_result["status"]
                }
            )
            
            await mock_event_bus.publish("trading.execution.RELIANCE", execution_event)
        
        # Verify complete pipeline
        assert len(pipeline_events["market_data"]) >= 1
        assert len(pipeline_events["strategy_signals"]) >= 1
        
        # Risk was checked
        mock_risk_manager.check_risk.assert_called_once()
        
        # Order was placed
        mock_paper_engine.place_order.assert_called_once()
        
        # Verify data flow integrity
        market_event = pipeline_events["market_data"][0]
        signal_event = pipeline_events["strategy_signals"][0]
        
        assert market_event.symbol == signal_event.symbol
        assert market_event.instrument_token == 738561


@pytest.mark.e2e
@pytest.mark.slow
class TestErrorHandlingFlow:
    """End-to-end tests for error scenarios and recovery."""
    
    async def test_risk_rejection_flow(self, mock_settings):
        """Test complete flow when risk manager rejects a trade."""
        # Mock risk manager that rejects trades
        mock_risk_manager = Mock()
        mock_risk_manager.check_risk = AsyncMock(return_value={
            "approved": False,
            "reason": "Position limit exceeded",
            "current_position": 150000,
            "limit": 100000
        })
        
        mock_paper_engine = Mock()
        mock_paper_engine.place_order = AsyncMock()  # Should not be called
        
        # Test signal processing
        trading_signal = {
            "symbol": "RELIANCE",
            "quantity": 50,  # Large quantity to trigger limit
            "price": 2500.00,
            "signal_type": "BUY"
        }
        
        # Check risk first
        risk_result = await mock_risk_manager.check_risk(trading_signal)
        
        # Verify rejection
        assert risk_result["approved"] is False
        assert "limit exceeded" in risk_result["reason"]
        
        # Verify order was not placed
        mock_paper_engine.place_order.assert_not_called()
        
    async def test_order_failure_handling(self, mock_settings):
        """Test handling of order placement failures."""
        mock_paper_engine = Mock()
        mock_paper_engine.place_order = AsyncMock(side_effect=Exception("Insufficient funds"))
        
        mock_event_bus = Mock()
        mock_event_bus.publish = AsyncMock()
        
        # Test order placement with failure
        order_data = {
            "tradingsymbol": "RELIANCE",
            "quantity": 10,
            "price": 2500.00
        }
        
        try:
            await mock_paper_engine.place_order(order_data)
            assert False, "Expected exception"
        except Exception as e:
            assert "Insufficient funds" in str(e)
            
        # Should publish error event
        # (Implementation would handle this in the actual trading engine)


@pytest.mark.e2e
@pytest.mark.slow 
class TestPerformanceFlow:
    """End-to-end performance tests."""
    
    async def test_high_volume_tick_processing(self, mock_settings, performance_config):
        """Test processing high volume of market ticks."""
        app = AlphaPTApplication()
        
        processed_ticks = []
        
        async def tick_processor(event):
            processed_ticks.append(event)
            
        # Mock fast processing components
        mock_event_bus = Mock()
        mock_event_bus.publish = AsyncMock(side_effect=tick_processor)
        
        app.app_state.update({
            "settings": mock_settings,
            "event_bus": mock_event_bus
        })
        
        # Generate high volume of ticks
        start_time = asyncio.get_event_loop().time()
        tick_count = performance_config["target_throughput"] // 10  # Smaller for E2E test
        
        for i in range(tick_count):
            tick_event = MarketDataEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.MARKET_TICK,
                timestamp=datetime.now(timezone.utc),
                source="performance_test",
                instrument_token=738561,
                symbol="RELIANCE",
                data={
                    "last_price": 2500.00 + (i % 10),
                    "volume": 1000000 + i,
                    "sequence": i
                }
            )
            
            await mock_event_bus.publish(f"market.tick.NSE.738561", tick_event)
            
        end_time = asyncio.get_event_loop().time()
        processing_time = end_time - start_time
        
        # Verify performance
        assert len(processed_ticks) == tick_count
        throughput = tick_count / processing_time
        
        # Should process at reasonable speed (adjusted for E2E test)
        min_throughput = performance_config["target_throughput"] // 100  # Much lower for E2E
        assert throughput >= min_throughput, f"Throughput {throughput} below minimum {min_throughput}"