import socket
import time
import http.client
import json
import os
import pytest


def wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except OSError:
            time.sleep(0.5)
    return False


pytestmark = pytest.mark.skipif(os.getenv("RUN_INFRA_TESTS") != "1", reason="Infra tests require running local docker infra (set RUN_INFRA_TESTS=1)")


def test_redis_ping():
    host, port = os.getenv("REDIS_HOST", "127.0.0.1"), int(os.getenv("REDIS_PORT", "6379"))
    assert wait_for_port(host, port), f"Redis not reachable at {host}:{port}"
    with socket.create_connection((host, port), timeout=2.0) as s:
        s.sendall(b"PING\r\n")
        data = s.recv(64)
    assert data.startswith(b"+PONG") or b"PONG" in data, f"Unexpected Redis reply: {data!r}"


def test_postgres_port_open():
    host, port = os.getenv("POSTGRES_HOST", "127.0.0.1"), int(os.getenv("POSTGRES_PORT", "5432"))
    assert wait_for_port(host, port), f"Postgres not reachable at {host}:{port}"
    # Connection at TCP level is sufficient for smoke; no protocol handshake
    with socket.create_connection((host, port), timeout=2.0):
        pass


def test_kafka_port_open():
    host, port = os.getenv("KAFKA_HOST", "127.0.0.1"), int(os.getenv("KAFKA_PORT", "9092"))
    assert wait_for_port(host, port), f"Kafka not reachable at {host}:{port}"
    with socket.create_connection((host, port), timeout=2.0):
        pass


def test_redpanda_admin_ready():
    host, port = os.getenv("REDPANDA_ADMIN_HOST", "127.0.0.1"), int(os.getenv("REDPANDA_ADMIN_PORT", "9644"))
    assert wait_for_port(host, port), f"Redpanda admin not reachable at {host}:{port}"
    conn = http.client.HTTPConnection(host, port, timeout=3.0)
    try:
        conn.request("GET", "/v1/status/ready")
        resp = conn.getresponse()
        body = resp.read()
        assert resp.status in (200,), f"Unexpected status: {resp.status}, body={body!r}"
    finally:
        conn.close()


def test_schema_registry_subjects_endpoint_optional():
    # Best-effort check; do not fail suite if endpoint is missing
    host, port = os.getenv("SCHEMA_REGISTRY_HOST", "127.0.0.1"), int(os.getenv("SCHEMA_REGISTRY_PORT", "8082"))
    if not wait_for_port(host, port, timeout=3.0):
        return  # Endpoint not enabled; skip silently
    conn = http.client.HTTPConnection(host, port, timeout=3.0)
    try:
        conn.request("GET", "/subjects")
        resp = conn.getresponse()
        _ = resp.read()
        assert resp.status in (200, 404), f"Unexpected schema registry status: {resp.status}"
    finally:
        conn.close()
