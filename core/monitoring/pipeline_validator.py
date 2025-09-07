"""
End-to-end pipeline validation and health monitoring - MULTI-BROKER VERSION
"""

import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import uuid

from core.logging import get_monitoring_logger_safe
try:
    from prometheus_client import Counter  # type: ignore
    _VALIDATOR_WARNINGS = Counter(
        'validator_warnings_total',
        'Total validator warnings by stage and broker',
        ['stage', 'broker', 'issue']
    )
except Exception:
    _VALIDATOR_WARNINGS = None
from core.market_hours.market_hours_checker import MarketHoursChecker
from .metrics_registry import MetricsRegistry


class PipelineValidator:
    """Validates end-to-end pipeline flow and detects bottlenecks for specific broker"""
    
    def __init__(self, settings, redis_client, market_hours_checker: Optional[MarketHoursChecker] = None, broker: str = None):
        self.settings = settings
        self.redis = redis_client
        # FIXED: Accept broker as parameter instead of using deprecated broker_namespace
        self.broker = broker or settings.active_brokers[0]  # Default to first active broker
        self.logger = get_monitoring_logger_safe("pipeline_validator")
        self.start_time = datetime.now(timezone.utc)  # Track service startup time (aware)
        
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

        # Cache effective trading enablement for the given broker
        self._trading_enabled = self._is_trading_enabled(self.broker)
        
    async def validate_end_to_end_flow(self) -> Dict[str, Any]:
        """Validate complete pipeline flow from market data to orders for this broker"""
        validation_id = str(uuid.uuid4())
        
        self.logger.info("Starting end-to-end pipeline validation",
                        validation_id=validation_id,
                        broker=self.broker)
        
        results = {
            "validation_id": validation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            # Quick Redis connectivity check to surface explicit infra issues
            try:
                if hasattr(self.redis, 'ping'):
                    await self.redis.ping()
            except Exception as re:
                results["overall_health"] = "error"
                results["bottlenecks"] = [{
                    "stage": "infrastructure",
                    "issue": "redis_unavailable",
                    "broker": self.broker,
                    "details": str(re)
                }]
                results["message"] = "Redis connectivity issue detected"
                self.logger.error("Redis connectivity issue during validation", validation_id=validation_id, broker=self.broker, error=str(re))
                return results
            # Market-aware: if market is closed, return idle state to reduce noise
            if not self.market_hours_checker.is_market_open():
                results["overall_health"] = "idle"
                results["message"] = "Market closed; validator in idle mode"
                # We still try to fetch minimal stage info without raising alerts
                stages = {}
                stages["market_data"] = await self._validate_market_data_flow()
                stages["signal_generation"] = {"healthy": True, "broker": self.broker, "skipped": True, "reason": "market_closed"}
                stages["risk_validation"] = {"healthy": True, "broker": self.broker, "skipped": True, "reason": "market_closed"}
                # If trading disabled, also mark order/portfolio as skipped; else mark idle
                if not self._trading_enabled:
                    stages["order_execution"] = {"healthy": True, "broker": self.broker, "skipped": True, "reason": "trading_disabled"}
                    stages["portfolio_updates"] = {"healthy": True, "broker": self.broker, "skipped": True, "reason": "trading_disabled"}
                else:
                    stages["order_execution"] = {"healthy": True, "broker": self.broker, "skipped": True, "reason": "market_closed"}
                    stages["portfolio_updates"] = {"healthy": True, "broker": self.broker, "skipped": True, "reason": "market_closed"}
                results["stages"] = stages
                self.logger.info("Pipeline validation idle (market closed)", validation_id=validation_id, broker=self.broker)
                return results

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

    # ---- Helpers: robust Redis value decoding and timestamp parsing ----
    def _decode_bytes(self, raw: Any) -> Optional[str]:
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            try:
                return raw.decode()
            except Exception:
                return None
        return str(raw)

    def _parse_timestamp_from_json_or_iso(self, value: str) -> Optional[datetime]:
        try:
            data = json.loads(value)
            if isinstance(data, dict) and isinstance(data.get("timestamp"), str):
                dt = datetime.fromisoformat(data["timestamp"])
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
        try:
            dt = datetime.fromisoformat(value)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def _in_startup_grace_period(self) -> bool:
        """Check if service is in startup grace period"""
        uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        return uptime_seconds < self.startup_grace_period_seconds
    
    async def _validate_market_data_flow(self) -> Dict[str, Any]:
        """Validate market data ingestion and distribution (shared across brokers)"""
        try:
            # Skip strict latency checks when market is closed to avoid false positives
            if not self.market_hours_checker.is_market_open():
                return {
                    "healthy": True,
                    "latency_ms": None,
                    "message": "Market closed: skipping market-data latency checks",
                    "reason": "market_closed"
                }
            # Check for recent market ticks - FIXED: Use pipeline metrics format with shared "market" namespace
            last_tick_key = MetricsRegistry.market_ticks_last()
            try:
                last_tick_time_raw = await self.redis.get(last_tick_key)
            except Exception as re:
                return {"healthy": False, "issue": "redis_unavailable", "error": str(re)}
            last_tick_time_str = self._decode_bytes(last_tick_time_raw)
            
            if not last_tick_time_str:
                return {
                    "healthy": False,
                    "latency_ms": None,
                    "issue": "No market data ticks found",
                    "recommendation": "Check market feed service and authentication"
                }
            
            # Calculate latency - FIXED: Parse JSON structure from PipelineMetricsCollector
            last_tick_time = self._parse_timestamp_from_json_or_iso(last_tick_time_str)
            if not last_tick_time:
                return {"healthy": False, "issue": "metrics_parse_error", "latency_ms": None}
            latency_seconds = (datetime.now(timezone.utc) - last_tick_time).total_seconds()
            
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
                try:
                    if _VALIDATOR_WARNINGS is not None:
                        _VALIDATOR_WARNINGS.labels(stage="market_data", broker=self.broker, issue=result.get("issue", "latency")).inc()
                except Exception:
                    pass
            
            return result
            
        except Exception as e:
            return {"healthy": False, "issue": "validation_error", "error": str(e)}
        
    async def _validate_signal_generation(self) -> Dict[str, Any]:
        """Validate signal generation for this specific broker"""
        try:
            # Early short-circuit: when market is open, trading enabled, and no strategies target this broker
            if self.market_hours_checker.is_market_open() and self._trading_enabled:
                try:
                    from .metrics_registry import MetricsRegistry
                    _raw = await self.redis.get(MetricsRegistry.strategies_count(self.broker))
                    if _raw is None:
                        active = 0
                    else:
                        s = _raw.decode() if isinstance(_raw, (bytes, bytearray)) else str(_raw)
                        active = int(s)
                except Exception:
                    active = None
                if active == 0:
                    return {
                        "healthy": True,
                        "broker": self.broker,
                        "last_signal_time": None,
                        "signals_last_5min": 0,
                        "info": f"No active strategies configured for {self.broker}",
                    }

            # Check broker-specific signal generation metrics - FIXED: Use pipeline: prefix to match PipelineMetricsCollector
            signals_key = MetricsRegistry.signals_last(self.broker)
            signal_count_key = MetricsRegistry.signals_count(self.broker)
            
            try:
                last_signal_time_raw = await self.redis.get(signals_key)
                signal_count_raw = await self.redis.get(signal_count_key)
            except Exception as re:
                return {"healthy": False, "broker": self.broker, "issue": "redis_unavailable", "error": str(re)}
            last_signal_time_str = self._decode_bytes(last_signal_time_raw)
            signal_count_str = self._decode_bytes(signal_count_raw)
            
            result = {
                "healthy": True,
                "broker": self.broker,
                "last_signal_time": None,  # Will be set later if data exists
                "signals_last_5min": int(signal_count_str) if signal_count_str else 0
            }
            
            # During market hours, expect some signal activity if trading path is enabled
            if self.market_hours_checker.is_market_open() and self._trading_enabled:
                if not last_signal_time_str:
                    # If no active strategies target this broker, do not warn
                    try:
                        from .metrics_registry import MetricsRegistry
                        strat_count_key = MetricsRegistry.strategies_count(self.broker)
                        strat_count_raw = await self.redis.get(strat_count_key)
                        if strat_count_raw is None:
                            active_strategies = 0
                        else:
                            if isinstance(strat_count_raw, (bytes, bytearray)):
                                strat_count_str = strat_count_raw.decode()
                            else:
                                strat_count_str = str(strat_count_raw)
                            active_strategies = int(strat_count_str)
                    except Exception:
                        active_strategies = None

                    if active_strategies == 0:
                        result["healthy"] = True
                        result["info"] = f"No active strategies configured for {self.broker}"
                    else:
                        result["healthy"] = False
                        result["issue"] = f"No signals generated for {self.broker} during market hours"
                        result["recommendation"] = f"Check strategy runner and {self.broker} broker configuration"
                        try:
                            if _VALIDATOR_WARNINGS is not None:
                                _VALIDATOR_WARNINGS.labels(stage="signal_generation", broker=self.broker, issue="no_signals").inc()
                        except Exception:
                            pass
                else:
                    # Check signal latency - FIXED: Handle JSON format from PipelineMetricsCollector
                    last_signal_time = self._parse_timestamp_from_json_or_iso(last_signal_time_str)
                    if not last_signal_time:
                        return {"healthy": False, "broker": self.broker, "issue": "metrics_parse_error"}
                    signal_latency = (datetime.now(timezone.utc) - last_signal_time).total_seconds()
                    result["last_signal_time"] = last_signal_time.isoformat()
                    
                    if signal_latency > self.thresholds["signal_processing_latency"]:
                        result["healthy"] = False
                        result["latency_ms"] = signal_latency * 1000
                        result["issue"] = f"Signal generation latency too high for {self.broker}: {signal_latency:.2f}s"
                        result["recommendation"] = f"Check strategy runner performance for {self.broker}"
                        try:
                            if _VALIDATOR_WARNINGS is not None:
                                _VALIDATOR_WARNINGS.labels(stage="signal_generation", broker=self.broker, issue="latency").inc()
                        except Exception:
                            pass
            
            return result
            
        except Exception as e:
            return {"healthy": False, "broker": self.broker, "issue": "validation_error", "error": str(e)}
    
    async def _validate_risk_management(self) -> Dict[str, Any]:
        """Validate risk management for this specific broker"""
        try:
            # Check broker-specific risk validation metrics - FIXED: Use pipeline: prefix to match PipelineMetricsCollector
            risk_key = MetricsRegistry.signals_validated_last(self.broker)
            risk_count_key = MetricsRegistry.signals_validated_count(self.broker)
            
            try:
                last_risk_time_raw = await self.redis.get(risk_key)
                risk_count_raw = await self.redis.get(risk_count_key)
            except Exception as re:
                return {"healthy": False, "broker": self.broker, "issue": "redis_unavailable", "error": str(re)}
            last_risk_time_str = self._decode_bytes(last_risk_time_raw)
            risk_count_str = self._decode_bytes(risk_count_raw)
            
            result = {
                "healthy": True,
                "broker": self.broker,
                "last_validation_time": last_risk_time_str.decode() if last_risk_time_str else None,
                "validations_last_5min": int(risk_count_str) if risk_count_str else 0
            }
            
            # Check risk validation latency if we have recent data
            if last_risk_time_str:
                last_risk_time = self._parse_timestamp_from_json_or_iso(last_risk_time_str)
                if not last_risk_time:
                    return {"healthy": False, "broker": self.broker, "issue": "metrics_parse_error"}
                risk_latency = (datetime.now(timezone.utc) - last_risk_time).total_seconds()
                
                if risk_latency > self.thresholds["risk_validation_latency"]:
                    result["healthy"] = False
                    result["latency_ms"] = risk_latency * 1000
                    result["issue"] = f"Risk validation latency too high for {self.broker}: {risk_latency:.2f}s"
                    result["recommendation"] = f"Check risk manager service performance for {self.broker}"
                    try:
                        if _VALIDATOR_WARNINGS is not None:
                            _VALIDATOR_WARNINGS.labels(stage="risk_validation", broker=self.broker, issue="latency").inc()
                    except Exception:
                        pass
            
            return result
            
        except Exception as e:
            return {"healthy": False, "broker": self.broker, "issue": "validation_error", "error": str(e)}
    
    async def _validate_order_execution(self) -> Dict[str, Any]:
        """Validate order execution for this specific broker"""
        try:
            # Respect disabled trading service: skip order execution checks when disabled
            if not self._trading_enabled:
                return {"healthy": True, "broker": self.broker, "skipped": True, "reason": "trading_disabled"}
            # Check broker-specific order execution metrics - FIXED: Use pipeline: prefix to match PipelineMetricsCollector
            execution_key = MetricsRegistry.orders_last(self.broker)
            execution_count_key = MetricsRegistry.orders_count(self.broker)
            
            try:
                last_execution_time_raw = await self.redis.get(execution_key)
                execution_count_raw = await self.redis.get(execution_count_key)
            except Exception as re:
                return {"healthy": False, "broker": self.broker, "issue": "redis_unavailable", "error": str(re)}
            last_execution_time_str = self._decode_bytes(last_execution_time_raw)
            execution_count_str = self._decode_bytes(execution_count_raw)
            
            result = {
                "healthy": True,
                "broker": self.broker,
                "last_execution_time": last_execution_time_str.decode() if last_execution_time_str else None,
                "executions_last_5min": int(execution_count_str) if execution_count_str else 0
            }
            
            # Check execution latency if we have recent data
            if last_execution_time_str:
                last_execution_time = self._parse_timestamp_from_json_or_iso(last_execution_time_str)
                if not last_execution_time:
                    return {"healthy": False, "broker": self.broker, "issue": "metrics_parse_error"}
                execution_latency = (datetime.now(timezone.utc) - last_execution_time).total_seconds()
                
                if execution_latency > self.thresholds["order_execution_latency"]:
                    result["healthy"] = False
                    result["latency_ms"] = execution_latency * 1000
                    result["issue"] = f"Order execution latency too high for {self.broker}: {execution_latency:.2f}s"
                    result["recommendation"] = f"Check trading engine service performance for {self.broker}"
                    try:
                        if _VALIDATOR_WARNINGS is not None:
                            _VALIDATOR_WARNINGS.labels(stage="order_execution", broker=self.broker, issue="latency").inc()
                    except Exception:
                        pass
            
            return result
            
        except Exception as e:
            return {"healthy": False, "broker": self.broker, "issue": "validation_error", "error": str(e)}
    
    async def _validate_portfolio_updates(self) -> Dict[str, Any]:
        """Validate portfolio updates for this specific broker"""
        try:
            # Respect disabled trading service: skip portfolio checks when disabled
            if not self._trading_enabled:
                return {"healthy": True, "broker": self.broker, "skipped": True, "reason": "trading_disabled"}
            # Check broker-specific portfolio update metrics - FIXED: Use pipeline: prefix to match PipelineMetricsCollector
            portfolio_key = MetricsRegistry.portfolio_updates_last(self.broker)
            portfolio_count_key = MetricsRegistry.portfolio_updates_count(self.broker)
            
            try:
                last_update_time_raw = await self.redis.get(portfolio_key)
                update_count_raw = await self.redis.get(portfolio_count_key)
            except Exception as re:
                return {"healthy": False, "broker": self.broker, "issue": "redis_unavailable", "error": str(re)}
            last_update_time_str = self._decode_bytes(last_update_time_raw)
            update_count_str = self._decode_bytes(update_count_raw)
            
            result = {
                "healthy": True,
                "broker": self.broker,
                "last_update_time": last_update_time_str.decode() if last_update_time_str else None,
                "updates_last_5min": int(update_count_str) if update_count_str else 0
            }
            
            # Check portfolio update latency if we have recent data
            if last_update_time_str:
                last_update_time = self._parse_timestamp_from_json_or_iso(last_update_time_str)
                if not last_update_time:
                    return {"healthy": False, "broker": self.broker, "issue": "metrics_parse_error"}
                portfolio_latency = (datetime.now(timezone.utc) - last_update_time).total_seconds()
                
                if portfolio_latency > self.thresholds["portfolio_update_latency"]:
                    result["healthy"] = False
                    result["latency_ms"] = portfolio_latency * 1000
                    result["issue"] = f"Portfolio update latency too high for {self.broker}: {portfolio_latency:.2f}s"
                    result["recommendation"] = f"Check portfolio manager service performance for {self.broker}"
                    try:
                        if _VALIDATOR_WARNINGS is not None:
                            _VALIDATOR_WARNINGS.labels(stage="portfolio_updates", broker=self.broker, issue="latency").inc()
                    except Exception:
                        pass
            
            return result
            
        except Exception as e:
            return {"healthy": False, "broker": self.broker, "issue": "validation_error", "error": str(e)}
    
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

    def _is_trading_enabled(self, broker: str) -> bool:
        """Determine if trading is enabled for the given broker using Settings helpers."""
        try:
            if broker == "paper":
                return bool(self.settings.is_paper_trading_enabled())
            if broker == "zerodha":
                return bool(self.settings.is_zerodha_trading_enabled())
        except Exception:
            pass
        return False
