"""
Pipeline metrics collector for tracking data flow across all services
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass

from core.logging import get_monitoring_logger_safe
from .metrics_registry import MetricsRegistry


@dataclass
class PipelineStageMetrics:
    """Metrics for a single pipeline stage"""
    stage_name: str
    last_activity: Optional[Dict[str, Any]] = None
    activity_count: int = 0
    age_seconds: float = float('inf')
    healthy: bool = False
    error_count: int = 0


class PipelineMetricsCollector:
    """Collects and tracks pipeline flow metrics across all services."""
    
    def __init__(self, redis_client, settings, broker_namespace=None):
        self.redis = redis_client
        self.settings = settings
        # Use provided broker_namespace or default to "shared" for market feed
        self.broker_namespace = broker_namespace or "shared"
        self.logger = get_monitoring_logger_safe("pipeline_metrics")
        
        # TTL for metrics keys (5 minutes)
        self.metrics_ttl = 300
        
    async def record_market_tick(self, tick_data: Dict[str, Any]) -> None:
        """Record market tick received"""
        try:
            timestamp = datetime.utcnow().isoformat()
            
            # Increment count and set last info in a single pipeline
            count_key = MetricsRegistry.market_ticks_count()
            
            # Store last tick info
            last_key = MetricsRegistry.market_ticks_last()
            last_data = {
                "timestamp": timestamp,
                "symbol": tick_data.get("symbol"),
                "instrument_token": tick_data.get("instrument_token"),
                "last_price": tick_data.get("last_price")
            }
            
            pipe = self.redis.pipeline(transaction=False)
            pipe.incr(count_key)
            pipe.setex(last_key, self.metrics_ttl, json.dumps(last_data))
            res = await pipe.execute()
            tick_count = int(res[0]) if res and len(res) > 0 else 0
            
            self.logger.debug("Market tick recorded", 
                            instrument_token=tick_data.get("instrument_token"),
                            tick_count=tick_count,
                            broker=self.broker_namespace)
                            
        except Exception as e:
            self.logger.error("Failed to record market tick", 
                            error=str(e),
                            broker=self.broker_namespace)
        
    async def record_signal_generated(self, signal: Dict[str, Any], broker_context: Optional[str] = None) -> None:
        """Record trading signal generated"""
        try:
            timestamp = datetime.utcnow().isoformat()
            
            # Select namespace (explicit broker preferred)
            namespace = broker_context or self.broker_namespace

            # Increment count and set last info via pipeline
            count_key = MetricsRegistry.signals_count(namespace)
            
            # Store last signal info
            last_key = MetricsRegistry.signals_last(namespace)
            last_data = {
                "timestamp": timestamp,
                "signal_id": signal.get("id"),
                "strategy_id": signal.get("strategy_id"), 
                "instrument_token": signal.get("instrument_token"),
                "signal_type": signal.get("signal_type")
            }
            
            pipe = self.redis.pipeline(transaction=False)
            pipe.incr(count_key)
            pipe.setex(last_key, self.metrics_ttl, json.dumps(last_data))
            res = await pipe.execute()
            signal_count = int(res[0]) if res and len(res) > 0 else 0
            
            self.logger.debug("Signal generation recorded",
                            signal_id=signal.get("id"),
                            strategy_id=signal.get("strategy_id"),
                            signal_count=signal_count,
                            broker=namespace)
                            
        except Exception as e:
            self.logger.error("Failed to record signal generation",
                            error=str(e),
                            broker=self.broker_namespace)
    
    async def record_signal_validated(self, signal: Dict[str, Any], passed: bool, broker_context: Optional[str] = None) -> None:
        """Record signal validation result"""
        try:
            timestamp = datetime.utcnow().isoformat()
            
            # Select namespace (explicit broker preferred)
            namespace = broker_context or self.broker_namespace

            # Increment appropriate count
            if passed:
                count_key = MetricsRegistry.signals_validated_count(namespace)
            else:
                count_key = MetricsRegistry.signals_rejected_count(namespace)
            
            
            # Store last validation info
            last_key = (
                MetricsRegistry.signals_validated_last(namespace)
                if passed else MetricsRegistry.signals_rejected_last(namespace)
            )
            last_data = {
                "timestamp": timestamp,
                "signal_id": signal.get("id"),
                "strategy_id": signal.get("strategy_id"),
                "validation_passed": passed
            }
            
            pipe = self.redis.pipeline(transaction=False)
            pipe.incr(count_key)
            pipe.setex(last_key, self.metrics_ttl, json.dumps(last_data))
            res = await pipe.execute()
            validation_count = int(res[0]) if res and len(res) > 0 else 0
            
            self.logger.debug("Signal validation recorded",
                            signal_id=signal.get("id"),
                            validation_passed=passed,
                            validation_count=validation_count,
                            broker=namespace)
                            
        except Exception as e:
            self.logger.error("Failed to record signal validation",
                            error=str(e),
                            broker=self.broker_namespace)
    
    async def record_order_processed(self, order: Dict[str, Any], broker_context: Optional[str] = None) -> None:
        """Record order processed by trading engine"""
        try:
            timestamp = datetime.utcnow().isoformat()
            
            # Select namespace (explicit broker preferred)
            namespace = broker_context or self.broker_namespace

            # Increment count and set last via pipeline
            count_key = MetricsRegistry.orders_count(namespace)
            
            # Store last order info
            last_key = MetricsRegistry.orders_last(namespace)
            last_data = {
                "timestamp": timestamp,
                "order_id": order.get("id"),
                "strategy_id": order.get("strategy_id"),
                "status": order.get("status"),
                "instrument_token": order.get("instrument_token")
            }
            
            pipe = self.redis.pipeline(transaction=False)
            pipe.incr(count_key)
            pipe.setex(last_key, self.metrics_ttl, json.dumps(last_data))
            res = await pipe.execute()
            order_count = int(res[0]) if res and len(res) > 0 else 0
            
            self.logger.debug("Order processing recorded",
                            order_id=order.get("id"),
                            status=order.get("status"),
                            order_count=order_count,
                            broker=namespace)
                            
        except Exception as e:
            self.logger.error("Failed to record order processing",
                            error=str(e),
                            broker=self.broker_namespace)
    
    async def record_portfolio_update(self, portfolio_id: str, update_data: Dict[str, Any], broker_context: Optional[str] = None) -> None:
        """Record portfolio update"""
        try:
            timestamp = datetime.utcnow().isoformat()
            
            # Select namespace (explicit broker preferred)
            namespace = broker_context or self.broker_namespace

            # Increment count and set last via pipeline
            count_key = MetricsRegistry.portfolio_updates_count(namespace)
            
            # Store last update info  
            last_key = MetricsRegistry.portfolio_updates_last(namespace)
            last_data = {
                "timestamp": timestamp,
                "portfolio_id": portfolio_id,
                "total_pnl": update_data.get("total_pnl"),
                "cash_balance": update_data.get("cash_balance")
            }
            
            pipe = self.redis.pipeline(transaction=False)
            pipe.incr(count_key)
            pipe.setex(last_key, self.metrics_ttl, json.dumps(last_data))
            res = await pipe.execute()
            update_count = int(res[0]) if res and len(res) > 0 else 0
            
            self.logger.debug("Portfolio update recorded",
                            portfolio_id=portfolio_id,
                            update_count=update_count,
                            broker=namespace)
                            
        except Exception as e:
            self.logger.error("Failed to record portfolio update",
                            error=str(e),
                            broker=self.broker_namespace)
    
    async def get_pipeline_health(self) -> Dict[str, Any]:
        """Get overall pipeline health status"""
        try:
            now = datetime.utcnow()
            health = {}
            
            # Check each stage for recent activity
            stages = [
                "market_ticks",
                "signals", 
                "signals_validated",
                "orders",
                "portfolio_updates"
            ]
            
            for stage in stages:
                stage_health = await self._get_stage_health(stage, now)
                health[stage] = stage_health
            
            # Calculate overall health
            all_healthy = all(
                stage_metrics.get("healthy", False) 
                for stage_metrics in health.values()
            )
            
            return {
                "broker": self.broker_namespace,
                "timestamp": now.isoformat(),
                "overall_healthy": all_healthy,
                "stages": health,
                "health_check_interval": self.settings.monitoring.health_check_interval if hasattr(self.settings, 'monitoring') else 30.0
            }
            
        except Exception as e:
            self.logger.error("Failed to get pipeline health",
                            error=str(e),
                            broker=self.broker_namespace)
            return {
                "broker": self.broker_namespace,
                "timestamp": datetime.utcnow().isoformat(),
                "overall_healthy": False,
                "error": str(e)
            }
    
    async def _get_stage_health(self, stage_name: str, now: datetime) -> Dict[str, Any]:
        """Get health status for a specific pipeline stage"""
        try:
            last_key = f"pipeline:{stage_name}:{self.broker_namespace}:last"
            count_key = f"pipeline:{stage_name}:{self.broker_namespace}:count"
            
            # Get last activity data
            last_data_str = await self.redis.get(last_key)
            total_count = await self.redis.get(count_key) or 0
            
            if last_data_str:
                last_activity = json.loads(last_data_str)
                last_time = datetime.fromisoformat(last_activity["timestamp"])
                age_seconds = (now - last_time).total_seconds()
                
                # Define health thresholds per stage
                thresholds = {
                    "market_ticks": 5.0,  # Market data should be very recent
                    "signals": 60.0,  # Signals can be less frequent 
                    "signals_validated": 60.0,
                    "orders": 60.0,
                    "portfolio_updates": 60.0
                }
                
                threshold = thresholds.get(stage_name, 60.0)
                healthy = age_seconds < threshold
                
                return {
                    "stage_name": stage_name,
                    "last_activity": last_activity,
                    "age_seconds": age_seconds,
                    "healthy": healthy,
                    "total_count": int(total_count),
                    "threshold_seconds": threshold
                }
            else:
                return {
                    "stage_name": stage_name,
                    "last_activity": None,
                    "age_seconds": float('inf'),
                    "healthy": False,
                    "total_count": int(total_count),
                    "message": "No recent activity found"
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get {stage_name} stage health",
                            error=str(e),
                            broker=self.broker_namespace)
            return {
                "stage_name": stage_name,
                "healthy": False,
                "error": str(e)
            }
    
    async def increment_count(self, metric_name: str, broker: str = None) -> None:
        """Increment a metric counter (generic method for backwards compatibility)"""
        try:
            # Use the provided broker or fall back to instance broker_namespace
            namespace = broker or self.broker_namespace
            count_key = f"pipeline:{metric_name}:{namespace}:count"
            await self.redis.incr(count_key)
            
            self.logger.debug("Metric count incremented", 
                            metric=metric_name,
                            broker=namespace)
                            
        except Exception as e:
            self.logger.error("Failed to increment count", 
                            metric=metric_name,
                            error=str(e),
                            broker=broker or self.broker_namespace)
    
    async def set_last_activity_timestamp(self, metric_name: str, broker: str = None) -> None:
        """Set the last activity timestamp for a metric"""
        try:
            # Use the provided broker or fall back to instance broker_namespace  
            namespace = broker or self.broker_namespace
            timestamp = datetime.utcnow().isoformat()
            
            last_key = f"pipeline:{metric_name}:{namespace}:last_activity"
            last_data = {
                "timestamp": timestamp,
                "metric": metric_name
            }
            
            await self.redis.setex(last_key, self.metrics_ttl, json.dumps(last_data))
            
            self.logger.debug("Last activity timestamp set",
                            metric=metric_name,
                            broker=namespace)
                            
        except Exception as e:
            self.logger.error("Failed to set last activity timestamp",
                            metric=metric_name,
                            error=str(e),
                            broker=broker or self.broker_namespace)
    
    async def reset_metrics(self) -> None:
        """Reset all pipeline metrics (useful for testing)"""
        try:
            stages = [
                "market_ticks",
                "signals",
                "signals_validated", 
                "signals_rejected",
                "orders",
                "portfolio_updates"
            ]
            
            keys_to_delete = []
            for stage in stages:
                keys_to_delete.extend([
                    f"pipeline:{stage}:{self.broker_namespace}:last",
                    f"pipeline:{stage}:{self.broker_namespace}:count"
                ])
            
            if keys_to_delete:
                await self.redis.delete(*keys_to_delete)
                
            self.logger.info("Pipeline metrics reset",
                           keys_deleted=len(keys_to_delete),
                           broker=self.broker_namespace)
                           
        except Exception as e:
            self.logger.error("Failed to reset metrics",
                            error=str(e),
                            broker=self.broker_namespace)

    async def set_strategy_count(self, broker: str, count: int) -> None:
        """Record the number of active strategies targeting a broker.

        Stored as pipeline:strategies:{broker}:count with a TTL for easy lookup by validators.
        """
        try:
            from .metrics_registry import MetricsRegistry
            key = MetricsRegistry.strategies_count(broker)
            await self.redis.setex(key, self.metrics_ttl, str(int(count)))
            self.logger.debug("Set strategy count", broker=broker, count=count)
        except Exception as e:
            self.logger.error("Failed to set strategy count", broker=broker, error=str(e))
