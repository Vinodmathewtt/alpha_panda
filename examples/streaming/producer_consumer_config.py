"""
Optimized Producer/Consumer Configuration Example

Demonstrates optimized aiokafka configuration for better
performance and reliability in production environments.
"""

# Producer Configuration
producer_config = {
    "acks": "all",                    # Wait for all replicas
    "enable_idempotence": True,       # Prevent duplicates
    "compression_type": "lz4",        # CPU-efficient compression (was gzip)
    "linger_ms": 15,                  # Batch optimization (was 5ms)
    "batch_size": 32768,              # 32KB batches for throughput
    "max_in_flight_requests_per_connection": 5,
    "retries": 10,
    "retry_backoff_ms": 100
}

# Consumer Configuration
consumer_config = {
    "enable_auto_commit": False,      # CRITICAL: Manual commits
    "auto_offset_reset": "earliest",  # Process all messages
    "fetch_min_bytes": 1024,          # Batch fetching
    "fetch_max_wait_ms": 500,         # Max wait for batch
    "max_poll_records": 100,          # Process in small batches
    "session_timeout_ms": 30000,      # Rebalance timeout
    "heartbeat_interval_ms": 10000    # Keep-alive interval
}

# Service Manager Pattern
class ServiceManager:
    async def start(self):
        # Initialize aiokafka producer/consumer
        pass
        
    async def stop(self):
        # Cleanup - MUST call producer.flush()
        pass