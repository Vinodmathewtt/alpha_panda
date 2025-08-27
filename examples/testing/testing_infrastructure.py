"""
Testing Architecture Example

Demonstrates shared test infrastructure using testcontainers
for integration testing with real infrastructure components.
"""

import pytest
import redis
from testcontainers.compose import DockerCompose
from testcontainers.redis import RedisContainer
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def test_infrastructure():
    """Start containerized infrastructure for testing"""
    with DockerCompose(".", compose_file_name="docker-compose.test.yml") as compose:
        # Wait for services to be ready
        redpanda_port = compose.get_service_port("redpanda", 9092)
        postgres_port = compose.get_service_port("postgres", 5432)
        redis_port = compose.get_service_port("redis", 6379)
        
        yield {
            "redpanda": f"localhost:{redpanda_port}",
            "postgres": f"postgresql://test:test@localhost:{postgres_port}/test_db",
            "redis": f"redis://localhost:{redis_port}/0"
        }

@pytest.fixture
async def event_deduplicator(test_infrastructure):
    """Create isolated deduplicator for tests"""
    redis_client = redis.from_url(test_infrastructure["redis"])
    return EventDeduplicator(redis_client, ttl_seconds=60)