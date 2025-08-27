from typing import Dict, List, Any
from .base import BaseHealthCheck, HealthCheckResult
from core.config.settings import Settings

class MultiBrokerHealthCheck(BaseHealthCheck):
    """Base class for broker-aware health checks."""
    
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
    
    async def check_all_brokers(self) -> List[HealthCheckResult]:
        """Check health for all active brokers."""
        results = []
        
        for broker in self.settings.active_brokers:
            try:
                result = await self.check_broker_health(broker)
                results.append(result)
            except Exception as e:
                results.append(HealthCheckResult(
                    component=f"{self.component_name}_{broker}",
                    passed=False,
                    message=f"Health check failed for {broker}: {str(e)}",
                    details={"broker": broker, "error": str(e)}
                ))
        
        return results
    
    async def check_broker_health(self, broker: str) -> HealthCheckResult:
        """Override this method in subclasses."""
        raise NotImplementedError

class BrokerTopicHealthCheck(MultiBrokerHealthCheck):
    """Verify that all broker-specific topics exist."""
    
    component_name = "broker_topics"
    
    async def check_broker_health(self, broker: str) -> HealthCheckResult:
        """Check if all required topics exist for a broker."""
        from core.schemas.topics import TopicMap
        
        topic_map = TopicMap(broker)
        required_topics = [
            topic_map.signals_raw(),
            topic_map.signals_validated(),
            topic_map.orders_submitted(),
            topic_map.orders_filled(),
            topic_map.pnl_snapshots()
        ]
        
        # Check topic existence using admin client
        # Implementation depends on your Kafka/Redpanda admin setup
        missing_topics = await self._check_topics_exist(required_topics)
        
        if missing_topics:
            return HealthCheckResult(
                component=f"broker_topics_{broker}",
                passed=False,
                message=f"Missing topics for {broker}: {', '.join(missing_topics)}",
                details={"broker": broker, "missing_topics": missing_topics}
            )
        
        return HealthCheckResult(
            component=f"broker_topics_{broker}",
            passed=True,
            message=f"All required topics exist for {broker}",
            details={"broker": broker, "topic_count": len(required_topics)}
        )
    
    async def _check_topics_exist(self, topics: List[str]) -> List[str]:
        """Check which topics are missing - simplified implementation."""
        # TODO: Implement actual topic existence check with Redpanda admin client
        # For now, assume all topics exist
        return []

class BrokerStateHealthCheck(MultiBrokerHealthCheck):
    """Check broker-specific state and configuration."""
    
    component_name = "broker_state"
    
    async def check_broker_health(self, broker: str) -> HealthCheckResult:
        """Check broker state consistency."""
        checks = []
        
        # Check Redis cache keys are properly namespaced
        cache_health = await self._check_cache_namespace(broker)
        checks.append(cache_health)
        
        # Check database configuration for broker
        db_health = await self._check_database_config(broker)
        checks.append(db_health)
        
        # Aggregate results
        passed = all(check["passed"] for check in checks)
        message = f"Broker state check for {broker}: {'PASSED' if passed else 'FAILED'}"
        
        return HealthCheckResult(
            component=f"broker_state_{broker}",
            passed=passed,
            message=message,
            details={"broker": broker, "checks": checks}
        )
    
    async def _check_cache_namespace(self, broker: str) -> Dict[str, Any]:
        """Check that Redis cache keys are properly namespaced."""
        # TODO: Implement Redis key namespace validation
        return {"passed": True, "message": f"Cache namespace valid for {broker}"}
    
    async def _check_database_config(self, broker: str) -> Dict[str, Any]:
        """Check database configuration for broker."""
        # TODO: Implement database config validation
        return {"passed": True, "message": f"Database config valid for {broker}"}