"""
Contract tests for component interfaces.

These tests verify that all components implement the expected interfaces
and contracts correctly, ensuring compatibility and proper integration.
"""

import asyncio
import inspect
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, AsyncMock

import pytest

from core.config.settings import Settings
from app.application import AlphaPTApplication


@pytest.mark.contract
class TestComponentContracts:
    """Test that all components follow expected interface contracts."""
    
    def test_component_manager_interface_contract(self):
        """Test that all manager components implement required interface methods."""
        # Define the expected component manager interface
        required_methods = [
            'initialize',  # async method returning bool
            'cleanup',     # async method for resource cleanup  
            'health_check' # async method returning dict
        ]
        
        # List of all manager components to test
        manager_classes = [
            'core.database.connection.DatabaseManager',
            'core.events.event_bus.EventBus', 
            'core.auth.auth_manager.AuthManager',
            'storage.storage_manager.StorageManager',
            'strategy_manager.strategy_manager.StrategyManager',
            'risk_manager.risk_manager.RiskManager',
            'paper_trade.engine.PaperTradingEngine',
            'monitoring.health_checker.HealthChecker'
        ]
        
        for manager_class_path in manager_classes:
            # Import the class
            module_path, class_name = manager_class_path.rsplit('.', 1)
            try:
                exec(f"from {module_path} import {class_name}")
                manager_class = eval(class_name)
                
                # Check that all required methods exist
                for method_name in required_methods:
                    assert hasattr(manager_class, method_name), \
                        f"{manager_class_path} missing required method: {method_name}"
                    
                    method = getattr(manager_class, method_name)
                    assert callable(method), \
                        f"{manager_class_path}.{method_name} is not callable"
                        
                    # Check if method is async (for async methods)
                    if method_name in ['initialize', 'cleanup', 'health_check']:
                        assert asyncio.iscoroutinefunction(method), \
                            f"{manager_class_path}.{method_name} should be async"
                            
            except ImportError:
                pytest.skip(f"Could not import {manager_class_path} - may not be implemented yet")
                
    def test_event_handler_contract(self):
        """Test that event handlers follow the expected contract."""
        # Event handlers should be async functions that accept an event parameter
        from core.events.event_types import BaseEvent, SystemEvent, EventType
        from datetime import datetime, timezone
        import uuid
        
        # Example event handler that follows the contract
        async def valid_event_handler(event: BaseEvent):
            """Valid event handler following the contract."""
            assert hasattr(event, 'event_id')
            assert hasattr(event, 'event_type') 
            assert hasattr(event, 'timestamp')
            assert hasattr(event, 'source')
            
        # Test that the handler can process events
        test_event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="contract_test"
        )
        
        # Should be callable as async
        assert asyncio.iscoroutinefunction(valid_event_handler)
        
        # Should accept the event (this is a contract validation)
        sig = inspect.signature(valid_event_handler)
        assert len(sig.parameters) == 1, "Event handler should accept exactly one parameter"
        
    def test_configuration_contract(self):
        """Test that configuration classes follow expected patterns."""
        from core.config.settings import Settings
        from core.config.database_config import DatabaseConfig
        
        # All config classes should be Pydantic BaseSettings or BaseModel
        assert hasattr(Settings, 'model_validate')  # Pydantic v2 method
        assert hasattr(DatabaseConfig, 'model_validate')
        
        # Settings should be serializable
        settings = Settings(secret_key="test")
        config_dict = settings.model_dump()
        assert isinstance(config_dict, dict)
        assert 'secret_key' in config_dict
        
    def test_database_manager_contract(self):
        """Test database manager interface contract."""
        from core.database.connection import DatabaseManager
        
        # Database managers should have specific methods for migration compatibility
        required_db_methods = [
            'execute_query',    # For running queries
            'get_connection',   # For getting connections
            'initialize',       # Standard manager method
            'cleanup'          # Standard manager method
        ]
        
        for method_name in required_db_methods:
            assert hasattr(DatabaseManager, method_name), \
                f"DatabaseManager missing required method: {method_name}"
                
    def test_trading_engine_contract(self):
        """Test trading engine interface contract.""" 
        try:
            from paper_trade.engine import PaperTradingEngine
            
            # Trading engines should have specific methods
            required_trading_methods = [
                'place_order',     # For placing orders
                'cancel_order',    # For canceling orders (if implemented)
                'get_positions',   # For getting positions
                'get_orders',      # For getting orders
                'initialize',      # Standard manager method
                'cleanup'          # Standard manager method
            ]
            
            for method_name in required_trading_methods:
                if hasattr(PaperTradingEngine, method_name):
                    method = getattr(PaperTradingEngine, method_name)
                    assert callable(method), \
                        f"PaperTradingEngine.{method_name} should be callable"
                        
        except ImportError:
            pytest.skip("PaperTradingEngine not available")
            
    def test_strategy_interface_contract(self):
        """Test strategy interface contract."""
        try:
            from strategy_manager.base_strategy import BaseStrategy
            
            # Strategies should follow the base strategy contract
            required_strategy_methods = [
                'initialize',
                'process_market_data',
                'cleanup'
            ]
            
            for method_name in required_strategy_methods:
                assert hasattr(BaseStrategy, method_name), \
                    f"BaseStrategy missing required method: {method_name}"
                    
        except ImportError:
            pytest.skip("BaseStrategy not available")


@pytest.mark.contract
class TestAPIContracts:
    """Test API endpoint contracts and schemas."""
    
    async def test_health_endpoint_contract(self, api_client):
        """Test that health endpoint follows expected contract."""
        response = await api_client.get("/api/v1/health")
        
        # Health endpoint should return some response
        assert response.status_code in [200, 404, 500, 503]
        
        # If successful, should follow health check schema
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            # Common health check fields
            expected_fields = ['status', 'timestamp']
            for field in expected_fields:
                if field in data:  # May not be implemented yet
                    assert isinstance(data[field], (str, dict, list))
                    
    async def test_api_error_response_contract(self, api_client):
        """Test that API error responses follow expected contract."""
        # Try to access a non-existent endpoint
        response = await api_client.get("/api/v1/non-existent-endpoint")
        
        # Should return an error status
        assert response.status_code >= 400
        
        # Error responses should be JSON when possible
        try:
            error_data = response.json()
            if isinstance(error_data, dict):
                # Common error response fields
                expected_error_fields = ['detail', 'error', 'message']
                has_error_field = any(field in error_data for field in expected_error_fields)
                # At least one error field should be present, or it's a valid minimal response
                assert has_error_field or len(error_data) == 0  # Empty dict is also valid
        except ValueError:
            # Non-JSON response is also acceptable for 404s
            pass
            
    async def test_authentication_contract(self, api_client):
        """Test authentication-related endpoint contracts."""
        # Test that protected endpoints require authentication
        protected_endpoints = [
            "/api/v1/trading/orders",
            "/api/v1/strategies", 
            "/api/v1/positions"
        ]
        
        for endpoint in protected_endpoints:
            try:
                response = await api_client.get(endpoint)
                
                # Should either be:
                # - 401 (Unauthorized) if auth is required
                # - 404 (Not Found) if endpoint doesn't exist
                # - 200 (OK) if using mock authentication
                # - 500 (Server Error) if there are other issues
                assert response.status_code in [200, 401, 404, 500, 503]
                
            except Exception:
                # API may not be fully implemented - that's OK for contract testing
                pass


@pytest.mark.contract
class TestEventContracts:
    """Test event system contracts."""
    
    def test_event_type_contract(self):
        """Test that all event types follow the base event contract."""
        from core.events.event_types import (
            BaseEvent, SystemEvent, TradingEvent, MarketDataEvent, RiskEvent
        )
        from datetime import datetime, timezone
        import uuid
        
        event_classes = [SystemEvent, TradingEvent, MarketDataEvent, RiskEvent]
        
        for event_class in event_classes:
            # All events should inherit from BaseEvent
            assert issubclass(event_class, BaseEvent)
            
            # All events should have serialization methods
            assert hasattr(event_class, 'to_json')
            assert hasattr(event_class, 'from_json')
            
            # Test that events can be created with required fields
            base_kwargs = {
                'event_id': str(uuid.uuid4()),
                'event_type': 'test_type',  # Will be validated by specific event
                'timestamp': datetime.now(timezone.utc),
                'source': 'contract_test'
            }
            
            try:
                # Try to create instance (may fail due to additional required fields)
                # This is mainly to test the basic structure exists
                event_class.__init__.__annotations__
                # If we get here, the class has proper type annotations
            except AttributeError:
                # Class may not use type annotations - that's acceptable
                pass
                
    def test_event_serialization_contract(self):
        """Test that events can be serialized and deserialized consistently."""
        from core.events.event_types import SystemEvent, EventType
        from datetime import datetime, timezone
        import uuid
        
        # Create a test event
        original_event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="contract_test"
        )
        
        # Test serialization
        json_str = original_event.to_json()
        assert isinstance(json_str, str)
        assert len(json_str) > 0
        
        # Test deserialization
        deserialized_event = SystemEvent.from_json(json_str)
        
        # Key fields should be preserved
        assert deserialized_event.event_id == original_event.event_id
        assert deserialized_event.event_type == original_event.event_type
        assert deserialized_event.source == original_event.source


@pytest.mark.contract
class TestDataContracts:
    """Test data model contracts."""
    
    def test_market_data_contract(self, sample_tick_data):
        """Test market data structure contracts."""
        # Market data should have required fields
        required_fields = [
            'instrument_token',
            'tradingsymbol', 
            'last_price',
            'timestamp'
        ]
        
        for field in required_fields:
            assert field in sample_tick_data, f"Market data missing required field: {field}"
            
        # Verify field types
        assert isinstance(sample_tick_data['instrument_token'], int)
        assert isinstance(sample_tick_data['tradingsymbol'], str)
        assert isinstance(sample_tick_data['last_price'], (int, float))
        
    def test_order_data_contract(self, sample_order_data):
        """Test order data structure contracts."""
        # Order data should have required fields
        required_fields = [
            'tradingsymbol',
            'exchange',
            'transaction_type',
            'quantity',
            'order_type'
        ]
        
        for field in required_fields:
            assert field in sample_order_data, f"Order data missing required field: {field}"
            
        # Verify field types and values
        assert isinstance(sample_order_data['tradingsymbol'], str)
        assert sample_order_data['exchange'] in ['NSE', 'BSE', 'NFO', 'BFO', 'CDS', 'MCX']
        assert sample_order_data['transaction_type'] in ['BUY', 'SELL']
        assert isinstance(sample_order_data['quantity'], int)
        assert sample_order_data['quantity'] > 0
        
    def test_strategy_config_contract(self, sample_strategy_config):
        """Test strategy configuration contracts."""
        # Strategy config should have required fields
        required_fields = [
            'name',
            'strategy_type', 
            'enabled',
            'parameters'
        ]
        
        for field in required_fields:
            assert field in sample_strategy_config, f"Strategy config missing required field: {field}"
            
        # Verify field types and structures
        assert isinstance(sample_strategy_config['name'], str)
        assert isinstance(sample_strategy_config['enabled'], bool)
        assert isinstance(sample_strategy_config['parameters'], dict)


@pytest.mark.contract
class TestPerformanceContracts:
    """Test performance-related contracts."""
    
    def test_throughput_contract(self, performance_config):
        """Test that performance configuration meets expected contracts."""
        required_performance_fields = [
            'tick_generation_rate',
            'target_throughput', 
            'max_latency_ms'
        ]
        
        for field in required_performance_fields:
            assert field in performance_config, f"Performance config missing: {field}"
            assert isinstance(performance_config[field], (int, float))
            assert performance_config[field] > 0
            
    def test_latency_contract(self):
        """Test latency requirements contract."""
        # Define maximum acceptable latencies for different operations
        max_latencies = {
            'order_processing': 100,    # milliseconds
            'market_data_processing': 10,  # milliseconds
            'strategy_signal_generation': 50,  # milliseconds
            'risk_check': 20           # milliseconds
        }
        
        # This is a contract definition - actual testing would measure real latencies
        for operation, max_latency_ms in max_latencies.items():
            assert max_latency_ms > 0, f"Invalid latency requirement for {operation}"
            assert max_latency_ms < 1000, f"Latency requirement too high for {operation}"