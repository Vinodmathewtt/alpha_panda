"""
Standardized service logger initialization for Alpha Panda services.
Provides consistent logging patterns across all service components.
"""

from typing import Dict, Tuple
import structlog

from .enhanced_logging import (
    get_trading_logger_safe,
    get_performance_logger_safe, 
    get_error_logger_safe,
    get_api_logger_safe,
    get_audit_logger_safe,
    get_monitoring_logger_safe,
    get_database_logger_safe
)
from .correlation import (
    CorrelationIdManager,
    get_correlated_logger,
    create_correlation_context
)


class ServiceLogger:
    """Standardized logger collection for services"""
    
    def __init__(self, service_name: str, component: str = None):
        """
        Initialize service logger collection.
        
        Args:
            service_name: Name of the service (e.g., 'risk_manager', 'trading_engine')
            component: Optional component within service (e.g., 'rules', 'state_manager')
        """
        self.service_name = service_name
        self.component = component
        
        # Create logger names with consistent format
        if component:
            base_name = f"{service_name}_{component}"
        else:
            base_name = service_name
            
        # Initialize all logger types
        self.main = get_trading_logger_safe(base_name)
        self.performance = get_performance_logger_safe(f"{base_name}_performance")
        self.error = get_error_logger_safe(f"{base_name}_errors")
        self.audit = get_audit_logger_safe(f"{base_name}_audit")
        self.monitoring = get_monitoring_logger_safe(f"{base_name}_monitoring")
        
        # Bind service context to all loggers
        service_context = {
            "service": service_name,
            "component": component
        }
        
        # Wrap loggers with correlation support
        self.main = get_correlated_logger(self.main.bind(**service_context))
        self.performance = get_correlated_logger(self.performance.bind(**service_context))
        self.error = get_correlated_logger(self.error.bind(**service_context))
        self.audit = get_correlated_logger(self.audit.bind(**service_context))
        self.monitoring = get_correlated_logger(self.monitoring.bind(**service_context))
    
    def bind_broker_context(self, broker: str) -> 'ServiceLogger':
        """
        Create logger instance bound to a specific broker context.
        
        Args:
            broker: Broker namespace (e.g., 'paper', 'zerodha')
            
        Returns:
            New ServiceLogger instance with broker context
        """
        bound_logger = ServiceLogger(self.service_name, self.component)
        
        broker_context = {"broker": broker}
        bound_logger.main = get_correlated_logger(self.main.logger.bind(**broker_context))
        bound_logger.performance = get_correlated_logger(self.performance.logger.bind(**broker_context))
        bound_logger.error = get_correlated_logger(self.error.logger.bind(**broker_context))
        bound_logger.audit = get_correlated_logger(self.audit.logger.bind(**broker_context))
        bound_logger.monitoring = get_correlated_logger(self.monitoring.logger.bind(**broker_context))
        
        return bound_logger
    
    def create_operation_context(self, operation: str, **additional_context) -> str:
        """
        Create a correlation context for a specific operation.
        
        Args:
            operation: Name of the operation
            **additional_context: Additional context information
            
        Returns:
            Correlation ID for the operation
        """
        return create_correlation_context(
            service=self.service_name,
            operation=operation,
            **additional_context
        )


class APIServiceLogger(ServiceLogger):
    """Specialized logger for API services with additional API-specific loggers"""
    
    def __init__(self, service_name: str, component: str = None):
        super().__init__(service_name, component)
        
        # Create API-specific logger names
        if component:
            base_name = f"{service_name}_{component}"
        else:
            base_name = service_name
            
        # Add API-specific logger
        self.api = get_api_logger_safe(f"{base_name}_api")
        
        # Bind service context
        service_context = {
            "service": service_name,
            "component": component
        }
        self.api = self.api.bind(**service_context)
    
    def bind_request_context(self, request_id: str, client_ip: str, method: str, path: str) -> 'APIServiceLogger':
        """
        Create logger instance bound to a specific API request context.
        
        Args:
            request_id: Unique request identifier
            client_ip: Client IP address
            method: HTTP method
            path: Request path
            
        Returns:
            New APIServiceLogger instance with request context
        """
        bound_logger = APIServiceLogger(self.service_name, self.component)
        
        request_context = {
            "request_id": request_id,
            "client_ip": client_ip,
            "method": method,
            "path": path
        }
        
        # Bind all logger types with request context
        bound_logger.main = self.main.bind(**request_context)
        bound_logger.performance = self.performance.bind(**request_context)
        bound_logger.error = self.error.bind(**request_context)
        bound_logger.audit = self.audit.bind(**request_context)
        bound_logger.monitoring = self.monitoring.bind(**request_context)
        bound_logger.api = self.api.bind(**request_context)
        
        return bound_logger


class DatabaseServiceLogger(ServiceLogger):
    """Specialized logger for database operations with additional database-specific loggers"""
    
    def __init__(self, service_name: str, component: str = None):
        super().__init__(service_name, component)
        
        # Create database-specific logger names
        if component:
            base_name = f"{service_name}_{component}"
        else:
            base_name = service_name
            
        # Add database-specific logger
        self.database = get_database_logger_safe(f"{base_name}_database")
        
        # Bind service context
        service_context = {
            "service": service_name,
            "component": component
        }
        self.database = self.database.bind(**service_context)


def get_service_logger(service_name: str, component: str = None) -> ServiceLogger:
    """
    Get a standardized service logger collection.
    
    Args:
        service_name: Name of the service
        component: Optional component within service
        
    Returns:
        ServiceLogger instance with all logger types initialized
    """
    return ServiceLogger(service_name, component)


def get_api_service_logger(service_name: str, component: str = None) -> APIServiceLogger:
    """
    Get a standardized API service logger collection.
    
    Args:
        service_name: Name of the API service
        component: Optional component within service
        
    Returns:
        APIServiceLogger instance with all logger types initialized
    """
    return APIServiceLogger(service_name, component)


def get_database_service_logger(service_name: str, component: str = None) -> DatabaseServiceLogger:
    """
    Get a standardized database service logger collection.
    
    Args:
        service_name: Name of the database service
        component: Optional component within service
        
    Returns:
        DatabaseServiceLogger instance with all logger types initialized
    """
    return DatabaseServiceLogger(service_name, component)