import asyncio
from datetime import datetime, timedelta, UTC
from typing import Dict, List, Any, Optional, AsyncGenerator
import json
import redis.asyncio as redis

from core.config.settings import Settings
from core.health.health_checker import ServiceHealthChecker
from core.monitoring import PipelineMonitor
from api.schemas.responses import ServiceInfo, ServiceStatus, HealthStatus

class DashboardService:
    """Service for aggregating dashboard data from various sources - MULTI-BROKER VERSION"""
    
    def __init__(
        self,
        settings: Settings,
        redis_client: redis.Redis,
        health_checker: ServiceHealthChecker,
        pipeline_monitor: PipelineMonitor
    ):
        self.settings = settings
        self.redis = redis_client
        self.health_checker = health_checker
        self.pipeline_monitor = pipeline_monitor
        # FIXED: Remove single broker reference, use active_brokers instead
    
    async def get_health_summary(self) -> Dict[str, Any]:
        """Get overall system health summary for all active brokers"""
        try:
            # Get health data for all brokers
            broker_health = {}
            overall_healthy = True
            
            for broker in self.settings.active_brokers:
                broker_health_data = await self._get_broker_health(broker)
                broker_health[broker] = broker_health_data
                if not broker_health_data.get("healthy", False):
                    overall_healthy = False
            
            # Add system-wide metrics
            uptime = await self._get_system_uptime()
            last_restart = await self._get_last_restart_time()
            
            return {
                "overall_healthy": overall_healthy,
                "active_brokers": self.settings.active_brokers,
                "broker_health": broker_health,
                "uptime_seconds": uptime,
                "last_restart": last_restart,
                "timestamp": datetime.now(UTC).isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
                "active_brokers": self.settings.active_brokers
            }
    
    async def _get_broker_health(self, broker: str) -> Dict[str, Any]:
        """Get health data for a specific broker"""
        try:
            # Get pipeline status for this broker
            pipeline_status = await self.pipeline_monitor.get_current_status(broker)
            broker_pipeline_data = pipeline_status.get(broker, {})
            
            # Determine broker health
            healthy = broker_pipeline_data.get("overall_health", "unknown") in ["healthy", "warning"]
            
            return {
                "healthy": healthy,
                "broker": broker,
                "pipeline_health": broker_pipeline_data.get("overall_health", "unknown"),
                "last_validation": broker_pipeline_data.get("timestamp"),
                "bottlenecks": len(broker_pipeline_data.get("bottlenecks", [])),
                "services": await self._get_broker_service_health(broker)
            }
        except Exception as e:
            return {
                "healthy": False,
                "broker": broker,
                "error": str(e)
            }
    
    async def _get_broker_service_health(self, broker: str) -> Dict[str, Any]:
        """Get service-level health metrics for a specific broker"""
        services = [
            "strategy_runner",
            "risk_manager",
            "paper_trading",
            "zerodha_trading",
        ]
        service_health = {}
        
        for service in services:
            try:
                # Check service-specific metrics for this broker
                metrics_key = f"alpha_panda:metrics:{broker}:{service}:last_activity"
                last_activity = await self.redis.get(metrics_key)
                
                if last_activity:
                    last_activity_time = datetime.fromisoformat(last_activity.decode())
                    latency = (datetime.now(UTC) - last_activity_time).total_seconds()
                    service_health[service] = {
                        "healthy": latency < 60,  # Less than 1 minute
                        "last_activity": last_activity.decode(),
                        "latency_seconds": latency
                    }
                else:
                    service_health[service] = {
                        "healthy": False,
                        "last_activity": None,
                        "message": "No recent activity"
                    }
            except Exception as e:
                service_health[service] = {
                    "healthy": False,
                    "error": str(e)
                }
        
        return service_health
    
    async def get_service_metrics(self, service_name: str, broker: str = None) -> Dict[str, Any]:
        """Get performance metrics for a specific service and broker"""
        try:
            if broker:
                # Get metrics for specific broker
                metrics_key = f"alpha_panda:metrics:{broker}:{service_name}:performance"
                metrics_data = await self.redis.get(metrics_key)
                
                if metrics_data:
                    return {
                        "broker": broker,
                        "service": service_name,
                        "metrics": json.loads(metrics_data)
                    }
                else:
                    return {
                        "broker": broker,
                        "service": service_name,
                        "message": f"No metrics found for {service_name} on {broker}"
                    }
            else:
                # Get metrics for all active brokers
                all_metrics = {}
                for active_broker in self.settings.active_brokers:
                    metrics_key = f"alpha_panda:metrics:{active_broker}:{service_name}:performance"
                    metrics_data = await self.redis.get(metrics_key)
                    
                    if metrics_data:
                        all_metrics[active_broker] = json.loads(metrics_data)
                    else:
                        all_metrics[active_broker] = {"message": f"No metrics found for {service_name}"}
                
                return {
                    "service": service_name,
                    "active_brokers": self.settings.active_brokers,
                    "broker_metrics": all_metrics
                }
                
        except Exception as e:
            return {
                "service": service_name,
                "broker": broker,
                "error": str(e)
            }
    
    async def get_trading_summary(self, broker: str = None, timeframe: str = "1h") -> Dict[str, Any]:
        """Get trading activity summary for specific broker or all brokers"""
        try:
            if broker:
                return await self._get_broker_trading_summary(broker, timeframe)
            else:
                # Get summary for all active brokers
                all_summaries = {}
                for active_broker in self.settings.active_brokers:
                    all_summaries[active_broker] = await self._get_broker_trading_summary(active_broker, timeframe)
                
                return {
                    "timeframe": timeframe,
                    "active_brokers": self.settings.active_brokers,
                    "broker_summaries": all_summaries
                }
                
        except Exception as e:
            return {
                "error": str(e),
                "broker": broker,
                "timeframe": timeframe
            }
    
    async def _get_broker_trading_summary(self, broker: str, timeframe: str) -> Dict[str, Any]:
        """Get trading summary for a specific broker"""
        try:
            # Calculate time range
            now = datetime.now(UTC)
            if timeframe == "1h":
                start_time = now - timedelta(hours=1)
            elif timeframe == "1d":
                start_time = now - timedelta(days=1)
            elif timeframe == "1w":
                start_time = now - timedelta(weeks=1)
            else:
                start_time = now - timedelta(hours=1)  # Default
            
            # Get broker-specific trading metrics
            signals_key = f"alpha_panda:metrics:{broker}:signals:count_{timeframe}"
            orders_key = f"alpha_panda:metrics:{broker}:orders:count_{timeframe}"
            pnl_key = f"alpha_panda:metrics:{broker}:pnl:total_{timeframe}"
            
            signals_count = await self.redis.get(signals_key)
            orders_count = await self.redis.get(orders_key)
            pnl_total = await self.redis.get(pnl_key)
            
            return {
                "broker": broker,
                "timeframe": timeframe,
                "signals_generated": int(signals_count) if signals_count else 0,
                "orders_executed": int(orders_count) if orders_count else 0,
                "pnl_total": float(pnl_total) if pnl_total else 0.0,
                "start_time": start_time.isoformat(),
                "end_time": now.isoformat()
            }
            
        except Exception as e:
            return {
                "broker": broker,
                "timeframe": timeframe,
                "error": str(e)
            }
    
    async def get_portfolio_summary(self, broker: str = None) -> Dict[str, Any]:
        """Get portfolio summary for specific broker or all brokers"""
        try:
            if broker:
                # Get portfolio for specific broker
                portfolio_key = f"portfolio:{broker}:summary"
                portfolio_data = await self.redis.get(portfolio_key)
                
                if portfolio_data:
                    return {
                        "broker": broker,
                        "portfolio": json.loads(portfolio_data)
                    }
                else:
                    return {
                        "broker": broker,
                        "message": f"No portfolio data found for {broker}"
                    }
            else:
                # Get portfolios for all active brokers
                all_portfolios = {}
                for active_broker in self.settings.active_brokers:
                    portfolio_key = f"portfolio:{active_broker}:summary"
                    portfolio_data = await self.redis.get(portfolio_key)
                    
                    if portfolio_data:
                        all_portfolios[active_broker] = json.loads(portfolio_data)
                    else:
                        all_portfolios[active_broker] = {"message": f"No portfolio data found"}
                
                return {
                    "active_brokers": self.settings.active_brokers,
                    "broker_portfolios": all_portfolios
                }
                
        except Exception as e:
            return {
                "error": str(e),
                "broker": broker
            }
    
    async def _get_system_uptime(self) -> float:
        """Get system uptime in seconds"""
        try:
            uptime_key = "alpha_panda:system:start_time"
            start_time_str = await self.redis.get(uptime_key)
            
            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str.decode())
                uptime = (datetime.now(UTC) - start_time).total_seconds()
                return uptime
            
            return 0.0
        except Exception:
            return 0.0
    
    async def _get_last_restart_time(self) -> Optional[str]:
        """Get last system restart time"""
        try:
            restart_key = "alpha_panda:system:last_restart"
            restart_time = await self.redis.get(restart_key)
            return restart_time.decode() if restart_time else None
        except Exception:
            return None
    
    async def stream_health_updates(self, broker: str = None) -> AsyncGenerator[str, None]:
        """Stream real-time health updates for specific broker or all brokers"""
        try:
            while True:
                if broker:
                    health_data = await self._get_broker_health(broker)
                    yield f"data: {json.dumps(health_data)}\n\n"
                else:
                    health_summary = await self.get_health_summary()
                    yield f"data: {json.dumps(health_summary)}\n\n"
                
                # Wait before next update
                await asyncio.sleep(5)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            error_data = {"error": str(e), "broker": broker}
            yield f"data: {json.dumps(error_data)}\n\n"
