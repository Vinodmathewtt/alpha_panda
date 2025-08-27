"""
End-to-end pipeline validation and health monitoring - MULTI-BROKER VERSION
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import uuid

from core.logging import get_monitoring_logger_safe
from core.market_hours.market_hours_checker import MarketHoursChecker


class PipelineValidator:
    """Validates end-to-end pipeline flow and detects bottlenecks for specific broker"""
    
    def __init__(self, settings, redis_client, market_hours_checker: Optional[MarketHoursChecker] = None, broker: str = None):
        self.settings = settings
        self.redis = redis_client
        # FIXED: Accept broker as parameter instead of using deprecated broker_namespace
        self.broker = broker or settings.active_brokers[0]  # Default to first active broker
        self.logger = get_monitoring_logger_safe("pipeline_validator")
        self.start_time = datetime.utcnow()  # Track service startup time
        
        # Market hours checker for market status awareness
        self.market_hours_checker = market_hours_checker or MarketHoursChecker()
        
        # Default thresholds (can be overridden by settings)
        self.thresholds = {
            "market_data_latency": getattr(settings.monitoring, 'market_data_latency_threshold', 1.0) if hasattr(settings, 'monitoring') else 1.0,
            "signal_processing_latency": 5.0,
            "risk_validation_latency": 2.0, 
            "order_execution_latency": 10.0,
            "portfolio_update_latency": 3.0
        }
        
        # Configurable grace period for startup - avoid false alarms
        self.startup_grace_period_seconds = getattr(settings.monitoring, 'startup_grace_period_seconds', 30.0) if hasattr(settings, 'monitoring') else 30.0
        
    async def validate_end_to_end_flow(self) -> Dict[str, Any]:
        """Validate complete pipeline flow from market data to orders for this broker"""
        validation_id = str(uuid.uuid4())
        
        self.logger.info("Starting end-to-end pipeline validation",
                        validation_id=validation_id,
                        broker=self.broker)
        
        results = {
            "validation_id": validation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "broker": self.broker,  # FIXED: Use broker instead of broker_namespace
            "stages": {},
            "bottlenecks": [],
            "recommendations": []
        }
        
        # Check if we're in startup grace period
        if self._in_startup_grace_period():
            self.logger.info("Service in startup grace period, skipping detailed validation",
                           broker=self.broker,
                           grace_period_seconds=self.startup_grace_period_seconds)
            results["overall_health"] = "startup"
            results["message"] = "Service starting up, validation deferred"
            return results
        
        try:
            # Stage 1: Market Data Flow
            market_data_health = await self._validate_market_data_flow()
            results["stages"]["market_data"] = market_data_health
            
            # Stage 2: Signal Generation (broker-specific)
            signal_health = await self._validate_signal_generation()
            results["stages"]["signal_generation"] = signal_health
            
            # Stage 3: Risk Validation (broker-specific)  
            risk_health = await self._validate_risk_management()
            results["stages"]["risk_validation"] = risk_health
            
            # Stage 4: Order Execution (broker-specific)
            execution_health = await self._validate_order_execution()
            results["stages"]["order_execution"] = execution_health
            
            # Stage 5: Portfolio Updates (broker-specific)
            portfolio_health = await self._validate_portfolio_updates()
            results["stages"]["portfolio_updates"] = portfolio_health
            
            # Determine overall health and identify bottlenecks
            overall_health, bottlenecks, recommendations = self._analyze_pipeline_health(results["stages"])
            
            results["overall_health"] = overall_health
            results["bottlenecks"] = bottlenecks
            results["recommendations"] = recommendations
            
            self.logger.info("Pipeline validation completed",
                           validation_id=validation_id,
                           overall_health=overall_health,
                           broker=self.broker,
                           bottleneck_count=len(bottlenecks))
            
        except Exception as e:
            self.logger.error("Pipeline validation failed",
                            validation_id=validation_id,
                            error=str(e),
                            broker=self.broker)
            results["overall_health"] = "error"
            results["error"] = str(e)
            
        return results
    
    def _in_startup_grace_period(self) -> bool:
        """Check if service is in startup grace period"""
        uptime_seconds = (datetime.utcnow() - self.start_time).total_seconds()
        return uptime_seconds < self.startup_grace_period_seconds
    
    async def _validate_market_data_flow(self) -> Dict[str, Any]:
        """Validate market data ingestion and distribution (shared across brokers)"""
        try:
            # Check for recent market ticks
            last_tick_key = "alpha_panda:metrics:market_data:last_tick_time"
            last_tick_time_str = await self.redis.get(last_tick_key)
            
            if not last_tick_time_str:
                return {
                    "healthy": False,
                    "latency_ms": None,
                    "issue": "No market data ticks found",
                    "recommendation": "Check market feed service and authentication"
                }
            
            # Calculate latency
            last_tick_time = datetime.fromisoformat(last_tick_time_str.decode())
            latency_seconds = (datetime.utcnow() - last_tick_time).total_seconds()
            
            # Check if market data is stale
            is_healthy = latency_seconds <= self.thresholds["market_data_latency"]
            
            result = {
                "healthy": is_healthy,
                "latency_ms": latency_seconds * 1000,
                "threshold_ms": self.thresholds["market_data_latency"] * 1000
            }
            
            if not is_healthy:
                result["issue"] = f"Market data latency too high: {latency_seconds:.2f}s"
                result["recommendation"] = "Check market feed service connectivity and performance"
            
            return result
            
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "recommendation": "Check Redis connectivity and market data service"
            }
    
    async def _validate_signal_generation(self) -> Dict[str, Any]:
        """Validate signal generation for this specific broker"""
        try:
            # Check broker-specific signal generation metrics
            signals_key = f"alpha_panda:metrics:{self.broker}:signals:last_generated"
            signal_count_key = f"alpha_panda:metrics:{self.broker}:signals:count_last_5min"
            
            last_signal_time_str = await self.redis.get(signals_key)
            signal_count_str = await self.redis.get(signal_count_key)
            
            result = {
                "healthy": True,
                "broker": self.broker,
                "last_signal_time": last_signal_time_str.decode() if last_signal_time_str else None,
                "signals_last_5min": int(signal_count_str) if signal_count_str else 0
            }
            
            # During market hours, expect some signal activity
            if self.market_hours_checker.is_market_open():
                if not last_signal_time_str:
                    result["healthy"] = False
                    result["issue"] = f"No signals generated for {self.broker} during market hours"
                    result["recommendation"] = f"Check strategy runner and {self.broker} broker configuration"
                else:
                    # Check signal latency
                    last_signal_time = datetime.fromisoformat(last_signal_time_str.decode())
                    signal_latency = (datetime.utcnow() - last_signal_time).total_seconds()
                    
                    if signal_latency > self.thresholds["signal_processing_latency"]:
                        result["healthy"] = False
                        result["latency_ms"] = signal_latency * 1000
                        result["issue"] = f"Signal generation latency too high for {self.broker}: {signal_latency:.2f}s"
                        result["recommendation"] = f"Check strategy runner performance for {self.broker}"
            
            return result
            
        except Exception as e:
            return {
                "healthy": False,
                "broker": self.broker,
                "error": str(e),
                "recommendation": f"Check Redis connectivity and strategy runner service for {self.broker}"
            }
    
    async def _validate_risk_management(self) -> Dict[str, Any]:
        """Validate risk management for this specific broker"""
        try:
            # Check broker-specific risk validation metrics
            risk_key = f"alpha_panda:metrics:{self.broker}:risk:last_validation"
            risk_count_key = f"alpha_panda:metrics:{self.broker}:risk:validations_last_5min"
            
            last_risk_time_str = await self.redis.get(risk_key)
            risk_count_str = await self.redis.get(risk_count_key)
            
            result = {
                "healthy": True,
                "broker": self.broker,
                "last_validation_time": last_risk_time_str.decode() if last_risk_time_str else None,
                "validations_last_5min": int(risk_count_str) if risk_count_str else 0
            }
            
            # Check risk validation latency if we have recent data
            if last_risk_time_str:
                last_risk_time = datetime.fromisoformat(last_risk_time_str.decode())
                risk_latency = (datetime.utcnow() - last_risk_time).total_seconds()
                
                if risk_latency > self.thresholds["risk_validation_latency"]:
                    result["healthy"] = False
                    result["latency_ms"] = risk_latency * 1000
                    result["issue"] = f"Risk validation latency too high for {self.broker}: {risk_latency:.2f}s"
                    result["recommendation"] = f"Check risk manager service performance for {self.broker}"
            
            return result
            
        except Exception as e:
            return {
                "healthy": False,
                "broker": self.broker,
                "error": str(e),
                "recommendation": f"Check Redis connectivity and risk manager service for {self.broker}"
            }
    
    async def _validate_order_execution(self) -> Dict[str, Any]:
        """Validate order execution for this specific broker"""
        try:
            # Check broker-specific order execution metrics
            execution_key = f"alpha_panda:metrics:{self.broker}:orders:last_execution"
            execution_count_key = f"alpha_panda:metrics:{self.broker}:orders:count_last_5min"
            
            last_execution_time_str = await self.redis.get(execution_key)
            execution_count_str = await self.redis.get(execution_count_key)
            
            result = {
                "healthy": True,
                "broker": self.broker,
                "last_execution_time": last_execution_time_str.decode() if last_execution_time_str else None,
                "executions_last_5min": int(execution_count_str) if execution_count_str else 0
            }
            
            # Check execution latency if we have recent data
            if last_execution_time_str:
                last_execution_time = datetime.fromisoformat(last_execution_time_str.decode())
                execution_latency = (datetime.utcnow() - last_execution_time).total_seconds()
                
                if execution_latency > self.thresholds["order_execution_latency"]:
                    result["healthy"] = False
                    result["latency_ms"] = execution_latency * 1000
                    result["issue"] = f"Order execution latency too high for {self.broker}: {execution_latency:.2f}s"
                    result["recommendation"] = f"Check trading engine service performance for {self.broker}"
            
            return result
            
        except Exception as e:
            return {
                "healthy": False,
                "broker": self.broker,
                "error": str(e),
                "recommendation": f"Check Redis connectivity and trading engine service for {self.broker}"
            }
    
    async def _validate_portfolio_updates(self) -> Dict[str, Any]:
        """Validate portfolio updates for this specific broker"""
        try:
            # Check broker-specific portfolio update metrics
            portfolio_key = f"alpha_panda:metrics:{self.broker}:portfolio:last_update"
            portfolio_count_key = f"alpha_panda:metrics:{self.broker}:portfolio:updates_last_5min"
            
            last_update_time_str = await self.redis.get(portfolio_key)
            update_count_str = await self.redis.get(portfolio_count_key)
            
            result = {
                "healthy": True,
                "broker": self.broker,
                "last_update_time": last_update_time_str.decode() if last_update_time_str else None,
                "updates_last_5min": int(update_count_str) if update_count_str else 0
            }
            
            # Check portfolio update latency if we have recent data
            if last_update_time_str:
                last_update_time = datetime.fromisoformat(last_update_time_str.decode())
                portfolio_latency = (datetime.utcnow() - last_update_time).total_seconds()
                
                if portfolio_latency > self.thresholds["portfolio_update_latency"]:
                    result["healthy"] = False
                    result["latency_ms"] = portfolio_latency * 1000
                    result["issue"] = f"Portfolio update latency too high for {self.broker}: {portfolio_latency:.2f}s"
                    result["recommendation"] = f"Check portfolio manager service performance for {self.broker}"
            
            return result
            
        except Exception as e:
            return {
                "healthy": False,
                "broker": self.broker,
                "error": str(e),
                "recommendation": f"Check Redis connectivity and portfolio manager service for {self.broker}"
            }
    
    def _analyze_pipeline_health(self, stages: Dict[str, Dict[str, Any]]) -> tuple:
        """Analyze overall pipeline health and identify bottlenecks"""
        bottlenecks = []
        recommendations = []
        
        # Count healthy stages
        healthy_stages = sum(1 for stage in stages.values() if stage.get("healthy", False))
        total_stages = len(stages)
        
        # Identify specific bottlenecks
        for stage_name, stage_data in stages.items():
            if not stage_data.get("healthy", False):
                bottlenecks.append({
                    "stage": stage_name,
                    "issue": stage_data.get("issue", "Unknown issue"),
                    "broker": self.broker
                })
                
                if "recommendation" in stage_data:
                    recommendations.append({
                        "stage": stage_name,
                        "recommendation": stage_data["recommendation"],
                        "broker": self.broker
                    })
        
        # Determine overall health
        if healthy_stages == total_stages:
            overall_health = "healthy"
        elif healthy_stages >= total_stages * 0.8:  # 80% threshold
            overall_health = "warning"
        elif healthy_stages >= total_stages * 0.6:  # 60% threshold
            overall_health = "degraded"
        else:
            overall_health = "critical"
        
        return overall_health, bottlenecks, recommendations