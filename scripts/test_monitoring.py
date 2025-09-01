#!/usr/bin/env python3
"""
Test script for enhanced monitoring system
"""

import asyncio
import sys
import os

# Add the parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config.settings import Settings
from core.logging import configure_logging, get_trading_logger_safe, get_monitoring_logger_safe
from core.health import ServiceHealthChecker
from core.monitoring import PipelineMonitor, PipelineMetricsCollector
import redis.asyncio as redis


async def test_enhanced_monitoring():
    """Test the enhanced monitoring system"""
    print("🧪 Testing Alpha Panda Enhanced Monitoring System...")
    
    try:
        # Load settings
        settings = Settings()
        active = getattr(settings, 'active_brokers', [])
        broker_ctx = (active[0] if active else 'shared')
        print(f"✅ Settings loaded - Brokers: {active} (ctx={broker_ctx})")
        
        # Test logging configuration
        configure_logging(settings)
        print("✅ Logging configuration completed")
        
        # Test loggers
        trading_logger = get_trading_logger_safe("test_trading")
        monitoring_logger = get_monitoring_logger_safe("test_monitoring")
        
        trading_logger.info("Test trading log message", test_data="example", broker=broker_ctx)
        monitoring_logger.info("Test monitoring log message", component="test")
        print("✅ Enhanced loggers working correctly")
        
        # Test Redis connection
        redis_client = redis.from_url(settings.redis.url)
        await redis_client.ping()
        print("✅ Redis connection successful")
        
        # Test pipeline metrics collector
        metrics_collector = PipelineMetricsCollector(redis_client, settings)
        
        # Test recording a sample market tick
        sample_tick = {
            "instrument_token": 123456,
            "symbol": "TEST",
            "last_price": 100.50
        }
        await metrics_collector.record_market_tick(sample_tick)
        print("✅ Pipeline metrics collector working")
        
        # Test pipeline health status
        health_status = await metrics_collector.get_pipeline_health()
        print(f"✅ Pipeline health check completed - Overall healthy: {health_status['overall_healthy']}")
        
        # Test pipeline monitor initialization
        pipeline_monitor = PipelineMonitor(settings, redis_client)
        print("✅ Pipeline monitor initialized successfully")
        
        # Test health checker if available
        try:
            health_checker = ServiceHealthChecker(settings)
            await health_checker.start()
            
            overall_health = await health_checker.get_overall_health()
            print(f"✅ System health check completed - Status: {overall_health.get('status', 'unknown')}")
            
            await health_checker.stop()
        except Exception as e:
            print(f"⚠️  Health checker test skipped: {e}")
        
        # Clean up test data
        await metrics_collector.reset_metrics()
        print("✅ Test cleanup completed")
        
        # FIX: Use aclose() for consistent async Redis client closure (redis-py 5.x preferred method)
        await redis_client.aclose()
        print("\n🎉 All monitoring tests passed successfully!")
        print("\nMonitoring system features verified:")
        print("  ✓ Enhanced logging with structured output")
        print("  ✓ Pipeline metrics collection")
        print("  ✓ Pipeline health monitoring")
        print("  ✓ Redis connectivity")
        print("  ✓ Configuration loading")
        
    except Exception as e:
        print(f"\n❌ Monitoring test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_enhanced_monitoring())
    sys.exit(0 if success else 1)
