"""
Service protocols for runtime interface validation.
Use typing_extensions.runtime_checkable to validate service implementations.
"""

from typing import Protocol, runtime_checkable, Dict, Any, Awaitable


@runtime_checkable  
class ServiceLifecycleProtocol(Protocol):
    """Protocol for basic service lifecycle methods"""
    
    async def start(self) -> None:
        """Start the service"""
        ...
    
    async def stop(self) -> None:
        """Stop the service"""
        ...


@runtime_checkable
class HealthCheckProtocol(Protocol):
    """Protocol for services that provide health checks"""
    
    async def health_check(self) -> Dict[str, Any]:
        """Return service health status"""
        ...


@runtime_checkable
class MetricsProtocol(Protocol):
    """Protocol for services that provide metrics"""
    
    def get_metrics(self) -> Dict[str, Any]:
        """Return service metrics"""
        ...


@runtime_checkable
class MarketFeedProtocol(ServiceLifecycleProtocol, HealthCheckProtocol, MetricsProtocol, Protocol):
    """Complete protocol for market feed services"""
    pass


@runtime_checkable
class MessageHandlerProtocol(Protocol):
    """Protocol for services with message handling capability"""
    
    async def _handle_message(self, message: Dict[str, Any], topic: str) -> None:
        """Handle incoming messages with topic context"""
        ...


@runtime_checkable
class StatusProviderProtocol(Protocol):
    """Protocol for services that provide status information"""
    
    def get_status(self) -> Dict[str, Any]:
        """Return service status"""
        ...


@runtime_checkable
class TradingEngineProtocol(ServiceLifecycleProtocol, StatusProviderProtocol, MessageHandlerProtocol, Protocol):
    """Complete protocol for trading engine services"""
    pass


@runtime_checkable
class PortfolioManagerProtocol(ServiceLifecycleProtocol, MessageHandlerProtocol, Protocol):
    """Complete protocol for portfolio manager services"""
    
    async def _handle_order_event(self, message: Dict[str, Any], topic: str) -> None:
        """Handle order events"""
        ...


@runtime_checkable
class RiskManagerProtocol(ServiceLifecycleProtocol, MessageHandlerProtocol, Protocol):
    """Complete protocol for risk manager services"""
    
    def get_monitoring_metrics(self) -> Dict[str, Any]:
        """Return risk monitoring metrics"""
        ...


@runtime_checkable
class StrategyRunnerProtocol(ServiceLifecycleProtocol, MessageHandlerProtocol, Protocol):
    """Complete protocol for strategy runner services"""
    
    async def _load_strategies(self) -> None:
        """Load strategies from configuration"""
        ...