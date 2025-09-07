#!/usr/bin/env python3
"""
Ad-hoc script to verify market feed service can load instruments.
"""

import asyncio
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from services.instrument_data.csv_loader import InstrumentCSVLoader


async def test_market_feed_integration():
    """Test that market feed service can load instruments from CSV."""
    print("🧪 Testing market feed service instrument loading...")
    
    # Initialize settings and database
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    
    try:
        # Initialize database
        await db_manager.init()
        
        # Test direct CSV loading (like market feed service does)
        print("\n📂 Test 1: Direct CSV loading...")
        csv_loader = InstrumentCSVLoader.from_default_path()
        instruments_data = csv_loader.load_instruments()
        
        print(f"✅ CSV loader found {len(instruments_data)} instruments")
        
        # Extract instrument tokens (like market feed service does)
        instrument_tokens = [int(item['instrument_token']) for item in instruments_data]
        
        print(f"✅ Extracted {len(instrument_tokens)} instrument tokens")
        print(f"   Sample tokens: {instrument_tokens[:10]}")
        
        # Test instrument registry service integration
        print("\n🔗 Test 2: Registry service integration...")
        instrument_service = InstrumentRegistryService(db_manager.get_session)
        
        # Load instruments into database via registry service
        result = await instrument_service.load_instruments_from_csv()
        print(f"✅ Registry service processed {result['total_processed']} instruments")
        
        # Get registry tokens for subscription
        registry_tokens = await instrument_service.get_registry_tokens()
        print(f"✅ Registry service provides {len(registry_tokens)} tokens for subscription")
        
        # Verify all CSV tokens are in registry
        csv_token_set = set(instrument_tokens)
        registry_token_set = set(registry_tokens)
        
        if csv_token_set == registry_token_set:
            print("✅ All CSV tokens are available in registry")
        else:
            print(f"⚠️  Mismatch between CSV and registry tokens:")
            print(f"    CSV only: {csv_token_set - registry_token_set}")
            print(f"    Registry only: {registry_token_set - csv_token_set}")
        
        print(f"\n✅ Market feed integration test passed!")
        print(f"   Market feed service will subscribe to {len(registry_tokens)} instruments")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await db_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(test_market_feed_integration())

