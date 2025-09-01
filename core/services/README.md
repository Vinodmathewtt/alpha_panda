# Core Services Module

## Overview

The `core/services/` module provides base service classes and common service utilities for Alpha Panda's microservice architecture. It defines standardized service lifecycle management, health monitoring, and common service patterns.

## Components

### `base_service.py`
Base service class for standardized service lifecycle management:

- **BaseService**: Abstract base class for all Alpha Panda services
- **ServiceStatus**: Enumeration of service lifecycle states (stopped, starting, running, stopping, error)
- **Lifecycle Management**: Standardized start/stop/health check patterns
- **Health Integration**: Built-in health monitoring and status reporting
- **Graceful Shutdown**: Proper service shutdown with cleanup
- **Error Handling**: Service-level error handling and recovery

### `__init__.py`
Module exports for easy importing of service base classes and utilities.

## Key Features

- **Standardized Lifecycle**: Consistent start/stop patterns across all services
- **Health Monitoring**: Built-in health check and status reporting capabilities
- **Graceful Shutdown**: Proper service shutdown with resource cleanup
- **Status Tracking**: Real-time service status monitoring and reporting
- **Error Recovery**: Service-level error handling and recovery mechanisms
- **Async Support**: Full asyncio support for non-blocking service operations
- **Logging Integration**: Built-in logging with service identification

## Usage

### Creating a Service
```python
from core.services.base_service import BaseService, ServiceStatus
import asyncio

class MyService(BaseService):
    def __init__(self, settings):
        super().__init__(service_name="my_service")
        self.settings = settings
        
    async def start(self):
        """Start the service"""
        self.status = ServiceStatus.STARTING
        self.logger.info("Starting service")
        
        try:
            # Initialize service resources
            await self._initialize_resources()
            
            self.status = ServiceStatus.RUNNING
            self.logger.info("Service started successfully")
            
        except Exception as e:
            self.status = ServiceStatus.ERROR
            self.logger.error(f"Service startup failed: {e}")
            raise
    
    async def stop(self):
        """Stop the service"""
        self.status = ServiceStatus.STOPPING
        self.logger.info("Stopping service")
        
        try:
            # Cleanup service resources
            await self._cleanup_resources()
            
            self.status = ServiceStatus.STOPPED
            self.logger.info("Service stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Service shutdown error: {e}")
            raise
    
    async def health_check(self):
        """Service health check"""
        if self.status == ServiceStatus.RUNNING:
            return {"status": "healthy"}
        else:
            return {"status": "unhealthy", "reason": f"Service status: {self.status}"}
```

### Service Lifecycle Management
```python
# Initialize service
service = MyService(settings)

# Start service
await service.start()

# Check service status
print(f"Service status: {service.status}")

# Health check
health = await service.health_check()
print(f"Health: {health}")

# Stop service gracefully
await service.stop()
```

### Multiple Service Orchestration
```python
async def run_services(services):
    """Run multiple services with coordinated lifecycle"""
    
    # Start all services
    for service in services:
        await service.start()
        print(f"Started {service.service_name}")
    
    try:
        # Wait for shutdown signal
        await wait_for_shutdown_signal()
        
    finally:
        # Stop all services in reverse order
        for service in reversed(services):
            await service.stop()
            print(f"Stopped {service.service_name}")
```

## Service Status Types

### Status Enumeration
- **STOPPED**: Service is not running
- **STARTING**: Service is in startup phase
- **RUNNING**: Service is fully operational
- **STOPPING**: Service is shutting down
- **ERROR**: Service encountered an error and is non-operational

### Status Transitions
- **STOPPED → STARTING**: Service initialization begins
- **STARTING → RUNNING**: Service startup completed successfully
- **STARTING → ERROR**: Service startup failed
- **RUNNING → STOPPING**: Graceful shutdown initiated
- **STOPPING → STOPPED**: Service shutdown completed
- **Any → ERROR**: Service error occurred

## Service Patterns

### Standard Service Structure
```python
class StandardService(BaseService):
    def __init__(self, service_name: str, settings):
        super().__init__(service_name)
        self.settings = settings
        self.resources = {}
    
    async def start(self):
        self.status = ServiceStatus.STARTING
        await self._initialize_dependencies()
        await self._start_components()
        self.status = ServiceStatus.RUNNING
    
    async def stop(self):
        self.status = ServiceStatus.STOPPING
        await self._stop_components()
        await self._cleanup_dependencies()
        self.status = ServiceStatus.STOPPED
    
    async def health_check(self):
        # Service-specific health checks
        return await self._perform_health_checks()
```

### Stream Processing Service Pattern
```python
from core.services.base_service import BaseService
from core.streaming.consumer import StreamConsumer

class StreamProcessingService(BaseService):
    def __init__(self, service_name: str, settings):
        super().__init__(service_name)
        self.settings = settings
        self.consumer = None
        self.producer = None
    
    async def start(self):
        self.status = ServiceStatus.STARTING
        
        # Initialize streaming components
        self.consumer = StreamConsumer(self.settings.kafka)
        self.producer = StreamProducer(self.settings.kafka)
        
        # Start consuming messages
        await self.consumer.start()
        await self.producer.start()
        
        self.status = ServiceStatus.RUNNING
    
    async def stop(self):
        self.status = ServiceStatus.STOPPING
        
        # Stop streaming components
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        
        self.status = ServiceStatus.STOPPED
```

## Health Monitoring Integration

### Built-in Health Checks
```python
# Service automatically provides basic health information
health_status = await service.health_check()

# Standard health response format
{
    "status": "healthy",  # healthy, unhealthy, degraded
    "uptime": 3600,      # seconds since startup
    "service_name": "my_service",
    "version": "1.0.0",
    "dependencies": {
        "database": "healthy",
        "redis": "healthy",
        "kafka": "degraded"
    }
}
```

### Custom Health Checks
```python
class MyService(BaseService):
    async def health_check(self):
        # Base service health
        base_health = await super().health_check()
        
        # Custom health checks
        dependencies = {}
        dependencies["database"] = await self._check_database()
        dependencies["external_api"] = await self._check_external_api()
        
        # Aggregate health status
        overall_status = self._aggregate_health_status(dependencies)
        
        return {
            **base_health,
            "dependencies": dependencies,
            "overall_status": overall_status
        }
```

## Architecture Patterns

- **Template Method Pattern**: BaseService defines service lifecycle template
- **Observer Pattern**: Service status change notifications
- **Strategy Pattern**: Different service implementations with common interface
- **Resource Management**: Proper resource acquisition and cleanup patterns
- **Graceful Degradation**: Service continues operation with reduced functionality
- **Circuit Breaker**: Service protection from cascading failures

## Best Practices

1. **Inherit from BaseService**: All services should extend BaseService
2. **Proper Resource Management**: Initialize and cleanup resources properly
3. **Health Check Implementation**: Implement meaningful health checks
4. **Error Handling**: Handle startup and runtime errors gracefully
5. **Logging**: Use consistent logging patterns with service identification
6. **Status Updates**: Keep service status current throughout lifecycle
7. **Dependency Management**: Manage service dependencies explicitly

## Dependencies

- **asyncio**: Async service lifecycle management
- **logging**: Service logging and monitoring
- **abc**: Abstract base class patterns
- **core.monitoring**: Health monitoring integration
- **core.config**: Service configuration management