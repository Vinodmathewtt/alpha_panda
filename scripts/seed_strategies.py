# Seed test strategies in database
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


async def seed_data():
    """Seed test data for development"""
    
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    await db_manager.init()
    
    async with db_manager.get_session() as session:
        # Create test user
        hashed_password = pwd_context.hash("testpassword")
        test_user = User(
            username="admin",
            hashed_password=hashed_password
        )
        session.add(test_user)
        
        # Create test strategies
        momentum_strategy = StrategyConfiguration(
            id="momentum_test_1",
            strategy_type="SimpleMomentumStrategy",
            instruments=[738561, 2714625],  # RELIANCE, HDFCBANK
            parameters={
                "lookback_period": 20,
                "momentum_threshold": 0.02,
                "position_size": 100
            },
            is_active=True,
            zerodha_trading_enabled=False  # Paper trading only
        )
        session.add(momentum_strategy)
        
        mean_reversion_strategy = StrategyConfiguration(
            id="mean_reversion_test_1", 
            strategy_type="MeanReversionStrategy",
            instruments=[177665, 60417],  # ICICIBANK, SBIN
            parameters={
                "lookback_period": 20,
                "std_dev_threshold": 2.0,
                "position_size": 50
            },
            is_active=True,
            zerodha_trading_enabled=False  # Paper trading only
        )
        session.add(mean_reversion_strategy)
        
        # Add a live trading enabled strategy for demonstration
        live_momentum_strategy = StrategyConfiguration(
            id="momentum_live_demo",
            strategy_type="SimpleMomentumStrategy", 
            instruments=[81153],  # TCS only for demo
            parameters={
                "lookback_period": 10,
                "momentum_threshold": 0.01,
                "position_size": 10  # Small size for live demo
            },
            is_active=True,
            zerodha_trading_enabled=True  # Zerodha trading enabled (requires Zerodha config)
        )
        session.add(live_momentum_strategy)
        
        await session.commit()
        print("✓ Seeded test strategies and user")
        print("  - momentum_test_1: Paper trading only")
        print("  - mean_reversion_test_1: Paper trading only") 
        print("  - momentum_live_demo: Zerodha trading enabled (requires Zerodha setup)")
        
    await db_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(seed_data())