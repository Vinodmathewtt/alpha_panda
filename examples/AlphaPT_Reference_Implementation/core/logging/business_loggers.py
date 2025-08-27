"""Specialized business loggers for AlphaPT trading operations."""

import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from core.logging.log_channels import LogChannel
from core.logging.multi_channel_logger import ChannelStructuredLogger, get_channel_logger


class TradingAuditLogger(ChannelStructuredLogger):
    """Enhanced audit logger for trading activities with dedicated file."""

    def __init__(self):
        super().__init__("trading_audit", "audit", LogChannel.AUDIT)
        self.session_id = str(uuid4())

    def order_lifecycle_event(
        self,
        event_type: str,  # placed, modified, cancelled, filled, rejected
        order_id: str,
        strategy_name: str,
        instrument_token: int,
        tradingsymbol: str,
        transaction_type: str,  # BUY, SELL
        quantity: int,
        price: Optional[Union[float, Decimal]] = None,
        order_type: str = "MARKET",
        user_id: Optional[str] = None,
        exchange: str = "NSE",
        **kwargs,
    ) -> None:
        """Log comprehensive order lifecycle events."""
        
        audit_data = {
            "audit_type": "order_lifecycle",
            "event_type": event_type,
            "order_id": order_id,
            "strategy_name": strategy_name,
            "instrument_token": instrument_token,
            "tradingsymbol": tradingsymbol,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "exchange": exchange,
            "session_id": self.session_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if price is not None:
            audit_data["price"] = float(price) if isinstance(price, Decimal) else price
        
        if user_id:
            audit_data["user_id"] = user_id
            
        # Add any additional context
        audit_data.update(kwargs)
        
        self.info(f"Order {event_type}", **audit_data)

    def position_change_event(
        self,
        strategy_name: str,
        instrument_token: int,
        tradingsymbol: str,
        old_quantity: int,
        new_quantity: int,
        position_value: float,
        pnl: float,
        average_price: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Log position change events."""
        
        audit_data = {
            "audit_type": "position_change",
            "strategy_name": strategy_name,
            "instrument_token": instrument_token,
            "tradingsymbol": tradingsymbol,
            "old_quantity": old_quantity,
            "new_quantity": new_quantity,
            "quantity_change": new_quantity - old_quantity,
            "position_value": position_value,
            "pnl": pnl,
            "session_id": self.session_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if average_price:
            audit_data["average_price"] = average_price
            
        audit_data.update(kwargs)
        
        self.info("Position changed", **audit_data)

    def risk_event(
        self,
        event_type: str,  # breach, warning, limit_updated
        strategy_name: str,
        risk_type: str,  # position_limit, loss_limit, exposure_limit
        risk_metric: str,
        current_value: float,
        limit_value: float,
        breach_level: str,  # warning, critical
        action_taken: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log risk management events."""
        
        audit_data = {
            "audit_type": "risk_management",
            "event_type": event_type,
            "strategy_name": strategy_name,
            "risk_type": risk_type,
            "risk_metric": risk_metric,
            "current_value": current_value,
            "limit_value": limit_value,
            "breach_percentage": ((current_value / limit_value) - 1) * 100 if limit_value > 0 else 0,
            "breach_level": breach_level,
            "session_id": self.session_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if action_taken:
            audit_data["action_taken"] = action_taken
            
        audit_data.update(kwargs)
        
        log_method = self.warning if breach_level == "warning" else self.error
        log_method(f"Risk {event_type}", **audit_data)

    def strategy_lifecycle_event(
        self,
        event_type: str,  # started, stopped, paused, resumed, error
        strategy_name: str,
        user_id: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log strategy lifecycle events."""
        
        audit_data = {
            "audit_type": "strategy_lifecycle",
            "event_type": event_type,
            "strategy_name": strategy_name,
            "session_id": self.session_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if user_id:
            audit_data["user_id"] = user_id
        if reason:
            audit_data["reason"] = reason
            
        audit_data.update(kwargs)
        
        self.info(f"Strategy {event_type}", **audit_data)

    def compliance_event(
        self,
        compliance_type: str,  # regulatory_limit, trading_halt, market_hours
        description: str,
        severity: str = "INFO",
        regulatory_reference: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log compliance-related events."""
        
        audit_data = {
            "audit_type": "compliance",
            "compliance_type": compliance_type,
            "description": description,
            "severity": severity,
            "session_id": self.session_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if regulatory_reference:
            audit_data["regulatory_reference"] = regulatory_reference
            
        audit_data.update(kwargs)
        
        log_method = getattr(self, severity.lower(), self.info)
        log_method(f"Compliance: {compliance_type}", **audit_data)


class SystemPerformanceLogger(ChannelStructuredLogger):
    """Enhanced performance logger with system metrics."""

    def __init__(self):
        super().__init__("system_performance", "performance", LogChannel.PERFORMANCE)

    def execution_metrics(
        self,
        operation: str,
        component: str,
        execution_time_ms: float,
        success: bool = True,
        record_count: Optional[int] = None,
        memory_usage_mb: Optional[float] = None,
        cpu_usage_percent: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Log detailed execution performance metrics."""
        
        perf_data = {
            "metric_type": "execution_performance",
            "operation": operation,
            "component": component,
            "execution_time_ms": execution_time_ms,
            "success": success,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if record_count is not None:
            perf_data["record_count"] = record_count
            perf_data["records_per_second"] = record_count / (execution_time_ms / 1000) if execution_time_ms > 0 else 0
            
        if memory_usage_mb is not None:
            perf_data["memory_usage_mb"] = memory_usage_mb
            
        if cpu_usage_percent is not None:
            perf_data["cpu_usage_percent"] = cpu_usage_percent
            
        perf_data.update(kwargs)
        
        self.info(f"Performance: {operation}", **perf_data)

    def throughput_metrics(
        self,
        operation: str,
        component: str,
        count: int,
        time_window_seconds: float,
        success_count: Optional[int] = None,
        error_count: Optional[int] = None,
        **kwargs,
    ) -> None:
        """Log throughput and rate metrics."""
        
        rate_per_second = count / time_window_seconds if time_window_seconds > 0 else 0
        success_rate = (success_count / count * 100) if success_count is not None and count > 0 else None
        
        throughput_data = {
            "metric_type": "throughput",
            "operation": operation,
            "component": component,
            "total_count": count,
            "time_window_seconds": time_window_seconds,
            "rate_per_second": rate_per_second,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if success_count is not None:
            throughput_data["success_count"] = success_count
        if error_count is not None:
            throughput_data["error_count"] = error_count
        if success_rate is not None:
            throughput_data["success_rate_percent"] = success_rate
            
        throughput_data.update(kwargs)
        
        self.info(f"Throughput: {operation}", **throughput_data)

    def latency_metrics(
        self,
        operation: str,
        component: str,
        latency_ms: float,
        latency_type: str = "end_to_end",  # end_to_end, processing, network
        target_latency_ms: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Log latency metrics with SLA tracking."""
        
        latency_data = {
            "metric_type": "latency",
            "operation": operation,
            "component": component,
            "latency_ms": latency_ms,
            "latency_type": latency_type,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if target_latency_ms is not None:
            latency_data["target_latency_ms"] = target_latency_ms
            latency_data["sla_breach"] = latency_ms > target_latency_ms
            latency_data["latency_ratio"] = latency_ms / target_latency_ms
            
        latency_data.update(kwargs)
        
        log_method = self.warning if (target_latency_ms and latency_ms > target_latency_ms) else self.info
        log_method(f"Latency: {operation}", **latency_data)

    def resource_utilization(
        self,
        component: str,
        cpu_percent: float,
        memory_mb: float,
        memory_percent: Optional[float] = None,
        disk_io_mb: Optional[float] = None,
        network_io_mb: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Log system resource utilization."""
        
        resource_data = {
            "metric_type": "resource_utilization",
            "component": component,
            "cpu_percent": cpu_percent,
            "memory_mb": memory_mb,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if memory_percent is not None:
            resource_data["memory_percent"] = memory_percent
        if disk_io_mb is not None:
            resource_data["disk_io_mb"] = disk_io_mb
        if network_io_mb is not None:
            resource_data["network_io_mb"] = network_io_mb
            
        resource_data.update(kwargs)
        
        self.info(f"Resources: {component}", **resource_data)


class MarketDataQualityLogger(ChannelStructuredLogger):
    """Logger for market data quality and monitoring."""

    def __init__(self):
        super().__init__("market_data_quality", "market_data", LogChannel.MARKET_DATA)

    def data_quality_event(
        self,
        instrument_token: int,
        tradingsymbol: str,
        quality_metric: str,  # latency, gap, duplicate, invalid_price
        severity: str,  # info, warning, error
        measured_value: float,
        threshold_value: Optional[float] = None,
        data_source: str = "zerodha",
        **kwargs,
    ) -> None:
        """Log market data quality events."""
        
        quality_data = {
            "event_type": "data_quality",
            "instrument_token": instrument_token,
            "tradingsymbol": tradingsymbol,
            "quality_metric": quality_metric,
            "severity": severity,
            "measured_value": measured_value,
            "data_source": data_source,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if threshold_value is not None:
            quality_data["threshold_value"] = threshold_value
            quality_data["threshold_breach"] = measured_value > threshold_value
            
        quality_data.update(kwargs)
        
        log_method = getattr(self, severity.lower(), self.info)
        log_method(f"Data quality: {quality_metric}", **quality_data)

    def feed_connectivity_event(
        self,
        event_type: str,  # connected, disconnected, reconnected, error
        data_source: str,
        connection_details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log market data feed connectivity events."""
        
        connectivity_data = {
            "event_type": "feed_connectivity",
            "connectivity_event": event_type,
            "data_source": data_source,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if connection_details:
            connectivity_data["connection_details"] = connection_details
        if error_message:
            connectivity_data["error_message"] = error_message
            
        connectivity_data.update(kwargs)
        
        log_method = self.error if event_type in ["disconnected", "error"] else self.info
        log_method(f"Feed {event_type}", **connectivity_data)


class SystemErrorLogger(ChannelStructuredLogger):
    """Enhanced error logger with categorization and context."""

    def __init__(self):
        super().__init__("system_errors", "error", LogChannel.ERRORS)

    def system_error(
        self,
        error: Exception,
        component: str,
        operation: Optional[str] = None,
        severity: str = "ERROR",
        context: Optional[Dict[str, Any]] = None,
        recovery_action: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log system errors with full context and recovery information."""
        
        error_data = {
            "error_category": "system_error",
            "component": component,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "severity": severity,
            "traceback": traceback.format_exc(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if operation:
            error_data["operation"] = operation
        if context:
            error_data["context"] = context
        if recovery_action:
            error_data["recovery_action"] = recovery_action
            
        error_data.update(kwargs)
        
        log_method = getattr(self, severity.lower(), self.error)
        log_method(f"System error in {component}", **error_data)

    def trading_error(
        self,
        error: Exception,
        error_category: str,  # order_error, position_error, strategy_error
        strategy_name: Optional[str] = None,
        order_id: Optional[str] = None,
        instrument_token: Optional[int] = None,
        impact_assessment: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log trading-specific errors with business impact."""
        
        error_data = {
            "error_category": "trading_error",
            "trading_error_type": error_category,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        
        if strategy_name:
            error_data["strategy_name"] = strategy_name
        if order_id:
            error_data["order_id"] = order_id
        if instrument_token:
            error_data["instrument_token"] = instrument_token
        if impact_assessment:
            error_data["impact_assessment"] = impact_assessment
            
        error_data.update(kwargs)
        
        self.error(f"Trading error: {error_category}", **error_data)


# Global instances for easy access
trading_audit_logger = TradingAuditLogger()
system_performance_logger = SystemPerformanceLogger()
market_data_quality_logger = MarketDataQualityLogger()
system_error_logger = SystemErrorLogger()


# Convenience functions
def log_order_event(event_type: str, **kwargs) -> None:
    """Convenience function to log order events."""
    trading_audit_logger.order_lifecycle_event(event_type, **kwargs)


def log_performance_metric(operation: str, component: str, execution_time_ms: float, **kwargs) -> None:
    """Convenience function to log performance metrics."""
    system_performance_logger.execution_metrics(operation, component, execution_time_ms, **kwargs)


def log_system_error(error: Exception, component: str, **kwargs) -> None:
    """Convenience function to log system errors."""
    system_error_logger.system_error(error, component, **kwargs)


def log_trading_error(error: Exception, error_category: str, **kwargs) -> None:
    """Convenience function to log trading errors."""
    system_error_logger.trading_error(error, error_category, **kwargs)