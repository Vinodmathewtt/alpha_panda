"""
Integration tests for broker_namespace migration.
Tests that verify the application can start with the new multi-broker architecture.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from core.config.settings import Settings
from core.monitoring.pipeline_metrics import PipelineMetricsCollector
from core.streaming.clients import StreamProcessor, RedpandaSettings


class TestBrokerNamespaceMigration:
    """Test that critical services work with active_brokers instead of broker_namespace"""
    
    def test_settings_has_active_brokers_not_broker_namespace(self):
        """Verify Settings class has active_brokers and not broker_namespace"""
        settings = Settings()
        
        # Should have active_brokers
        assert hasattr(settings, 'active_brokers')
        assert isinstance(settings.active_brokers, list)
        assert len(settings.active_brokers) > 0
        
        # Should NOT have broker_namespace
        assert not hasattr(settings, 'broker_namespace')
    
    @pytest.mark.asyncio
    async def test_pipeline_metrics_collector_accepts_broker_namespace(self):
        """Test PipelineMetricsCollector works with broker_namespace parameter"""
        mock_redis = AsyncMock()
        settings = Settings()
        
        # Should work with explicit broker_namespace
        collector = PipelineMetricsCollector(mock_redis, settings, "paper")
        assert collector.broker_namespace == "paper"
        
        # Should use default "shared" when no broker_namespace provided
        collector_default = PipelineMetricsCollector(mock_redis, settings)
        assert collector_default.broker_namespace == "shared"
    
    @pytest.mark.asyncio  
    async def test_stream_processor_uses_active_brokers(self):
        """Test StreamProcessor uses active_brokers instead of broker_namespace"""
        settings = Settings()
        settings.active_brokers = ["paper", "zerodha"]
        
        redpanda_config = RedpandaSettings()
        mock_redis = AsyncMock()
        
        processor = StreamProcessor(
            name="test-processor",
            config=redpanda_config,
            consume_topics=["test.topic"],
            group_id="test-group",
            redis_client=mock_redis,
            settings=settings
        )
        
        # Should use active_brokers
        assert processor.active_brokers == ["paper", "zerodha"]
        assert processor.default_broker_namespace == "paper"
        
        # Should NOT have broker_namespace attribute
        assert not hasattr(processor, 'broker_namespace')
    
    def test_service_startup_integration(self):
        """Integration test that services can be instantiated without broker_namespace errors"""
        from services.market_feed.service import MarketFeedService
        from core.config.settings import Settings
        from unittest.mock import Mock
        
        settings = Settings()
        mock_redis = Mock()
        mock_auth = Mock()
        
        # This should not raise AttributeError about broker_namespace
        try:
            service = MarketFeedService(
                redis_client=mock_redis,
                settings=settings,
                auth_service=mock_auth
            )
            # If we get here, the migration fix worked
            assert service is not None
        except AttributeError as e:
            if "broker_namespace" in str(e):
                pytest.fail(f"broker_namespace migration not complete: {e}")
            else:
                # Other AttributeError is fine for this test
                pass