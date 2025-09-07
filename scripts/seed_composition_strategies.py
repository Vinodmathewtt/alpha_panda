#!/usr/bin/env python3
"""
Seed composition-based strategies for testing the migration
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.database.models import StrategyConfiguration, User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed_composition_strategies():
    """Seed composition-based strategies"""
    
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    await db_manager.init()
    
    async with db_manager.get_session() as session:
        # Check if admin user exists, create if not
        from sqlalchemy import select
        stmt = select(User).where(User.username == "admin")
        result = await session.execute(stmt)
        admin_user = result.scalar_one_or_none()
        
        if not admin_user:
            hashed_password = pwd_context.hash("testpassword")
            admin_user = User(
                username="admin",
                hashed_password=hashed_password
            )
            session.add(admin_user)
        
        # Create composition-based strategies
        momentum_strategy = StrategyConfiguration(
            id="momentum_composition_1",
            strategy_type="momentum",  # Composition type (rules-based)
            instruments=[738561, 2714625],  # RELIANCE, HDFCBANK tokens
            parameters={
                "lookback_periods": 20,  # Migrated parameter name
                "threshold": 0.02,
                "position_size": 100
            },
            is_active=True,
            zerodha_trading_enabled=False,
            use_composition=True  # Explicit composition flag
        )
        session.add(momentum_strategy)
        
        mean_reversion_strategy = StrategyConfiguration(
            id="mean_reversion_composition_1", 
            strategy_type="mean_reversion",  # Composition type (rules-based)
            instruments=[177665, 60417],  # ICICIBANK, SBIN tokens
            parameters={
                "lookback_periods": 20,  # Migrated parameter name
                "std_deviation_threshold": 2.0,  # Migrated parameter name
                "position_size": 50
            },
            is_active=True,
            zerodha_trading_enabled=False,
            use_composition=True  # Explicit composition flag
        )
        session.add(mean_reversion_strategy)
        
        # Also create a legacy strategy for comparison
        legacy_momentum = StrategyConfiguration(
            id="legacy_momentum_1",
            strategy_type="SimpleMomentumStrategy",  # Legacy type
            instruments=[256265],  # TCS token
            parameters={
                "lookback_period": 15,  # Legacy parameter name
                "momentum_threshold": "0.025",
                "position_size": 75
            },
            is_active=True,
            zerodha_trading_enabled=False,
            use_composition=False  # Explicit legacy flag
        )
        session.add(legacy_momentum)
        
        await session.commit()
        print("✓ Seeded composition and legacy test strategies")
        print("  - momentum_composition_1 (MomentumProcessor)")
        print("  - mean_reversion_composition_1 (MeanReversionProcessor)")
        print("  - legacy_momentum_1 (SimpleMomentumStrategy)")
    
    await db_manager.shutdown()


async def clean_test_strategies():
    """Clean up test strategies"""
    
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    await db_manager.init()
    
    async with db_manager.get_session() as session:
        from sqlalchemy import select, delete
        
        # Delete test strategies
        test_strategy_ids = [
            "momentum_composition_1",
            "mean_reversion_composition_1", 
            "legacy_momentum_1"
        ]
        
        deleted_count = 0
        for strategy_id in test_strategy_ids:
            stmt = delete(StrategyConfiguration).where(
                StrategyConfiguration.id == strategy_id
            )
            result = await session.execute(stmt)
            if result.rowcount > 0:
                deleted_count += 1
                print(f"✓ Deleted test strategy: {strategy_id}")
        
        await session.commit()
        print(f"✓ Cleanup complete: {deleted_count} test strategies deleted")
    
    await db_manager.shutdown()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        print("🧹 Cleaning up test strategies...")
        asyncio.run(clean_test_strategies())
    else:
        print("🌱 Seeding composition-based test strategies...")
        asyncio.run(seed_composition_strategies())
