#!/usr/bin/env python3
"""
Quick test script to verify shutdown behavior
"""
import asyncio
import signal
import sys
from app.application import AlphaPTApplication

async def main():
    print("🔍 Testing AlphaPT shutdown behavior...")
    
    app = AlphaPTApplication()
    
    def signal_handler(sig, frame):
        print(f"\n⚠️ Received signal {sig}, initiating graceful shutdown...")
        asyncio.create_task(shutdown(app))
    
    async def shutdown(app):
        print("🛑 Starting graceful shutdown...")
        await app.stop()
        print("✅ Shutdown completed!")
        sys.exit(0)
    
    # Install signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Test banner display
        app.display_startup_banner()
        
        # Initialize (this should work now)
        result = await app.initialize()
        if result:
            print("✅ Application initialized successfully!")
            print("🔄 Running for 10 seconds... Press Ctrl+C to test shutdown")
            
            # Run for a bit
            await asyncio.sleep(10)
            
            print("⏰ Time limit reached, shutting down...")
            await app.stop()
            
        else:
            print("❌ Application failed to initialize")
            
    except KeyboardInterrupt:
        print("\n⚠️ Keyboard interrupt received")
        await shutdown(app)
    except Exception as e:
        print(f"❌ Error: {e}")
        await shutdown(app)
    
    print("👋 Test completed!")

if __name__ == "__main__":
    asyncio.run(main())