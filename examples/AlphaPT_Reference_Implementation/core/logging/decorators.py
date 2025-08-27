"""Enhanced logging decorators for AlphaPT."""

import asyncio
import functools
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Union, Dict

from core.logging.business_loggers import (
    system_performance_logger,
    trading_audit_logger,
    system_error_logger
)


def log_trading_performance(
    operation: str,
    component: Optional[str] = None,
    include_args: bool = False,
    include_result: bool = False
):
    """Decorator to log trading operation performance."""
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error = None
            result = None
            
            # Extract component name if not provided
            actual_component = component or getattr(func, '__module__', 'unknown')
            
            # Prepare context
            context = {}
            if include_args and args:
                context['args_count'] = len(args)
            if include_args and kwargs:
                context['kwargs'] = {k: str(v)[:100] for k, v in kwargs.items()}
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = e
                # Log trading error
                system_error_logger.trading_error(
                    error=e,
                    error_category="operation_error",
                    operation=operation,
                    component=actual_component
                )
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                
                # Add result info if requested
                if include_result and result is not None:
                    context['result_type'] = type(result).__name__
                    if hasattr(result, '__len__'):
                        context['result_size'] = len(result)
                
                # Log performance metrics
                system_performance_logger.execution_metrics(
                    operation=operation,
                    component=actual_component,
                    execution_time_ms=execution_time_ms,
                    success=success,
                    **context
                )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error = None
            result = None
            
            actual_component = component or getattr(func, '__module__', 'unknown')
            
            context = {}
            if include_args and args:
                context['args_count'] = len(args)
            if include_args and kwargs:
                context['kwargs'] = {k: str(v)[:100] for k, v in kwargs.items()}
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = e
                system_error_logger.trading_error(
                    error=e,
                    error_category="operation_error",
                    operation=operation,
                    component=actual_component
                )
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                
                if include_result and result is not None:
                    context['result_type'] = type(result).__name__
                    if hasattr(result, '__len__'):
                        context['result_size'] = len(result)
                
                system_performance_logger.execution_metrics(
                    operation=operation,
                    component=actual_component,
                    execution_time_ms=execution_time_ms,
                    success=success,
                    **context
                )
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def log_order_lifecycle(event_type: str):
    """Decorator to automatically log order lifecycle events."""
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = None
            try:
                result = await func(*args, **kwargs)
                
                # Extract order information from result or arguments
                order_info = {}
                if hasattr(result, '__dict__'):
                    order_info = {
                        'order_id': getattr(result, 'order_id', 'unknown'),
                        'strategy_name': getattr(result, 'strategy_name', 'unknown'),
                        'instrument_token': getattr(result, 'instrument_token', 0),
                        'tradingsymbol': getattr(result, 'tradingsymbol', 'unknown'),
                        'transaction_type': getattr(result, 'transaction_type', 'unknown'),
                        'quantity': getattr(result, 'quantity', 0),
                        'price': getattr(result, 'price', None)
                    }
                
                # Log the order event
                trading_audit_logger.order_lifecycle_event(
                    event_type=event_type,
                    **order_info
                )
                
                return result
            except Exception as e:
                # Still try to log partial information
                if args and hasattr(args[0], '__dict__'):
                    order_info = {
                        'order_id': getattr(args[0], 'order_id', 'unknown'),
                        'error': str(e)
                    }
                    trading_audit_logger.order_lifecycle_event(
                        event_type=f"{event_type}_failed",
                        **order_info
                    )
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = None
            try:
                result = func(*args, **kwargs)
                
                order_info = {}
                if hasattr(result, '__dict__'):
                    order_info = {
                        'order_id': getattr(result, 'order_id', 'unknown'),
                        'strategy_name': getattr(result, 'strategy_name', 'unknown'),
                        'instrument_token': getattr(result, 'instrument_token', 0),
                        'tradingsymbol': getattr(result, 'tradingsymbol', 'unknown'),
                        'transaction_type': getattr(result, 'transaction_type', 'unknown'),
                        'quantity': getattr(result, 'quantity', 0),
                        'price': getattr(result, 'price', None)
                    }
                
                trading_audit_logger.order_lifecycle_event(
                    event_type=event_type,
                    **order_info
                )
                
                return result
            except Exception as e:
                if args and hasattr(args[0], '__dict__'):
                    order_info = {
                        'order_id': getattr(args[0], 'order_id', 'unknown'),
                        'error': str(e)
                    }
                    trading_audit_logger.order_lifecycle_event(
                        event_type=f"{event_type}_failed",
                        **order_info
                    )
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def log_system_performance(
    operation: str,
    component: Optional[str] = None,
    measure_memory: bool = False,
    critical_threshold_ms: Optional[float] = None
):
    """Decorator to log system performance with optional memory measurement."""
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            import psutil
            import os
            
            start_time = time.time()
            process = psutil.Process(os.getpid()) if measure_memory else None
            start_memory = process.memory_info().rss / 1024 / 1024 if process else None
            
            actual_component = component or getattr(func, '__module__', 'unknown')
            
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                
                perf_data = {
                    'operation': operation,
                    'component': actual_component,
                    'execution_time_ms': execution_time_ms,
                    'success': True
                }
                
                if measure_memory and process:
                    end_memory = process.memory_info().rss / 1024 / 1024
                    perf_data['memory_usage_mb'] = end_memory
                    if start_memory:
                        perf_data['memory_delta_mb'] = end_memory - start_memory
                
                # Check if performance is critical
                is_critical = (critical_threshold_ms and 
                             execution_time_ms > critical_threshold_ms)
                
                if is_critical:
                    perf_data['performance_alert'] = 'critical_threshold_exceeded'
                    perf_data['threshold_ms'] = critical_threshold_ms
                
                system_performance_logger.execution_metrics(**perf_data)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            import psutil
            import os
            
            start_time = time.time()
            process = psutil.Process(os.getpid()) if measure_memory else None
            start_memory = process.memory_info().rss / 1024 / 1024 if process else None
            
            actual_component = component or getattr(func, '__module__', 'unknown')
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                
                perf_data = {
                    'operation': operation,
                    'component': actual_component,
                    'execution_time_ms': execution_time_ms,
                    'success': True
                }
                
                if measure_memory and process:
                    end_memory = process.memory_info().rss / 1024 / 1024
                    perf_data['memory_usage_mb'] = end_memory
                    if start_memory:
                        perf_data['memory_delta_mb'] = end_memory - start_memory
                
                is_critical = (critical_threshold_ms and 
                             execution_time_ms > critical_threshold_ms)
                
                if is_critical:
                    perf_data['performance_alert'] = 'critical_threshold_exceeded'
                    perf_data['threshold_ms'] = critical_threshold_ms
                
                system_performance_logger.execution_metrics(**perf_data)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def log_database_operation(
    operation_type: str,
    table_name: Optional[str] = None,
    log_slow_queries: bool = True,
    slow_query_threshold_ms: float = 1000.0
):
    """Decorator to log database operations with performance tracking."""
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            record_count = None
            success = True
            
            try:
                result = await func(*args, **kwargs)
                
                # Try to extract record count from result
                if isinstance(result, (list, tuple)):
                    record_count = len(result)
                elif hasattr(result, 'rowcount'):
                    record_count = result.rowcount
                
                return result
            except Exception as e:
                success = False
                system_error_logger.system_error(
                    error=e,
                    component="database",
                    operation=f"{operation_type}_{table_name or 'unknown'}"
                )
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                
                # Log performance metrics
                perf_data = {
                    'operation': f"db_{operation_type}",
                    'component': 'database',
                    'execution_time_ms': execution_time_ms,
                    'success': success
                }
                
                if table_name:
                    perf_data['table_name'] = table_name
                if record_count is not None:
                    perf_data['record_count'] = record_count
                
                # Check for slow queries
                if log_slow_queries and execution_time_ms > slow_query_threshold_ms:
                    perf_data['slow_query_alert'] = True
                    perf_data['threshold_ms'] = slow_query_threshold_ms
                
                system_performance_logger.execution_metrics(**perf_data)
        
        # Similar sync wrapper implementation
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            record_count = None
            success = True
            
            try:
                result = func(*args, **kwargs)
                
                if isinstance(result, (list, tuple)):
                    record_count = len(result)
                elif hasattr(result, 'rowcount'):
                    record_count = result.rowcount
                
                return result
            except Exception as e:
                success = False
                system_error_logger.system_error(
                    error=e,
                    component="database",
                    operation=f"{operation_type}_{table_name or 'unknown'}"
                )
                raise
            finally:
                execution_time_ms = (time.time() - start_time) * 1000
                
                perf_data = {
                    'operation': f"db_{operation_type}",
                    'component': 'database',
                    'execution_time_ms': execution_time_ms,
                    'success': success
                }
                
                if table_name:
                    perf_data['table_name'] = table_name
                if record_count is not None:
                    perf_data['record_count'] = record_count
                
                if log_slow_queries and execution_time_ms > slow_query_threshold_ms:
                    perf_data['slow_query_alert'] = True
                    perf_data['threshold_ms'] = slow_query_threshold_ms
                
                system_performance_logger.execution_metrics(**perf_data)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Convenience functions for manual logging
def log_manual_audit_event(event_type: str, **kwargs):
    """Manually log an audit event."""
    trading_audit_logger.order_lifecycle_event(event_type, **kwargs)


def log_manual_performance_metric(operation: str, execution_time_ms: float, **kwargs):
    """Manually log a performance metric."""
    system_performance_logger.execution_metrics(
        operation, 
        kwargs.get('component', 'manual'), 
        execution_time_ms, 
        **kwargs
    )


def log_manual_error(error: Exception, component: str, **kwargs):
    """Manually log a system error."""
    system_error_logger.system_error(error, component, **kwargs)