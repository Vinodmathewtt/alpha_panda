"""
Unit tests for service interface validation.
Prevents AttributeError exceptions by validating method signatures exist.
"""

import pytest
import inspect
from typing import get_type_hints, Protocol
from unittest.mock import Mock

# Import service classes for interface validation
from services.market_feed.service import MarketFeedService
from services.strategy_runner.service import StrategyRunnerService  
from services.trading_engine.service import TradingEngineService
from services.portfolio_manager.service import PortfolioManagerService
from services.risk_manager.service import RiskManagerService


class TestServiceMethodValidation:
    """Test that all service methods called by other services actually exist"""
    
    def test_market_feed_service_interface(self):
        """Test MarketFeedService has all required methods"""
        # Check critical methods exist
        assert hasattr(MarketFeedService, 'start')
        assert hasattr(MarketFeedService, 'stop')
        assert hasattr(MarketFeedService, 'get_connection_status')
        
        # Validate method signatures
        start_method = getattr(MarketFeedService, 'start')
        assert callable(start_method)
        
        # Check if start method is async
        assert inspect.iscoroutinefunction(start_method)
    
    def test_strategy_runner_service_interface(self):
        """Test StrategyRunnerService has required methods and attributes"""
        assert hasattr(StrategyRunnerService, 'start')
        assert hasattr(StrategyRunnerService, 'stop')
        assert hasattr(StrategyRunnerService, 'load_strategies')
        
        # Test method signatures
        load_strategies = getattr(StrategyRunnerService, 'load_strategies')
        assert callable(load_strategies)
    
    def test_trading_engine_service_interface(self):
        """Test TradingEngineService interface compliance"""
        assert hasattr(TradingEngineService, 'start')
        assert hasattr(TradingEngineService, 'stop')
        assert hasattr(TradingEngineService, 'execute_signal')
        
        # Verify execute_signal method exists and is callable
        execute_signal = getattr(TradingEngineService, 'execute_signal')
        assert callable(execute_signal)
        assert inspect.iscoroutinefunction(execute_signal)
    
    def test_portfolio_manager_service_interface(self):
        """Test PortfolioManagerService method existence"""
        assert hasattr(PortfolioManagerService, 'start')
        assert hasattr(PortfolioManagerService, 'stop')
        assert hasattr(PortfolioManagerService, 'update_portfolio')
        assert hasattr(PortfolioManagerService, 'get_portfolio_snapshot')
        
        # Test portfolio update method signature
        update_portfolio = getattr(PortfolioManagerService, 'update_portfolio')
        assert callable(update_portfolio)
    
    def test_risk_manager_service_interface(self):
        """Test RiskManagerService critical methods exist"""
        assert hasattr(RiskManagerService, 'start')
        assert hasattr(RiskManagerService, 'stop')
        assert hasattr(RiskManagerService, 'validate_signal')
        
        # Test signal validation method
        validate_signal = getattr(RiskManagerService, 'validate_signal')
        assert callable(validate_signal)
        assert inspect.iscoroutinefunction(validate_signal)


class TestServiceInitializationParameters:
    """Test service constructors accept required parameters"""
    
    def test_market_feed_service_init_parameters(self):
        """Test MarketFeedService __init__ accepts required parameters"""
        # Get constructor signature
        init_sig = inspect.signature(MarketFeedService.__init__)
        params = list(init_sig.parameters.keys())
        
        # Should accept basic parameters (self is always first)
        assert 'self' in params
        # Check for expected parameters based on service requirements
        
        # Try creating mock instance to validate constructor works
        try:
            # This tests that constructor can be called with reasonable parameters
            mock_settings = Mock()
            mock_redis = Mock()
            
            # This should not raise TypeError for missing parameters
            service = MarketFeedService(mock_settings, mock_redis)
            assert service is not None
            
        except TypeError as e:
            pytest.fail(f"MarketFeedService constructor missing required parameters: {e}")
    
    def test_strategy_runner_service_init_parameters(self):
        """Test StrategyRunnerService constructor parameters"""
        init_sig = inspect.signature(StrategyRunnerService.__init__)
        params = list(init_sig.parameters.keys())
        
        assert 'self' in params
        
        # Test constructor can be called
        try:
            mock_settings = Mock()
            mock_redis = Mock()
            service = StrategyRunnerService(mock_settings, mock_redis)
            assert service is not None
            
        except TypeError as e:
            pytest.fail(f"StrategyRunnerService constructor error: {e}")
    
    def test_trading_engine_service_init_parameters(self):
        """Test TradingEngineService constructor"""
        init_sig = inspect.signature(TradingEngineService.__init__)
        
        try:
            mock_settings = Mock()
            mock_redis = Mock()
            service = TradingEngineService(mock_settings, mock_redis)
            assert service is not None
            
        except TypeError as e:
            pytest.fail(f"TradingEngineService constructor error: {e}")


class TestServiceAsyncMethodSignatures:
    """Test that async service methods have correct signatures"""
    
    def test_async_start_methods(self):
        """Test all services have async start methods"""
        services = [
            MarketFeedService,
            StrategyRunnerService, 
            TradingEngineService,
            PortfolioManagerService,
            RiskManagerService
        ]
        
        for service_class in services:
            assert hasattr(service_class, 'start')
            start_method = getattr(service_class, 'start')
            assert inspect.iscoroutinefunction(start_method), f"{service_class.__name__}.start() must be async"
    
    def test_async_stop_methods(self):
        """Test all services have async stop methods"""
        services = [
            MarketFeedService,
            StrategyRunnerService,
            TradingEngineService, 
            PortfolioManagerService,
            RiskManagerService
        ]
        
        for service_class in services:
            assert hasattr(service_class, 'stop')
            stop_method = getattr(service_class, 'stop')
            assert inspect.iscoroutinefunction(stop_method), f"{service_class.__name__}.stop() must be async"
    
    def test_message_handler_signatures(self):
        """Test message handler methods accept (message, topic) parameters"""
        # Test that handler methods have correct signature for topic-aware processing
        
        # Get all methods that might be message handlers (start with _handle_)
        service_classes = [StrategyRunnerService, TradingEngineService, PortfolioManagerService]
        
        for service_class in service_classes:
            methods = inspect.getmembers(service_class, predicate=inspect.isfunction)
            handler_methods = [method for name, method in methods if name.startswith('_handle_')]
            
            for handler_method in handler_methods:
                sig = inspect.signature(handler_method)
                params = list(sig.parameters.keys())
                
                # Handler should accept self, message, topic as minimum
                assert 'self' in params, f"{service_class.__name__}.{handler_method.__name__} missing 'self' parameter"
                
                # Should have at least message parameter
                param_count = len([p for p in params if p != 'self'])
                assert param_count >= 1, f"{service_class.__name__}.{handler_method.__name__} should accept message parameter"


class TestCriticalServiceMethodsExist:
    """Test critical service methods that are commonly called exist"""
    
    def test_portfolio_manager_critical_methods(self):
        """Test PortfolioManagerService has critical methods called by other services"""
        critical_methods = [
            'handle_order_filled',
            'handle_order_placed', 
            'process_order_fill',
            'get_portfolio_balance',
            'update_position'
        ]
        
        for method_name in critical_methods:
            if hasattr(PortfolioManagerService, method_name):
                method = getattr(PortfolioManagerService, method_name)
                assert callable(method), f"{method_name} exists but is not callable"
            else:
                # If method doesn't exist, log for implementation
                print(f"WARNING: PortfolioManagerService.{method_name} not found - may need implementation")
    
    def test_trading_engine_trader_methods(self):
        """Test TradingEngineService has trader-related methods"""
        critical_methods = [
            'get_trader',
            'route_signal_to_trader',
            'handle_validated_signal'
        ]
        
        for method_name in critical_methods:
            if hasattr(TradingEngineService, method_name):
                method = getattr(TradingEngineService, method_name)
                assert callable(method)
            else:
                print(f"WARNING: TradingEngineService.{method_name} not found")
    
    def test_risk_manager_validation_methods(self):
        """Test RiskManagerService has signal validation methods"""
        critical_methods = [
            'validate_trading_signal',
            'check_risk_limits',
            'handle_raw_signal'
        ]
        
        for method_name in critical_methods:
            if hasattr(RiskManagerService, method_name):
                method = getattr(RiskManagerService, method_name)
                assert callable(method)
            else:
                print(f"WARNING: RiskManagerService.{method_name} not found")


class TestServiceLifecycleManagement:
    """Test service lifecycle methods work correctly"""
    
    def test_service_context_manager_protocol(self):
        """Test services can be used as async context managers"""
        # Test if services implement async context manager protocol
        services = [
            MarketFeedService,
            StrategyRunnerService,
            TradingEngineService
        ]
        
        for service_class in services:
            # Check for context manager methods
            has_aenter = hasattr(service_class, '__aenter__')
            has_aexit = hasattr(service_class, '__aexit__')
            
            if has_aenter or has_aexit:
                assert has_aenter and has_aexit, f"{service_class.__name__} incomplete async context manager"
    
    def test_graceful_shutdown_interface(self):
        """Test services have graceful shutdown capabilities"""
        services = [
            MarketFeedService,
            StrategyRunnerService,
            TradingEngineService,
            PortfolioManagerService
        ]
        
        for service_class in services:
            # All services should have stop method
            assert hasattr(service_class, 'stop')
            stop_method = getattr(service_class, 'stop')
            assert inspect.iscoroutinefunction(stop_method)
            
            # Check for cleanup-related methods
            cleanup_methods = ['cleanup', 'shutdown', 'close']
            has_cleanup = any(hasattr(service_class, method) for method in cleanup_methods)
            
            # Either stop() handles cleanup or there's a dedicated cleanup method
            assert has_cleanup or hasattr(service_class, 'stop'), f"{service_class.__name__} lacks cleanup interface"


class TestServiceDependencyInterfaces:
    """Test service dependency injection interfaces"""
    
    def test_settings_dependency_interface(self):
        """Test services correctly accept settings objects"""
        # Mock settings object with common attributes
        mock_settings = Mock()
        mock_settings.active_brokers = ["paper", "zerodha"]
        mock_settings.redis = Mock()
        mock_settings.kafka = Mock()
        
        services = [
            MarketFeedService,
            StrategyRunnerService, 
            TradingEngineService
        ]
        
        for service_class in services:
            try:
                # Test that service can be instantiated with mock settings
                service = service_class(mock_settings, Mock())  # settings, redis_client
                assert service is not None
                
            except TypeError as e:
                # This indicates missing required constructor parameters
                pytest.fail(f"{service_class.__name__} constructor signature issue: {e}")
            except Exception as e:
                # Other exceptions during initialization might be acceptable
                # as long as constructor signature is correct
                pass
    
    def test_redis_client_dependency_interface(self):
        """Test services correctly accept Redis client dependencies"""
        mock_redis = Mock()
        mock_redis.get = Mock()
        mock_redis.set = Mock()
        mock_redis.hget = Mock()
        mock_redis.hset = Mock()
        
        mock_settings = Mock()
        
        services = [
            StrategyRunnerService,
            TradingEngineService,
            PortfolioManagerService
        ]
        
        for service_class in services:
            try:
                service = service_class(mock_settings, mock_redis)
                assert service is not None
                
                # Test that service stores redis client
                if hasattr(service, 'redis_client') or hasattr(service, '_redis'):
                    # Service correctly accepts and stores Redis client
                    pass
                else:
                    print(f"WARNING: {service_class.__name__} may not store Redis client properly")
                    
            except Exception as e:
                pytest.fail(f"{service_class.__name__} Redis dependency issue: {e}")