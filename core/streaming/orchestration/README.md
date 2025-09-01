# Core Streaming Orchestration

## Overview

The streaming orchestration module provides high-level coordination and lifecycle management for streaming services in Alpha Panda. It handles the orchestration of multiple streaming components, service lifecycle coordination, and inter-service communication patterns.

## Components

### `lifecycle_coordinator.py`
Service lifecycle coordination across streaming components:

- **Lifecycle Management**: Coordinates startup and shutdown of streaming services
- **Dependency Resolution**: Manages service dependencies and startup order
- **Health Coordination**: Coordinates health checks across streaming services
- **Graceful Shutdown**: Orchestrates graceful shutdown of streaming pipeline
- **Resource Management**: Manages shared resources across streaming components

### `service_orchestrator.py`
High-level orchestration of streaming services:

- **Service Registry**: Maintains registry of active streaming services
- **Message Routing**: Orchestrates message routing between services
- **Load Balancing**: Balances load across streaming service instances
- **Service Discovery**: Handles service discovery and registration
- **Configuration Management**: Manages configuration across streaming services

## Architecture Patterns

### Service Lifecycle Coordination
```python
class LifecycleCoordinator:
    """Coordinates lifecycle of streaming services"""
    
    def __init__(self, services: List[StreamingService]):
        self.services = services
        self.dependency_graph = self.build_dependency_graph()
    
    async def start_services(self):
        """Start services in dependency order"""
        startup_order = self.resolve_startup_order()
        
        for service in startup_order:
            await service.start()
            await self.verify_service_health(service)
    
    async def shutdown_services(self):
        """Shutdown services in reverse dependency order"""
        shutdown_order = reversed(self.resolve_startup_order())
        
        for service in shutdown_order:
            await service.graceful_shutdown()
```

### Service Orchestration
```python
class ServiceOrchestrator:
    """Orchestrates streaming service operations"""
    
    def __init__(self):
        self.service_registry = {}
        self.message_router = MessageRouter()
    
    def register_service(self, service: StreamingService):
        """Register streaming service with orchestrator"""
        self.service_registry[service.name] = service
        self.message_router.add_service(service)
    
    async def route_message(self, message: dict, target_service: str):
        """Route message to target service"""
        service = self.service_registry.get(target_service)
        if service:
            await service.process_message(message)
```

## Usage

### Service Orchestration Setup
```python
from core.streaming.orchestration import ServiceOrchestrator, LifecycleCoordinator

# Initialize orchestrator
orchestrator = ServiceOrchestrator()

# Register streaming services
orchestrator.register_service(strategy_runner_service)
orchestrator.register_service(risk_manager_service)
orchestrator.register_service(trading_engine_service)

# Initialize lifecycle coordinator
coordinator = LifecycleCoordinator([
    strategy_runner_service,
    risk_manager_service,
    trading_engine_service
])

# Start all services in correct order
await coordinator.start_services()
```

### Message Routing
```python
# Route message to specific service
await orchestrator.route_message(
    message={"type": "signal", "data": signal_data},
    target_service="risk_manager"
)

# Broadcast message to all services
await orchestrator.broadcast_message(
    message={"type": "system_event", "data": system_data}
)
```

## Coordination Patterns

### Dependency Management
```python
class DependencyGraph:
    """Manages service dependencies for startup order"""
    
    def __init__(self):
        self.dependencies = {}
    
    def add_dependency(self, service: str, depends_on: str):
        """Add dependency relationship"""
        if service not in self.dependencies:
            self.dependencies[service] = []
        self.dependencies[service].append(depends_on)
    
    def resolve_startup_order(self) -> List[str]:
        """Resolve topological order for service startup"""
        return self.topological_sort()
```

### Health Coordination
```python
async def coordinate_health_checks(self):
    """Coordinate health checks across all services"""
    health_results = {}
    
    for service_name, service in self.service_registry.items():
        health_results[service_name] = await service.health_check()
    
    overall_health = self.assess_overall_health(health_results)
    return {
        "overall_status": overall_health,
        "service_health": health_results
    }
```

## Architecture Benefits

- **Centralized Coordination**: Single point for managing streaming service lifecycle
- **Dependency Resolution**: Automatic resolution of service startup dependencies
- **Health Monitoring**: Coordinated health checking across streaming pipeline
- **Graceful Shutdown**: Orchestrated shutdown to prevent data loss
- **Resource Efficiency**: Shared resource management across services
- **Configuration Management**: Centralized configuration distribution

## Configuration

Orchestration configuration:

```python
class OrchestrationSettings(BaseModel):
    startup_timeout: int = 60  # seconds
    shutdown_timeout: int = 30  # seconds
    health_check_interval: int = 30  # seconds
    max_startup_retries: int = 3
    service_discovery_enabled: bool = True
```

## Dependencies

- **core.streaming.patterns**: StreamServiceBuilder integration
- **core.monitoring**: Health monitoring and metrics
- **core.config**: Configuration management
- **asyncio**: Async coordination and lifecycle management