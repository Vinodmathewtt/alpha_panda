#!/usr/bin/env python3
"""
Test script to validate enhanced monitoring and alerting implementations.
"""

import asyncio
import logging
import json
from datetime import datetime, timezone
from core.monitoring.alerting import AlertManager, AlertSeverity, AlertCategory
from core.monitoring.metrics_collector import MetricsCollector, MetricThreshold
from core.health.health_checker import ServiceHealthChecker
from core.config.settings import Settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockRedisClient:
    """Mock Redis client for testing"""
    
    def __init__(self):
        self.data = {}
    
    async def get(self, key):
        value = self.data.get(key)
        return value.encode('utf-8') if value else None
    
    async def setex(self, key, ttl, value):
        self.data[key] = value
    
    async def incr(self, key):
        self.data[key] = str(int(self.data.get(key, 0)) + 1)
    
    async def expire(self, key, ttl):
        pass  # Mock implementation
    
    async def ping(self):
        return True
    
    async def exists(self, key):
        return 1 if key in self.data else 0
    
    async def keys(self, pattern):
        return [k for k in self.data.keys() if pattern.replace('*', '') in k]


class MockAuthService:
    """Mock authentication service for testing"""
    
    def __init__(self, authenticated=True):
        self._authenticated = authenticated
    
    def is_authenticated(self):
        return self._authenticated
    
    async def get_current_user_profile(self):
        if self._authenticated:
            return type('UserProfile', (), {'user_id': 'test_user'})()
        return None


async def test_alerting_system():
    """Test the alerting system"""
    logger.info("Testing alerting system...")
    
    # Create alert manager
    alert_manager = AlertManager()
    
    # Test sending alerts
    await alert_manager.send_alert(
        title="Test Alert",
        message="This is a test alert",
        severity=AlertSeverity.HIGH,
        category=AlertCategory.SYSTEM,
        component="test_component"
    )
    
    await alert_manager.critical_alert(
        title="Critical Test Alert",
        message="This is a critical test alert",
        component="test_component"
    )
    
    await alert_manager.authentication_alert(
        title="Auth Test Alert",
        message="This is an authentication test alert",
        component="test_auth"
    )
    
    # Get stats
    stats = alert_manager.get_stats()
    logger.info(f"Alert manager stats: {stats}")
    
    # Get recent alerts
    recent_alerts = alert_manager.get_recent_alerts(minutes=60)
    logger.info(f"Recent alerts: {len(recent_alerts)}")
    
    logger.info("✅ Alerting system test completed")


async def test_metrics_collector():
    """Test the metrics collector"""
    logger.info("Testing metrics collector...")
    
    # Create mock Redis client
    redis_client = MockRedisClient()
    
    # Create settings mock
    settings = type('Settings', (), {
        'broker_namespace': 'test'
    })()
    
    # Create metrics collector
    collector = MetricsCollector(redis_client, settings)
    
    # Add custom threshold
    custom_threshold = MetricThreshold(
        metric_name="test_metric",
        warning_threshold=10.0,
        critical_threshold=20.0
    )
    collector.add_threshold(custom_threshold)
    
    # Test caching metrics
    test_metrics = {
        "service_name": "test_service",
        "messages_processed": 100,
        "error_rate_percent": 2.5,
        "avg_processing_time_ms": 50.0
    }
    
    await collector.cache_service_metrics("test_service", test_metrics)
    
    # Test collection
    await collector.collect_all_metrics()
    
    # Get metrics
    service_metrics = collector.get_service_metrics("test_service")
    if service_metrics:
        logger.info(f"Service metrics: {service_metrics.to_dict()}")
    
    aggregated = collector.get_aggregated_metrics()
    logger.info(f"Aggregated metrics: {json.dumps(aggregated, indent=2, default=str)}")
    
    logger.info("✅ Metrics collector test completed")


async def test_health_checker():
    """Test the health checker with pipeline flow implementations"""
    logger.info("Testing health checker...")
    
    # Create mock Redis client with test data
    redis_client = MockRedisClient()
    
    # Add some test data for pipeline flow checks
    current_time = datetime.now(timezone.utc).isoformat()
    redis_client.data.update({
        "alpha_panda:metrics:market_ticks:last_processed": current_time,
        "alpha_panda:metrics:market_ticks:count_last_minute": "25",
        "alpha_panda:metrics:test:signals:last_generated": current_time,
        "alpha_panda:metrics:test:signals:count_last_5min": "5",
        "alpha_panda:metrics:test:orders:last_processed": current_time,
        "alpha_panda:metrics:test:orders:filled_last_hour": "10",
        "alpha_panda:metrics:test:orders:failed_last_hour": "2"
    })
    
    # Create settings
    settings = Settings()
    settings.broker_namespace = "test"
    
    # Create mock auth service (authenticated)
    auth_service = MockAuthService(authenticated=True)
    
    # Create health checker
    health_checker = ServiceHealthChecker(
        settings=settings,
        redis_client=redis_client,
        auth_service=auth_service
    )
    
    # Test individual health checks
    logger.info("Testing market data flow check...")
    market_data_result = await health_checker._check_market_data_flow()
    logger.info(f"Market data flow: {market_data_result}")
    
    logger.info("Testing signal generation flow check...")
    signal_result = await health_checker._check_signal_generation_flow()
    logger.info(f"Signal generation flow: {signal_result}")
    
    logger.info("Testing order flow check...")
    order_result = await health_checker._check_order_flow()
    logger.info(f"Order flow: {order_result}")
    
    logger.info("Testing authentication health check...")
    auth_result = await health_checker._check_zerodha_auth_health()
    logger.info(f"Authentication health: {auth_result}")
    
    # Test overall health check
    logger.info("Testing overall health check...")
    overall_health = await health_checker.get_overall_health()
    logger.info(f"Overall health status: {overall_health['status']}")
    logger.info(f"Health summary: {overall_health['summary']}")
    
    logger.info("✅ Health checker test completed")


async def test_auth_failure_scenario():
    """Test health checker with authentication failure"""
    logger.info("Testing authentication failure scenario...")
    
    redis_client = MockRedisClient()
    settings = Settings()
    settings.broker_namespace = "test"
    
    # Create auth service that fails authentication
    auth_service = MockAuthService(authenticated=False)
    
    health_checker = ServiceHealthChecker(
        settings=settings,
        redis_client=redis_client,
        auth_service=auth_service
    )
    
    # Test authentication failure
    auth_result = await health_checker._check_zerodha_auth_health()
    logger.info(f"Auth failure result: {auth_result}")
    
    # Test overall health with auth failure
    overall_health = await health_checker.get_overall_health()
    logger.info(f"Overall health with auth failure: {overall_health['status']}")
    
    logger.info("✅ Authentication failure test completed")


async def main():
    """Main test function"""
    logger.info("🚀 Starting enhanced monitoring and alerting tests...")
    
    try:
        # Test each component
        await test_alerting_system()
        await test_metrics_collector()
        await test_health_checker()
        await test_auth_failure_scenario()
        
        logger.info("🎉 All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())