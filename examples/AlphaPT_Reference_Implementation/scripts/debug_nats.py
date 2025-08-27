#!/usr/bin/env python3
"""
Debug NATS publishing issues
"""
import asyncio
from core.events import get_event_bus_core, get_event_publisher
from core.events.event_types import SystemEvent, EventType
from core.config.settings import Settings
from datetime import datetime, timezone
import uuid

async def test_nats_publishing():
    print("🔍 Testing NATS publishing for different subjects...")
    
    settings = Settings()
    
    # Get event publisher
    try:
        event_publisher = get_event_publisher(settings)
        print("✅ Event publisher obtained")
        
        # Test 1: health.check (this works)
        health_event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.HEALTH_CHECK,
            timestamp=datetime.now(timezone.utc),
            source="debug_test",
            component="debug",
            severity="INFO",
            message="Test health check event"
        )
        
        print("\n📤 Testing health.check subject...")
        try:
            await event_publisher.publish("health.check", health_event)
            print("✅ health.check - SUCCESS")
        except Exception as e:
            print(f"❌ health.check - FAILED: {e}")
        
        # Test 2: system.quality.metrics (this fails)
        metrics_event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.HEALTH_CHECK,
            timestamp=datetime.now(timezone.utc),
            source="debug_test",
            component="debug",
            severity="INFO",
            message="Test quality metrics event"
        )
        
        print("\n📤 Testing system.quality.metrics subject...")
        try:
            await event_publisher.publish("system.quality.metrics", metrics_event)
            print("✅ system.quality.metrics - SUCCESS")
        except Exception as e:
            print(f"❌ system.quality.metrics - FAILED: {e}")
            
        # Test 3: system.test (should work)
        test_event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.HEALTH_CHECK,
            timestamp=datetime.now(timezone.utc),
            source="debug_test",
            component="debug",
            severity="INFO",
            message="Test system event"
        )
        
        print("\n📤 Testing system.test subject...")
        try:
            await event_publisher.publish("system.test", test_event)
            print("✅ system.test - SUCCESS")
        except Exception as e:
            print(f"❌ system.test - FAILED: {e}")
        
        # Test 4: Check event bus connection
        event_bus = get_event_bus_core(settings)
        print(f"\n🔍 Event Bus Connected: {event_bus.is_connected}")
        if hasattr(event_bus, 'js') and event_bus.js:
            print("✅ JetStream client available")
        else:
            print("❌ JetStream client not available")
            
    except Exception as e:
        print(f"❌ Failed to get event publisher: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_nats_publishing())