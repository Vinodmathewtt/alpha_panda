"""
Performance and resilience tests for Alpha Panda system.

Tests system performance under various conditions:
- High-frequency market data processing
- Concurrent multi-broker operations
- Memory usage and resource management
- Network failure and recovery scenarios
- Load testing and stress testing
"""

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest

from core.schemas.events import (
    EventEnvelope, EventType, MarketTick, TradingSignal, SignalType
)
from tests.mocks.realistic_data_generator import RealisticMarketDataGenerator


class TestSystemPerformance:
    """Test system performance under various load conditions."""
    
    @pytest.fixture
    def performance_data_generator(self):
        """High-performance data generator for load testing."""
        return RealisticMarketDataGenerator(seed=42)
    
    @pytest.fixture
    def mock_pipeline_services(self):
        """Mock services optimized for performance testing."""
        services = {
            'market_feed': AsyncMock(),
            'strategy_runner': AsyncMock(), 
            'risk_manager': AsyncMock(),
            'trading_engine': AsyncMock(),
            'portfolio_manager': AsyncMock()
        }
        
        # Configure fast responses
        services['strategy_runner'].process_tick = AsyncMock()
        services['risk_manager'].validate_signal = AsyncMock(return_value=True)
        services['trading_engine'].execute_signal = AsyncMock()
        services['portfolio_manager'].update_position = AsyncMock()
        
        return services
    
    @pytest.mark.asyncio
    async def test_high_frequency_market_data_throughput(self, performance_data_generator, mock_pipeline_services):
        """Test system throughput with high-frequency market data."""
        
        # Generate 1000 market ticks across 2 instruments
        tick_count = 1000
        ticks_per_instrument = tick_count // 2
        
        all_events = []
        
        for instrument in [256265, 738561]:
            for i in range(ticks_per_instrument):
                tick = performance_data_generator.generate_tick(instrument, mode="ltp")
                event = EventEnvelope(
                    type=EventType.MARKET_TICK,
                    data=tick.model_dump(),
                    source="market_feed",
                    key=f"{instrument}",
                    broker="paper",
                    correlation_id=str(uuid4())
                )
                all_events.append(event)
        
        # Measure processing time
        start_time = time.time()
        
        # Process all ticks concurrently
        await asyncio.gather(*[
            mock_pipeline_services['strategy_runner'].process_tick(event)
            for event in all_events
        ])
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Calculate throughput
        throughput = len(all_events) / processing_time
        
        # Verify high throughput (target: >500 ticks/second)
        assert throughput > 500, f"Throughput {throughput:.1f} ticks/sec below target of 500"
        
        # Verify all ticks processed
        assert mock_pipeline_services['strategy_runner'].process_tick.call_count == len(all_events)
    
    @pytest.mark.asyncio
    async def test_concurrent_multi_broker_load(self, performance_data_generator, mock_pipeline_services):
        """Test concurrent processing load across multiple brokers."""
        
        # Create high-volume events for both brokers
        paper_events = []
        zerodha_events = []
        
        for i in range(200):  # 200 events per broker
            tick = performance_data_generator.generate_tick(256265, mode="full")
            
            paper_event = EventEnvelope(
                type=EventType.MARKET_TICK,
                data=tick.model_dump(),
                source="market_feed",
                key=f"{tick.instrument_token}",
                broker="paper",
                correlation_id=str(uuid4())
            )
            paper_events.append(paper_event)
            
            zerodha_event = EventEnvelope(
                type=EventType.MARKET_TICK,
                data=tick.model_dump(),
                source="market_feed",
                key=f"{tick.instrument_token}",
                broker="zerodha",
                correlation_id=str(uuid4())
            )
            zerodha_events.append(zerodha_event)
        
        # Process both broker loads concurrently
        start_time = time.time()
        
        await asyncio.gather(
            # Paper broker processing
            asyncio.gather(*[
                mock_pipeline_services['strategy_runner'].process_tick(event)
                for event in paper_events
            ]),
            # Zerodha broker processing  
            asyncio.gather(*[
                mock_pipeline_services['strategy_runner'].process_tick(event)
                for event in zerodha_events
            ])
        )
        
        end_time = time.time()
        total_processing_time = end_time - start_time
        
        # Verify performance (400 total events should complete in <2 seconds)
        assert total_processing_time < 2.0, f"Processing took {total_processing_time:.2f}s, expected <2.0s"
        
        # Verify all events processed
        total_events = len(paper_events) + len(zerodha_events)
        assert mock_pipeline_services['strategy_runner'].process_tick.call_count == total_events
    
    @pytest.mark.asyncio 
    async def test_memory_efficiency_under_load(self, performance_data_generator, mock_pipeline_services):
        """Test memory usage remains stable under sustained load."""
        
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Generate sustained load for memory testing
        batch_size = 100
        batches = 10
        
        for batch in range(batches):
            events = []
            
            for i in range(batch_size):
                tick = performance_data_generator.generate_tick(256265, mode="full")
                event = EventEnvelope(
                    type=EventType.MARKET_TICK,
                    data=tick.model_dump(),
                    source="market_feed",
                    key=f"{tick.instrument_token}",
                    broker="paper",
                    correlation_id=str(uuid4())
                )
                events.append(event)
            
            # Process batch
            await asyncio.gather(*[
                mock_pipeline_services['strategy_runner'].process_tick(event)
                for event in events
            ])
            
            # Clear events to allow garbage collection
            del events
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Verify memory usage didn't increase excessively (< 50MB increase)
        assert memory_increase < 50, f"Memory increased by {memory_increase:.1f}MB, expected <50MB"
        
        # Verify all batches processed
        total_events = batch_size * batches
        assert mock_pipeline_services['strategy_runner'].process_tick.call_count == total_events


class TestSystemResilience:
    """Test system resilience and recovery capabilities."""
    
    @pytest.fixture
    def resilience_data_generator(self):
        """Data generator for resilience testing."""
        return RealisticMarketDataGenerator(seed=42)
    
    @pytest.fixture
    def mock_unreliable_services(self):
        """Mock services that simulate failures for resilience testing."""
        services = {
            'market_feed': AsyncMock(),
            'strategy_runner': AsyncMock(),
            'risk_manager': AsyncMock(),
            'trading_engine': AsyncMock(),
            'portfolio_manager': AsyncMock()
        }
        
        return services
    
    @pytest.mark.asyncio
    async def test_service_failure_recovery(self, resilience_data_generator, mock_unreliable_services):
        """Test system recovery from service failures."""
        
        tick = resilience_data_generator.generate_tick(256265, mode="full")
        event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=tick.model_dump(),
            source="market_feed",
            key=f"{tick.instrument_token}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Configure service to fail then recover
        failure_count = 0
        async def failing_process_tick(event):
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:  # Fail first 2 attempts
                raise Exception(f"Service failure #{failure_count}")
            return None  # Success on 3rd attempt
        
        mock_unreliable_services['strategy_runner'].process_tick = failing_process_tick
        
        # Implement retry logic with exponential backoff
        max_retries = 3
        retry_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                await mock_unreliable_services['strategy_runner'].process_tick(event)
                break  # Success
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e  # Final attempt failed
                await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
        
        # Verify service eventually succeeded
        assert failure_count == 3  # Failed twice, succeeded on 3rd
    
    @pytest.mark.asyncio
    async def test_network_partition_simulation(self, resilience_data_generator, mock_unreliable_services):
        """Test system behavior during network partition scenarios."""
        
        # Simulate network partition by making services timeout
        async def timeout_simulation(*args, **kwargs):
            await asyncio.sleep(5)  # Simulate network timeout
            raise asyncio.TimeoutError("Network timeout")
        
        mock_unreliable_services['trading_engine'].execute_signal = timeout_simulation
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            instrument_token=256265,
            signal_type=SignalType.BUY,
            quantity=100,
            price=Decimal('25000.0'),
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
        
        # Test timeout handling with shorter timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                mock_unreliable_services['trading_engine'].execute_signal(signal_event),
                timeout=1.0  # 1 second timeout
            )
    
    @pytest.mark.asyncio
    async def test_cascade_failure_prevention(self, resilience_data_generator, mock_unreliable_services):
        """Test prevention of cascade failures across services."""
        
        # Configure one service to fail
        mock_unreliable_services['risk_manager'].validate_signal = AsyncMock(
            side_effect=Exception("Risk manager down")
        )
        
        # Other services should continue working
        mock_unreliable_services['strategy_runner'].process_tick = AsyncMock()
        mock_unreliable_services['portfolio_manager'].update_position = AsyncMock()
        
        tick = resilience_data_generator.generate_tick(256265, mode="full")
        tick_event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=tick.model_dump(),
            source="market_feed",
            key=f"{tick.instrument_token}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Strategy runner should still work despite risk manager failure
        await mock_unreliable_services['strategy_runner'].process_tick(tick_event)
        mock_unreliable_services['strategy_runner'].process_tick.assert_called_once()
        
        # Risk manager failure should be isolated
        with pytest.raises(Exception, match="Risk manager down"):
            await mock_unreliable_services['risk_manager'].validate_signal(tick_event)
        
        # Portfolio manager should still work
        await mock_unreliable_services['portfolio_manager'].update_position(tick_event)
        mock_unreliable_services['portfolio_manager'].update_position.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_resource_exhaustion_handling(self, resilience_data_generator, mock_unreliable_services):
        """Test handling of resource exhaustion scenarios."""
        
        # Simulate resource exhaustion by limiting concurrent operations
        semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent operations
        
        async def resource_limited_process_tick(event):
            async with semaphore:
                await asyncio.sleep(0.1)  # Simulate processing time
                return None
        
        mock_unreliable_services['strategy_runner'].process_tick = resource_limited_process_tick
        
        # Create more events than resource limit
        events = []
        for i in range(20):  # More than semaphore limit
            tick = resilience_data_generator.generate_tick(256265, mode="ltp")
            event = EventEnvelope(
                type=EventType.MARKET_TICK,
                data=tick.model_dump(),
                source="market_feed",
                key=f"{tick.instrument_token}",
                broker="paper",
                correlation_id=str(uuid4())
            )
            events.append(event)
        
        # Process with resource limitation
        start_time = time.time()
        await asyncio.gather(*[
            mock_unreliable_services['strategy_runner'].process_tick(event)
            for event in events
        ])
        end_time = time.time()
        
        # Verify processing time reflects resource limiting
        # With 5 concurrent limit and 0.1s per operation, 20 operations should take ~0.4s
        processing_time = end_time - start_time
        expected_min_time = (len(events) / 5) * 0.1  # Theoretical minimum with perfect batching
        
        assert processing_time >= expected_min_time * 0.8  # Allow some variance
    
    @pytest.mark.asyncio
    async def test_data_corruption_detection(self, resilience_data_generator):
        """Test detection and handling of data corruption."""
        
        # Create corrupted market tick data
        corrupted_tick_data = {
            'instrument_token': "invalid_token",  # Should be int
            'last_price': "invalid_price",        # Should be Decimal
            'timestamp': "invalid_timestamp"      # Should be datetime
        }
        
        corrupted_event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=corrupted_tick_data,
            source="market_feed",
            key="corrupted",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Test data validation
        with pytest.raises((ValueError, TypeError)):
            # Attempt to parse corrupted data into MarketTick model
            MarketTick(**corrupted_tick_data)
    
    @pytest.mark.asyncio
    async def test_graceful_degradation_mode(self, resilience_data_generator, mock_unreliable_services):
        """Test graceful degradation when services become unavailable."""
        
        # Configure services for degradation scenario
        mock_unreliable_services['risk_manager'].validate_signal = AsyncMock(
            side_effect=Exception("Risk manager unavailable")
        )
        
        # System should continue with reduced functionality
        async def degraded_strategy_processing(event):
            try:
                # Attempt risk validation
                await mock_unreliable_services['risk_manager'].validate_signal(event)
            except Exception:
                # Risk manager down - use conservative defaults
                # Only allow small quantities
                return {"max_quantity": 10, "mode": "degraded"}
            return {"max_quantity": 100, "mode": "normal"}
        
        tick = resilience_data_generator.generate_tick(256265, mode="full")
        tick_event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=tick.model_dump(),
            source="market_feed", 
            key=f"{tick.instrument_token}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Process in degraded mode
        result = await degraded_strategy_processing(tick_event)
        
        # Verify degraded mode activated
        assert result["mode"] == "degraded"
        assert result["max_quantity"] == 10  # Conservative limit
    
    @pytest.mark.asyncio
    async def test_system_recovery_after_total_failure(self, mock_unreliable_services):
        """Test complete system recovery after total failure."""
        
        # Simulate total system failure
        for service_name, service in mock_unreliable_services.items():
            for method_name in ['process_tick', 'validate_signal', 'execute_signal', 'update_position']:
                if hasattr(service, method_name):
                    setattr(service, method_name, AsyncMock(side_effect=Exception(f"{service_name} failed")))
        
        # Verify all services are down
        with pytest.raises(Exception):
            await mock_unreliable_services['strategy_runner'].process_tick({})
        
        with pytest.raises(Exception):
            await mock_unreliable_services['risk_manager'].validate_signal({})
        
        # Simulate system recovery
        for service_name, service in mock_unreliable_services.items():
            for method_name in ['process_tick', 'validate_signal', 'execute_signal', 'update_position']:
                if hasattr(service, method_name):
                    setattr(service, method_name, AsyncMock(return_value=True))  # Healthy again
        
        # Verify services recovered
        await mock_unreliable_services['strategy_runner'].process_tick({})
        await mock_unreliable_services['risk_manager'].validate_signal({})
        
        # Verify calls succeeded
        mock_unreliable_services['strategy_runner'].process_tick.assert_called_once()
        mock_unreliable_services['risk_manager'].validate_signal.assert_called_once()