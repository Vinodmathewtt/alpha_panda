"""
Health Checks & Readiness Probes Example

Demonstrates production-ready health check implementation
for monitoring service availability and consumer lag.
"""

from fastapi import FastAPI, HTTPException
from typing import Dict, Any
from datetime import datetime

class ServiceHealthChecker:
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.kafka_healthy = False
        self.redis_healthy = False
        self.db_healthy = False
        
    async def check_kafka_health(self) -> bool:
        """Check if Kafka producer/consumer are connected"""
        try:
            # Test produce/consume to a health topic
            await self.producer.send("health.check", value={"service": self.service_name})
            return True
        except Exception:
            return False
            
    async def check_consumer_lag(self) -> Dict[str, int]:
        """Monitor consumer lag across all partitions"""
        lag_info = {}
        for topic in self.subscribed_topics:
            partitions = await self.consumer.partitions_for_topic(topic)
            for partition in partitions:
                tp = TopicPartition(topic, partition)
                committed = await self.consumer.committed(tp)
                high_water = await self.consumer.highwater(tp)
                lag_info[f"{topic}:{partition}"] = high_water - (committed or 0)
        return lag_info
        
    async def health_endpoint(self) -> Dict[str, Any]:
        """FastAPI health endpoint"""
        checks = {
            "kafka": await self.check_kafka_health(),
            "redis": await self.check_redis_health(), 
            "database": await self.check_db_health(),
            "consumer_lag": await self.check_consumer_lag()
        }
        
        # Service is healthy if all checks pass and lag < threshold
        max_lag = max(checks["consumer_lag"].values()) if checks["consumer_lag"] else 0
        healthy = all([checks["kafka"], checks["redis"], checks["database"]]) and max_lag < 10000
        
        return {
            "service": self.service_name,
            "healthy": healthy,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks
        }