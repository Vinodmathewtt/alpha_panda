#!/usr/bin/env python3
"""
Ad-hoc script to verify instrument data service integration.
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


async def test_instrument_integration():
    """Test the instrument data service integration."""
    print("🧪 Testing instrument data service integration...")
    
    # Initialize settings and database
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    
    try:
        # Initialize database
        await db_manager.init()
        
        # Create instrument registry service
        instrument_service = InstrumentRegistryService(db_manager.get_session)
        
        # Test 1: Load instruments from CSV
        print("\n📥 Test 1: Loading instruments from CSV...")
        result = await instrument_service.load_instruments_from_csv()
        print(f"✅ Loaded {result['total_processed']} instruments")
        print(f"   Total in database: {result['total_in_database']}")
        print(f"   Registry updated: {result['registry_updated']}")
        
        # Test 2: Get registry tokens
        print("\n📊 Test 2: Getting registry tokens...")
        tokens = await instrument_service.get_registry_tokens()
        print(f"✅ Found {len(tokens)} instruments in registry")
        if tokens:
            print(f"   Sample tokens: {tokens[:5]}")
        
        # Test 3: Search instruments
        print("\n🔍 Test 3: Searching instruments...")
        results = await instrument_service.search_instruments("RELIANCE", limit=3)
        print(f"✅ Found {len(results)} instruments matching 'RELIANCE'")
        for instrument in results:
            print(f"   - {instrument['tradingsymbol']} ({instrument['instrument_token']})")
        
        # Test 4: Get statistics
        print("\n📈 Test 4: Getting statistics...")
        stats = await instrument_service.get_statistics()
        print(f"✅ Statistics:")
        print(f"   Total instruments: {stats['total_instruments']}")
        print(f"   NSE instruments: {stats['nse_instruments']}")
        print(f"   Registry instruments: {stats['registry_instruments']}")
        print(f"   Registry by exchange: {stats['registry_by_exchange']}")
        
        print("\n✅ All tests passed! Instrument data service integration is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await db_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(test_instrument_integration())

