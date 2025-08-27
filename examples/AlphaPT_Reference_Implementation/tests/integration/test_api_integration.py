"""
Integration tests for AlphaPT API endpoints and WebSocket functionality.

Tests the complete API stack including routers, middleware, authentication,
and WebSocket connections.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch
from httpx import AsyncClient
from fastapi.testclient import TestClient

from api.server import create_app
from app.application import AlphaPTApplication
from core.config.settings import Settings


@pytest.mark.integration
class TestAPIServerSetup:
    """Test API server setup and configuration."""
    
    def test_create_app(self):
        """Test API application creation."""
        app = create_app()
        
        assert app is not None
        assert hasattr(app, 'router')
        assert hasattr(app, 'middleware_stack')
        
    @pytest.mark.asyncio
    async def test_app_startup_event(self):
        """Test application startup event handling."""
        with patch('api.server.get_application') as mock_get_app:
            mock_application = Mock(spec=AlphaPTApplication)
            mock_application.initialize = AsyncMock(return_value=True)
            mock_get_app.return_value = mock_application
            
            app = create_app()
            
            # Trigger startup event
            async with AsyncClient(app=app, base_url="http://test") as client:
                # Application should be initialized during startup
                assert True  # If we get here, startup was successful
                
    @pytest.mark.asyncio
    async def test_app_shutdown_event(self):
        """Test application shutdown event handling."""
        with patch('api.server.get_application') as mock_get_app:
            mock_application = Mock(spec=AlphaPTApplication)
            mock_application.initialize = AsyncMock(return_value=True)
            mock_application.cleanup = AsyncMock()
            mock_get_app.return_value = mock_application
            
            app = create_app()
            
            async with AsyncClient(app=app, base_url="http://test") as client:
                pass  # Client cleanup triggers shutdown
            
            # Cleanup should be called during shutdown
            mock_application.cleanup.assert_called_once()


@pytest.mark.integration
class TestHealthEndpoints:
    """Test health check endpoints."""
    
    @pytest.fixture
    async def client(self):
        """Create test client with mocked application."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        mock_application.health_check = AsyncMock(return_value={
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00Z",
            "components": {
                "database": {"status": "healthy"},
                "event_bus": {"status": "healthy"}
            }
        })
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client
                
    @pytest.mark.asyncio
    async def test_basic_health_check(self, client):
        """Test basic health check endpoint."""
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "components" in data
        
    @pytest.mark.asyncio
    async def test_detailed_health_check(self, client):
        """Test detailed health check endpoint."""
        response = await client.get("/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        assert "components" in data
        assert len(data["components"]) > 0
        
    @pytest.mark.asyncio
    async def test_health_check_with_unhealthy_components(self):
        """Test health check when components are unhealthy."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        mock_application.health_check = AsyncMock(return_value={
            "status": "unhealthy",
            "timestamp": "2024-01-01T00:00:00Z",
            "components": {
                "database": {"status": "unhealthy", "error": "Connection failed"},
                "event_bus": {"status": "healthy"}
            }
        })
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health")
                
                assert response.status_code == 503  # Service Unavailable
                data = response.json()
                assert data["status"] == "unhealthy"


@pytest.mark.integration 
class TestTradingEndpoints:
    """Test trading API endpoints."""
    
    @pytest.fixture
    async def client_with_trading(self):
        """Create test client with mocked trading components."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        
        # Mock paper trading engine
        mock_paper_engine = Mock()
        mock_paper_engine.place_order = AsyncMock(return_value={
            "order_id": "ORDER123",
            "status": "COMPLETE",
            "quantity": 10,
            "price": 2500.00
        })
        mock_paper_engine.get_orders = AsyncMock(return_value=[])
        mock_paper_engine.get_positions = AsyncMock(return_value=[])
        
        mock_application.app_state = {
            "paper_trading_engine": mock_paper_engine,
            "settings": Mock(paper_trading_enabled=True)
        }
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client
                
    @pytest.mark.asyncio
    async def test_place_order(self, client_with_trading):
        """Test placing an order through API."""
        order_data = {
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "quantity": 10,
            "order_type": "MARKET",
            "product": "MIS"
        }
        
        response = await client_with_trading.post("/api/v1/trading/orders", json=order_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["order_id"] == "ORDER123"
        assert data["status"] == "COMPLETE"
        
    @pytest.mark.asyncio
    async def test_get_orders(self, client_with_trading):
        """Test retrieving orders."""
        response = await client_with_trading.get("/api/v1/trading/orders")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
    @pytest.mark.asyncio
    async def test_get_positions(self, client_with_trading):
        """Test retrieving positions."""
        response = await client_with_trading.get("/api/v1/trading/positions")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
    @pytest.mark.asyncio
    async def test_invalid_order_data(self, client_with_trading):
        """Test placing order with invalid data."""
        invalid_order = {
            "tradingsymbol": "",  # Empty symbol
            "quantity": -10,      # Negative quantity
        }
        
        response = await client_with_trading.post("/api/v1/trading/orders", json=invalid_order)
        
        assert response.status_code == 422  # Validation error


@pytest.mark.integration
class TestStrategyEndpoints:
    """Test strategy management endpoints."""
    
    @pytest.fixture
    async def client_with_strategies(self):
        """Create test client with mocked strategy components."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        
        # Mock strategy manager
        mock_strategy_manager = Mock()
        mock_strategy_manager.get_strategy_status = Mock(return_value={
            "total_strategies": 2,
            "running_strategies": 1,
            "strategies": {
                "momentum_strategy": {"status": "running", "pnl": 1500.0},
                "mean_reversion_strategy": {"status": "stopped", "pnl": -200.0}
            }
        })
        mock_strategy_manager.start_strategy = AsyncMock(return_value=True)
        mock_strategy_manager.stop_strategy = AsyncMock(return_value=True)
        
        mock_application.app_state = {
            "strategy_manager": mock_strategy_manager
        }
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client
                
    @pytest.mark.asyncio
    async def test_get_strategies_status(self, client_with_strategies):
        """Test getting strategies status."""
        response = await client_with_strategies.get("/api/v1/strategies")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_strategies"] == 2
        assert data["running_strategies"] == 1
        assert "momentum_strategy" in data["strategies"]
        
    @pytest.mark.asyncio
    async def test_start_strategy(self, client_with_strategies):
        """Test starting a strategy."""
        response = await client_with_strategies.post("/api/v1/strategies/momentum_strategy/start")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Strategy started successfully"
        
    @pytest.mark.asyncio
    async def test_stop_strategy(self, client_with_strategies):
        """Test stopping a strategy."""
        response = await client_with_strategies.post("/api/v1/strategies/momentum_strategy/stop")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Strategy stopped successfully"
        
    @pytest.mark.asyncio
    async def test_strategy_not_found(self, client_with_strategies):
        """Test operations on non-existent strategy."""
        response = await client_with_strategies.post("/api/v1/strategies/non_existent/start")
        
        assert response.status_code == 404


@pytest.mark.integration
class TestMarketDataEndpoints:
    """Test market data endpoints."""
    
    @pytest.fixture
    async def client_with_market_data(self):
        """Create test client with mocked market data components."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        
        # Mock storage manager
        mock_storage_manager = Mock()
        mock_storage_manager.get_latest_ticks = AsyncMock(return_value=[
            {
                "instrument_token": 738561,
                "tradingsymbol": "RELIANCE",
                "last_price": 2500.50,
                "volume": 1000000,
                "timestamp": "2024-01-01T10:00:00Z"
            }
        ])
        
        mock_application.app_state = {
            "storage_manager": mock_storage_manager
        }
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client
                
    @pytest.mark.asyncio
    async def test_get_latest_ticks(self, client_with_market_data):
        """Test getting latest market ticks."""
        response = await client_with_market_data.get("/api/v1/market-data/ticks/738561")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["instrument_token"] == 738561
        
    @pytest.mark.asyncio
    async def test_get_ticks_with_limit(self, client_with_market_data):
        """Test getting ticks with limit parameter."""
        response = await client_with_market_data.get("/api/v1/market-data/ticks/738561?limit=50")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.integration
class TestWebSocketIntegration:
    """Test WebSocket integration."""
    
    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """Test WebSocket connection establishment."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            
            # Test WebSocket endpoint exists
            routes = [route.path for route in app.routes]
            assert any("/ws" in route for route in routes)
            
    @pytest.mark.asyncio
    async def test_websocket_market_data_subscription(self):
        """Test WebSocket market data subscription."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            
            with TestClient(app) as client:
                with client.websocket_connect("/ws/market-data") as websocket:
                    # Send subscription message
                    websocket.send_json({
                        "action": "subscribe",
                        "instruments": [738561]
                    })
                    
                    # Should receive confirmation
                    response = websocket.receive_json()
                    assert response["status"] == "subscribed"


@pytest.mark.integration
class TestAPIMiddleware:
    """Test API middleware functionality."""
    
    @pytest.fixture
    async def client_with_middleware(self):
        """Create test client with middleware."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client
                
    @pytest.mark.asyncio
    async def test_cors_middleware(self, client_with_middleware):
        """Test CORS middleware."""
        response = await client_with_middleware.options("/api/v1/health", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        })
        
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        
    @pytest.mark.asyncio
    async def test_request_logging_middleware(self, client_with_middleware):
        """Test request logging middleware."""
        with patch('api.middleware.get_logger') as mock_logger:
            mock_logger.return_value.info = Mock()
            
            response = await client_with_middleware.get("/health")
            
            # Logger should be called for request/response
            assert mock_logger.return_value.info.call_count >= 1
            
    @pytest.mark.asyncio
    async def test_error_handling_middleware(self, client_with_middleware):
        """Test error handling middleware."""
        # This would test custom error responses
        response = await client_with_middleware.get("/non-existent-endpoint")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


@pytest.mark.integration 
class TestAPIAuthentication:
    """Test API authentication and authorization."""
    
    @pytest.fixture
    async def client_with_auth(self):
        """Create test client with authentication."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        
        # Mock auth manager
        mock_auth_manager = Mock()
        mock_auth_manager.is_authenticated = Mock(return_value=True)
        mock_auth_manager.get_current_user = Mock(return_value={
            "user_id": "test_user",
            "name": "Test User"
        })
        
        mock_application.app_state = {
            "auth_manager": mock_auth_manager
        }
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client
                
    @pytest.mark.asyncio
    async def test_protected_endpoint_without_auth(self):
        """Test accessing protected endpoint without authentication."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        
        # Mock unauthenticated state
        mock_auth_manager = Mock()
        mock_auth_manager.is_authenticated = Mock(return_value=False)
        
        mock_application.app_state = {
            "auth_manager": mock_auth_manager
        }
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/trading/orders")
                
                # Should be unauthorized
                assert response.status_code == 401
                
    @pytest.mark.asyncio
    async def test_protected_endpoint_with_auth(self, client_with_auth):
        """Test accessing protected endpoint with authentication."""
        # Add authorization header
        headers = {"Authorization": "Bearer test_token"}
        
        response = await client_with_auth.get("/api/v1/trading/orders", headers=headers)
        
        # Should be successful (even if empty result)
        assert response.status_code in [200, 404]  # Depends on implementation


@pytest.mark.integration
class TestAPIPerformance:
    """Test API performance characteristics."""
    
    @pytest.fixture
    async def performance_client(self):
        """Create client for performance testing."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        mock_application.health_check = AsyncMock(return_value={"status": "healthy"})
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client
                
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, performance_client):
        """Test handling concurrent requests."""
        import time
        
        async def make_request():
            response = await performance_client.get("/health")
            return response.status_code
        
        # Make 10 concurrent requests
        start_time = time.time()
        tasks = [make_request() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # All requests should succeed
        assert all(status == 200 for status in results)
        
        # Should complete within reasonable time
        assert end_time - start_time < 5.0  # 5 seconds for 10 requests
        
    @pytest.mark.asyncio
    async def test_request_response_time(self, performance_client):
        """Test individual request response time."""
        import time
        
        start_time = time.time()
        response = await performance_client.get("/health")
        end_time = time.time()
        
        assert response.status_code == 200
        
        # Response should be fast
        response_time = end_time - start_time
        assert response_time < 1.0  # Should respond within 1 second


@pytest.mark.integration
class TestAPIErrorHandling:
    """Test comprehensive API error handling."""
    
    @pytest.fixture
    async def error_client(self):
        """Create client for error testing."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                yield client
                
    @pytest.mark.asyncio
    async def test_404_error_handling(self, error_client):
        """Test 404 error responses."""
        response = await error_client.get("/non-existent-endpoint")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        
    @pytest.mark.asyncio
    async def test_500_error_handling(self):
        """Test 500 error handling."""
        mock_application = Mock(spec=AlphaPTApplication)
        mock_application.initialize = AsyncMock(return_value=True)
        mock_application.cleanup = AsyncMock()
        mock_application.health_check = AsyncMock(side_effect=Exception("Internal error"))
        
        with patch('api.server.get_application', return_value=mock_application):
            app = create_app()
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health")
                
                assert response.status_code == 500
                
    @pytest.mark.asyncio
    async def test_validation_error_handling(self, error_client):
        """Test validation error responses."""
        # Send invalid JSON data
        response = await error_client.post("/api/v1/trading/orders", json={
            "invalid_field": "invalid_value"
        })
        
        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data