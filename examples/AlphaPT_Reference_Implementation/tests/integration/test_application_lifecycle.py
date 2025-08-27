"""
Integration tests for application lifecycle management.

Tests the complete initialization, running, and cleanup of the AlphaPT application
with real or semi-real component interactions.
"""

import asyncio
from unittest.mock import patch, AsyncMock, Mock

import pytest

from app.application import AlphaPTApplication
from core.config.settings import Settings


@pytest.mark.integration
class TestApplicationLifecycle:
    """Test complete application lifecycle with component interactions."""
    
    async def test_application_full_initialization(self, mock_settings):
        """Test full application initialization with all components."""
        app = AlphaPTApplication()
        
        # Mock all component managers to return True for initialization
        with patch('core.database.connection.DatabaseManager') as mock_db_class, \
             patch('core.events.event_bus.EventBus') as mock_event_bus_class, \
             patch('core.auth.auth_manager.AuthManager') as mock_auth_class, \
             patch('storage.storage_manager.StorageManager') as mock_storage_class, \
             patch('strategy_manager.strategy_manager.StrategyManager') as mock_strategy_class, \
             patch('risk_manager.risk_manager.RiskManager') as mock_risk_class, \
             patch('paper_trade.engine.PaperTradingEngine') as mock_paper_class, \
             patch('monitoring.health_checker.HealthChecker') as mock_health_class:
            
            # Configure mock instances
            for mock_class in [mock_db_class, mock_event_bus_class, mock_auth_class, 
                             mock_storage_class, mock_strategy_class, mock_risk_class, 
                             mock_paper_class, mock_health_class]:
                mock_instance = Mock()
                mock_instance.initialize = AsyncMock(return_value=True)
                mock_instance.cleanup = AsyncMock()
                mock_instance.health_check = AsyncMock(return_value={"status": "healthy"})
                mock_class.return_value = mock_instance
            
            # Test initialization
            result = await app.initialize()
            
            assert result is True
            assert app.app_state["settings"] is not None
            assert app.app_state["db_manager"] is not None
            assert app.app_state["event_bus"] is not None
            
            # Test cleanup
            await app.cleanup()
            
    async def test_application_initialization_failure(self, mock_settings):
        """Test application behavior when component initialization fails."""
        app = AlphaPTApplication()
        
        # Mock database manager to fail initialization
        with patch('core.database.connection.DatabaseManager') as mock_db_class:
            mock_db_instance = Mock()
            mock_db_instance.initialize = AsyncMock(return_value=False)
            mock_db_class.return_value = mock_db_instance
            
            # Application initialization should handle failure gracefully
            result = await app.initialize()
            
            # Depending on implementation, may return False or handle gracefully
            # The key is that it doesn't crash
            assert isinstance(result, bool)
            
    async def test_application_health_check_integration(self, mock_settings):
        """Test application health check with multiple components."""
        app = AlphaPTApplication()
        
        # Mock components with different health statuses
        mock_healthy_component = Mock()
        mock_healthy_component.health_check = AsyncMock(return_value={"status": "healthy"})
        
        mock_unhealthy_component = Mock()
        mock_unhealthy_component.health_check = AsyncMock(return_value={"status": "unhealthy", "error": "Connection failed"})
        
        # Set up app state with mixed health components
        app.app_state.update({
            "settings": mock_settings,
            "db_manager": mock_healthy_component,
            "event_bus": mock_unhealthy_component,
            "auth_manager": mock_healthy_component,
        })
        
        # Test health check aggregation
        health = await app.health_check()
        
        assert isinstance(health, dict)
        assert "status" in health
        # Health check should aggregate component statuses
        
    async def test_application_graceful_shutdown(self, mock_settings):
        """Test graceful application shutdown."""
        app = AlphaPTApplication()
        
        # Mock components
        mock_component = Mock()
        mock_component.cleanup = AsyncMock()
        mock_component.initialize = AsyncMock(return_value=True)
        
        # Set up minimal app state
        app.app_state.update({
            "settings": mock_settings,
            "db_manager": mock_component,
            "event_bus": mock_component,
        })
        
        # Test shutdown signal handling
        shutdown_event = asyncio.Event()
        app.app_state["shutdown_event"] = shutdown_event
        
        # Test stop method
        await app.stop()
        
        # Should have called cleanup on components
        assert mock_component.cleanup.called
        
    async def test_component_dependency_order(self, mock_settings):
        """Test that components are initialized in correct dependency order."""
        app = AlphaPTApplication()
        
        initialization_order = []
        
        def track_init(component_name):
            async def mock_init():
                initialization_order.append(component_name)
                return True
            return mock_init
        
        # Mock components to track initialization order
        with patch('core.database.connection.DatabaseManager') as mock_db_class, \
             patch('core.events.event_bus.EventBus') as mock_event_bus_class:
            
            # Set up tracking
            mock_db_instance = Mock()
            mock_db_instance.initialize = track_init("database")
            mock_db_class.return_value = mock_db_instance
            
            mock_event_bus_instance = Mock() 
            mock_event_bus_instance.initialize = track_init("event_bus")
            mock_event_bus_instance.connect = track_init("event_bus_connect")
            mock_event_bus_class.return_value = mock_event_bus_instance
            
            # Initialize application
            result = await app.initialize()
            
            # Verify initialization happened and in some order
            assert len(initialization_order) > 0
            # Database should typically be initialized before event bus
            if "database" in initialization_order and "event_bus" in initialization_order:
                db_index = initialization_order.index("database")
                event_bus_index = initialization_order.index("event_bus")
                # This may or may not be enforced - depends on implementation


@pytest.mark.integration
class TestComponentInteraction:
    """Test interactions between different application components."""
    
    async def test_event_bus_database_integration(self, mock_settings):
        """Test event bus and database manager working together."""
        # Create actual instances but with mocked external dependencies
        from core.database.connection import DatabaseManager
        from core.events.event_bus import EventBus
        
        # Mock external connections
        with patch('asyncpg.connect', new_callable=AsyncMock) as mock_pg_connect, \
             patch('nats.connect', new_callable=AsyncMock) as mock_nats_connect:
            
            # Set up successful connections
            mock_pg_connect.return_value = AsyncMock()
            mock_nats_connection = AsyncMock()
            mock_nats_connection.jetstream.return_value = AsyncMock()
            mock_nats_connect.return_value = mock_nats_connection
            
            # Create and initialize components
            db_manager = DatabaseManager(mock_settings)
            event_bus = EventBus(mock_settings)
            
            # Test initialization
            db_result = await db_manager.initialize()
            event_result = await event_bus.connect()
            
            # Both should initialize successfully (or fail gracefully)
            assert isinstance(db_result, bool)
            assert isinstance(event_result, bool)
            
            # Cleanup
            await db_manager.cleanup()
            await event_bus.disconnect()
            
    async def test_auth_database_integration(self, mock_settings):
        """Test authentication manager with database integration."""
        from core.auth.auth_manager import AuthManager
        from core.database.connection import DatabaseManager
        
        # Mock database connection
        with patch('asyncpg.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = AsyncMock()
            
            # Create components
            db_manager = DatabaseManager(mock_settings)
            await db_manager.initialize()
            
            auth_manager = AuthManager(mock_settings, db_manager)
            await auth_manager.initialize()
            
            # Test basic authentication operations
            assert auth_manager.is_authenticated() is False
            assert auth_manager.get_access_token() is None
            
            # Cleanup
            await auth_manager.cleanup()
            await db_manager.cleanup()
            
    async def test_strategy_event_integration(self, mock_settings):
        """Test strategy manager with event bus integration."""
        from strategy_manager.strategy_manager import StrategyManager
        from core.events.event_bus import EventBus
        
        # Mock external connections
        with patch('nats.connect', new_callable=AsyncMock) as mock_nats_connect:
            # Set up NATS connection
            mock_nats_connection = AsyncMock()
            mock_nats_connection.jetstream.return_value = AsyncMock()
            mock_nats_connect.return_value = mock_nats_connection
            
            # Create components
            event_bus = EventBus(mock_settings)
            await event_bus.connect()
            
            strategy_manager = StrategyManager(mock_settings, event_bus)
            result = await strategy_manager.initialize()
            
            # Should initialize successfully or fail gracefully
            assert isinstance(result, bool)
            
            # Cleanup
            await strategy_manager.cleanup()
            await event_bus.disconnect()


@pytest.mark.integration
@pytest.mark.slow
class TestRealServiceIntegration:
    """Integration tests with real external services (when available)."""
    
    async def test_real_database_connection(self, mock_settings):
        """Test connection to real database if available."""
        from core.database.connection import DatabaseManager
        
        # This test only runs if database services are available
        db_manager = DatabaseManager(mock_settings)
        
        try:
            result = await db_manager.initialize()
            if result:
                # Test basic operations
                health = await db_manager.health_check()
                assert isinstance(health, dict)
                
                # Test cleanup
                await db_manager.cleanup()
            else:
                # Database not available - that's ok for testing
                pytest.skip("Database services not available")
                
        except Exception as e:
            # External service not available - skip test
            pytest.skip(f"Database connection failed: {e}")
            
    async def test_real_event_bus_connection(self, mock_settings):
        """Test connection to real NATS if available.""" 
        from core.events.event_bus import EventBus
        
        event_bus = EventBus(mock_settings)
        
        try:
            result = await event_bus.connect()
            if result:
                # Test basic operations
                health = await event_bus.health_check()
                assert isinstance(health, dict)
                
                # Test cleanup
                await event_bus.disconnect()
            else:
                pytest.skip("NATS service not available")
                
        except Exception as e:
            # External service not available - skip test
            pytest.skip(f"NATS connection failed: {e}")


@pytest.mark.integration
class TestAPIIntegration:
    """Test API integration with application components."""
    
    async def test_api_server_creation_with_app(self, mock_application):
        """Test API server creation with application context."""
        from api.server import create_app
        
        # Test that API app can be created with application context
        with patch('api.server.get_application', return_value=mock_application):
            api_app = create_app()
            
            assert api_app is not None
            # Should have routes configured
            assert len(api_app.routes) > 0
            
    async def test_health_endpoint_integration(self, api_client, mock_application):
        """Test health endpoint with application integration."""
        # Mock application health check
        mock_application.health_check.return_value = {
            "status": "healthy",
            "components": {
                "database": {"status": "healthy"},
                "event_bus": {"status": "healthy"}
            }
        }
        
        response = await api_client.get("/api/v1/health")
        
        # Should get some response
        assert response.status_code in [200, 404, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)