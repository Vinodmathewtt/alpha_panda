"""
Continuous pipeline monitoring and alerting - MULTI-BROKER VERSION
"""

import asyncio
import json
from datetime import datetime
from typing import Optional, Dict

from core.logging import get_monitoring_logger_safe
from core.market_hours.market_hours_checker import MarketHoursChecker
from .pipeline_validator import PipelineValidator


class PipelineMonitor:
    """Continuous pipeline monitoring and alerting for all active brokers"""
    
    def __init__(self, settings, redis_client, market_hours_checker: MarketHoursChecker = None):
        self.settings = settings
        self.redis = redis_client
        # Use injected MarketHoursChecker or create new instance as fallback
        if market_hours_checker is None:
            market_hours_checker = MarketHoursChecker()
        
        # FIXED: Create validators for each active broker
        self.validators = {}
        for broker in settings.active_brokers:
            self.validators[broker] = PipelineValidator(settings, redis_client, market_hours_checker, broker)
        
        self.logger = get_monitoring_logger_safe("pipeline_monitor")
        
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Get monitoring interval from settings
        self.monitor_interval = getattr(settings.monitoring, 'health_check_interval', 30.0) if hasattr(settings, 'monitoring') else 30.0
    
    async def start(self):
        """Start pipeline monitoring"""
        if self._running:
            self.logger.warning("Pipeline monitor already running", 
                              active_brokers=self.settings.active_brokers)
            return
            
        self.logger.info("Starting pipeline monitoring",
                        monitor_interval=self.monitor_interval,
                        active_brokers=self.settings.active_brokers)
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        
        self.logger.info("Pipeline monitoring started", 
                        active_brokers=self.settings.active_brokers)
    
    async def stop(self):
        """Stop pipeline monitoring"""
        if not self._running:
            return
            
        self.logger.info("Stopping pipeline monitoring", 
                        active_brokers=self.settings.active_brokers)
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        
        self.logger.info("Pipeline monitoring stopped", 
                        active_brokers=self.settings.active_brokers)
    
    async def _monitoring_loop(self):
        """Main monitoring loop for all active brokers"""
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        while self._running:
            try:
                # Run validation for each active broker
                all_results = {}
                overall_healthy = True
                
                for broker, validator in self.validators.items():
                    validation_results = await validator.validate_end_to_end_flow()
                    all_results[broker] = validation_results
                    
                    # Track overall health
                    broker_health = validation_results.get("overall_health", "unknown")
                    if broker_health not in ["healthy", "warning"]:
                        overall_healthy = False
                
                    
                    # Log broker-specific results
                    if broker_health == "healthy":
                        self.logger.info("Pipeline validation passed",
                                       validation_id=validation_results.get("validation_id"),
                                       overall_health=broker_health,
                                       broker=broker)
                    elif broker_health == "startup":
                        self.logger.debug("Pipeline validation in startup grace period",
                                        validation_id=validation_results.get("validation_id"),
                                        overall_health=broker_health,
                                        broker=broker)
                    elif broker_health == "warning":
                        self.logger.warning("Pipeline validation shows warnings",
                                          validation_id=validation_results.get("validation_id"),
                                          overall_health=broker_health,
                                          bottlenecks=validation_results.get("bottlenecks", []),
                                          recommendations=validation_results.get("recommendations", []),
                                          broker=broker)
                    else:
                        self.logger.error("CRITICAL: Pipeline validation failed",
                                        validation_id=validation_results.get("validation_id"),
                                        overall_health=broker_health,
                                        bottlenecks=validation_results.get("bottlenecks", []),
                                        recommendations=validation_results.get("recommendations", []),
                                        broker=broker)
                    
                    # Store broker-specific results with TTL
                    validation_key = f"pipeline:validation:{broker}"
                    await self.redis.setex(
                        validation_key,
                        300,  # 5 min TTL
                        json.dumps(validation_results, default=str)
                    )
                    
                    # Store health history for trending
                    await self._store_health_history(validation_results, broker)
                
                # Store aggregated results
                aggregated_results = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "overall_healthy": overall_healthy,
                    "active_brokers": self.settings.active_brokers,
                    "broker_results": all_results
                }
                
                await self.redis.setex(
                    "pipeline:validation:aggregated",
                    300,
                    json.dumps(aggregated_results, default=str)
                )
                
                # Reset failure counter on success
                consecutive_failures = 0
                
                # Wait for next monitoring cycle
                await asyncio.sleep(self.monitor_interval)
                
            except asyncio.CancelledError:
                self.logger.info("Pipeline monitoring cancelled", 
                                active_brokers=self.settings.active_brokers)
                break
            except Exception as e:
                consecutive_failures += 1
                self.logger.error("Pipeline monitoring error",
                                error=str(e),
                                consecutive_failures=consecutive_failures,
                                active_brokers=self.settings.active_brokers)
                
                # If we have too many consecutive failures, increase sleep time
                if consecutive_failures >= max_consecutive_failures:
                    sleep_time = min(300, self.monitor_interval * consecutive_failures)  # Max 5 minutes
                    self.logger.warning("Too many consecutive monitoring failures, backing off",
                                      sleep_time=sleep_time,
                                      active_brokers=self.settings.active_brokers)
                    await asyncio.sleep(sleep_time)
                else:
                    await asyncio.sleep(30)  # Short retry delay
    
    async def _store_health_history(self, validation_results: dict, broker: str):
        """Store health history for trending analysis"""
        try:
            timestamp = datetime.utcnow()
            
            # Store simplified health record
            health_record = {
                "timestamp": timestamp.isoformat(),
                "overall_health": validation_results.get("overall_health", "unknown"),
                "broker": broker,
                "stage_health": {
                    stage_name: stage_data.get("healthy", False)
                    for stage_name, stage_data in validation_results.get("stages", {}).items()
                },
                "bottleneck_count": len(validation_results.get("bottlenecks", []))
            }
            
            # Store in Redis list (keep last 100 records per broker)
            history_key = f"pipeline:health_history:{broker}"
            
            # Add new record
            await self.redis.lpush(history_key, json.dumps(health_record, default=str))
            
            # Trim to keep only last 100 records
            await self.redis.ltrim(history_key, 0, 99)
            
            # Set expiration (24 hours)
            await self.redis.expire(history_key, 86400)
            
        except Exception as e:
            self.logger.error("Failed to store health history",
                            error=str(e),
                            broker=broker)
    
    async def get_health_history(self, broker: str = None, limit: int = 50) -> dict:
        """Get recent health history for specific broker or all brokers"""
        try:
            if broker:
                # Get history for specific broker
                history_key = f"pipeline:health_history:{broker}"
                history_data = await self.redis.lrange(history_key, 0, limit - 1)
                return {broker: [json.loads(record) for record in history_data]}
            else:
                # Get history for all active brokers
                all_history = {}
                for active_broker in self.settings.active_brokers:
                    history_key = f"pipeline:health_history:{active_broker}"
                    history_data = await self.redis.lrange(history_key, 0, limit - 1)
                    all_history[active_broker] = [json.loads(record) for record in history_data]
                return all_history
            
        except Exception as e:
            self.logger.error("Failed to get health history",
                            error=str(e),
                            broker=broker)
            return {}
    
    async def get_current_status(self, broker: str = None) -> dict:
        """Get current pipeline monitoring status for specific broker or all brokers"""
        try:
            if broker:
                # Get status for specific broker
                validation_key = f"pipeline:validation:{broker}"
                current_data = await self.redis.get(validation_key)
                
                if current_data:
                    return {broker: json.loads(current_data)}
                else:
                    return {
                        broker: {
                            "broker": broker,
                            "status": "no_recent_data",
                            "message": "No recent validation data available"
                        }
                    }
            else:
                # Get aggregated status for all brokers
                aggregated_data = await self.redis.get("pipeline:validation:aggregated")
                if aggregated_data:
                    return json.loads(aggregated_data)
                else:
                    return {
                        "status": "no_recent_data",
                        "message": "No recent validation data available",
                        "active_brokers": self.settings.active_brokers
                    }
                
        except Exception as e:
            self.logger.error("Failed to get current status",
                            error=str(e),
                            broker=broker)
            return {
                "status": "error",
                "error": str(e),
                "active_brokers": self.settings.active_brokers
            }