"""Real-time SSE endpoints for dashboard monitoring."""

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from api.dependencies import get_current_user, get_settings, get_redis_client
from core.config.settings import Settings
import asyncio
import json
import redis.asyncio as redis
import time
import random

router = APIRouter(prefix="/dashboard/events", tags=["realtime"])


@router.get("/health")
async def health_stream(
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """Server-Sent Events for health monitoring"""
    async def event_generator():
        while True:
            try:
                # Simulate health data - in production, this would fetch from monitoring API
                health_data = await get_simulated_health_data(redis_client)

                yield {
                    "event": "health_update",
                    "data": json.dumps(health_data)
                }

                await asyncio.sleep(10)  # Update every 10 seconds
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)})
                }
                await asyncio.sleep(10)

    return EventSourceResponse(event_generator())


@router.get("/pipeline")
async def pipeline_stream(
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """Server-Sent Events for pipeline monitoring"""
    async def event_generator():
        while True:
            try:
                # Simulate pipeline data - in production, this would fetch from pipeline monitor
                pipeline_data = await get_simulated_pipeline_data()

                yield {
                    "event": "pipeline_update",
                    "data": json.dumps(pipeline_data)
                }

                await asyncio.sleep(5)  # Update every 5 seconds
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)})
                }
                await asyncio.sleep(5)

    return EventSourceResponse(event_generator())


@router.get("/activity")
async def activity_stream(
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
):
    """Server-Sent Events for activity feed"""
    async def event_generator():
        while True:
            try:
                # Simulate activity events
                activity_event = await get_simulated_activity_event()

                yield {
                    "event": "activity_item",
                    "data": json.dumps(activity_event)
                }

                await asyncio.sleep(random.randint(5, 15))  # Random intervals
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)})
                }
                await asyncio.sleep(10)

    return EventSourceResponse(event_generator())


@router.get("/logs")
async def logs_stream(
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
):
    """Server-Sent Events for log streaming"""
    async def event_generator():
        while True:
            try:
                # Simulate log entries
                log_entry = await get_simulated_log_entry()

                yield {
                    "event": "log_entry",
                    "data": json.dumps(log_entry)
                }

                await asyncio.sleep(random.randint(1, 3))  # Frequent log updates
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)})
                }
                await asyncio.sleep(5)

    return EventSourceResponse(event_generator())


# Helper functions to simulate real-time data
async def get_simulated_health_data(redis_client: redis.Redis):
    """Generate simulated health data"""
    try:
        await redis_client.ping()
        redis_status = "healthy"
    except Exception:
        redis_status = "unhealthy"

    return {
        "status": "healthy",
        "timestamp": time.time(),
        "data": {
            "summary": {
                "total_checks": 5,
                "healthy": random.randint(4, 5),
                "degraded": random.randint(0, 1),
                "unhealthy": 0
            },
            "checks": {
                "cpu_usage": {
                    "status": "healthy",
                    "details": {
                        "cpu_percent": random.uniform(10, 80)
                    }
                },
                "memory_usage": {
                    "status": "healthy",
                    "details": {
                        "used_percent": random.uniform(20, 70)
                    }
                },
                "disk_space": {
                    "status": "healthy",
                    "details": {
                        "used_percent": random.uniform(15, 60)
                    }
                },
                "redis": {
                    "status": redis_status,
                    "details": {}
                },
                "database": {
                    "status": "healthy",
                    "details": {}
                }
            }
        }
    }


async def get_simulated_pipeline_data():
    """Generate simulated pipeline data"""
    stages = ["market_ticks", "signals", "signals_validated", "orders", "portfolio_updates"]

    return {
        "status": "healthy",
        "timestamp": time.time(),
        "data": {
            "health": {
                "stages": {
                    stage: {
                        "healthy": random.choice([True, True, True, False]),  # 75% healthy
                        "status": random.choice(["healthy", "healthy", "healthy", "degraded"]),
                        "count": random.randint(50, 200),
                        "throughput": random.uniform(80, 120)
                    }
                    for stage in stages
                }
            },
            "throughput": random.uniform(90, 110),
            "latency": random.uniform(10, 50)
        }
    }


async def get_simulated_activity_event():
    """Generate simulated activity events"""
    events = [
        {"type": "info", "message": "Market feed connected", "service": "market_feed"},
        {"type": "success", "message": "Order executed successfully", "service": "trading_engine"},
        {"type": "warning", "message": "High CPU usage detected", "service": "system"},
        {"type": "info", "message": "Strategy signal generated", "service": "strategy_runner"},
        {"type": "success", "message": "Portfolio updated", "service": "portfolio_manager"},
        {"type": "info", "message": "Risk check passed", "service": "risk_manager"}
    ]

    event = random.choice(events)
    event["timestamp"] = time.time()
    return event


async def get_simulated_log_entry():
    """Generate simulated log entries"""
    levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
    services = ["market_feed", "strategy_runner", "risk_manager", "trading_engine", "portfolio_manager", "api"]

    messages = {
        "DEBUG": "Processing tick data for symbol {}",
        "INFO": "Service {} started successfully",
        "WARNING": "Connection timeout, retrying...",
        "ERROR": "Failed to process message: {}"
    }

    level = random.choice(levels)
    service = random.choice(services)
    message_template = messages[level]

    if "{}" in message_template:
        if "symbol" in message_template:
            message = message_template.format("NSE:RELIANCE-EQ")
        elif "Service" in message_template:
            message = message_template.format(service)
        else:
            message = message_template.format("connection error")
    else:
        message = message_template

    return {
        "timestamp": time.time(),
        "level": level,
        "service": service,
        "message": message
    }
