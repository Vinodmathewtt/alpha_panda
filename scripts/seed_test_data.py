#!/usr/bin/env python3
"""
Seed test data for Alpha Panda testing

This script populates the test database with necessary data for testing,
including test strategies, users, and configurations.
"""

import asyncio
import sys
import json
import os
from datetime import datetime
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database URL: prefer explicit env, fallback to standard dev DB
TEST_DATABASE_URL = (
    os.getenv("DATABASE__POSTGRES_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql+asyncpg://alpha_panda:alpha_panda@localhost:5432/alpha_panda"
)

# Test data
TEST_STRATEGIES = [
    {
        "id": "momentum_test_1",
        "strategy_type": "SimpleMomentumStrategy",
        "instruments": [738561, 2714625],  # NIFTY, BANKNIFTY
        "parameters": {
            "lookback_period": 20,
            "momentum_threshold": 0.02,
            "position_size": 100
        },
        "is_active": True,
        "zerodha_trading_enabled": False
    },
    {
        "id": "momentum_test_2",
        "strategy_type": "SimpleMomentumStrategy",
        "instruments": [256265],  # MIDCPNIFTY
        "parameters": {
            "lookback_period": 15,
            "momentum_threshold": 0.015,
            "position_size": 50
        },
        "is_active": True,
        "zerodha_trading_enabled": True
    },
    {
        "id": "mean_reversion_test_1",
        "strategy_type": "MeanReversionStrategy",
        "instruments": [738561],
        "parameters": {
            "lookback_period": 50,
            "deviation_threshold": 2.0,
            "position_size": 50
        },
        "is_active": True,
        "zerodha_trading_enabled": True
    },
    {
        "id": "mean_reversion_test_2",
        "strategy_type": "MeanReversionStrategy",
        "instruments": [2714625, 779521],
        "parameters": {
            "lookback_period": 30,
            "deviation_threshold": 1.5,
            "position_size": 75
        },
        "is_active": True,
        "zerodha_trading_enabled": False
    },
    {
        "id": "inactive_strategy",
        "strategy_type": "SimpleMomentumStrategy",
        "instruments": [738561],
        "parameters": {
            "lookback_period": 10,
            "momentum_threshold": 0.01,
            "position_size": 25
        },
        "is_active": False,
        "zerodha_trading_enabled": False
    }
]

TEST_USERS = [
    {
        "username": "testuser",
        "email": "test@example.com",
        "password_hash": "$2b$12$example_hash_for_testing_purposes_only",
        "is_active": True
    },
    {
        "username": "admin",
        "email": "admin@example.com", 
        "password_hash": "$2b$12$another_example_hash_for_testing_purposes",
        "is_active": True
    }
]


async def create_engine():
    """Create database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,  # Set to True for SQL debugging
        future=True
    )
    return engine


async def seed_strategies(session: AsyncSession):
    """Seed test strategies"""
    logger.info("Seeding test strategies...")
    
    # Clear existing test strategies
    await session.execute(
        text("DELETE FROM strategies WHERE id LIKE '%test%' OR id = 'inactive_strategy'")
    )
    
    # Insert test strategies
    for strategy in TEST_STRATEGIES:
        await session.execute(
            text("""
                INSERT INTO strategies (id, strategy_type, instruments, parameters, is_active, zerodha_trading_enabled, created_at, updated_at)
                VALUES (:id, :strategy_type, :instruments, :parameters, :is_active, :zerodha_trading_enabled, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    strategy_type = EXCLUDED.strategy_type,
                    instruments = EXCLUDED.instruments,
                    parameters = EXCLUDED.parameters,
                    is_active = EXCLUDED.is_active,
                    zerodha_trading_enabled = EXCLUDED.zerodha_trading_enabled,
                    updated_at = NOW()
            """),
            {
                "id": strategy["id"],
                "strategy_type": strategy["strategy_type"],
                "instruments": strategy["instruments"],
                "parameters": json.dumps(strategy["parameters"]),
                "is_active": strategy["is_active"],
                "zerodha_trading_enabled": strategy["zerodha_trading_enabled"]
            }
        )
    
    await session.commit()
    logger.info(f"Seeded {len(TEST_STRATEGIES)} test strategies")


async def seed_users(session: AsyncSession):
    """Seed test users"""
    logger.info("Seeding test users...")
    
    # Clear existing test users
    await session.execute(
        text("DELETE FROM users WHERE username IN ('testuser', 'admin')")
    )
    
    # Insert test users
    for user in TEST_USERS:
        await session.execute(
            text("""
                INSERT INTO users (username, email, password_hash, is_active, created_at)
                VALUES (:username, :email, :password_hash, :is_active, NOW())
                ON CONFLICT (username) DO UPDATE SET
                    email = EXCLUDED.email,
                    password_hash = EXCLUDED.password_hash,
                    is_active = EXCLUDED.is_active
            """),
            user
        )
    
    await session.commit()
    logger.info(f"Seeded {len(TEST_USERS)} test users")


async def seed_trading_sessions(session: AsyncSession):
    """Seed sample trading sessions"""
    logger.info("Seeding sample trading sessions...")
    
    # Clear existing test sessions
    await session.execute(
        text("DELETE FROM trading_sessions WHERE session_data->>'test_session' = 'true'")
    )
    
    # Create sample trading sessions
    sample_sessions = [
        {
            "session_id": "test_session_1",
            "strategy_ids": ["momentum_test_1", "mean_reversion_test_1"],
            "start_time": datetime.now().isoformat(),
            "total_trades": 25,
            "total_pnl": 1250.50,
            "test_session": True
        },
        {
            "session_id": "test_session_2",
            "strategy_ids": ["momentum_test_2"],
            "start_time": datetime.now().isoformat(),
            "total_trades": 15,
            "total_pnl": -125.25,
            "test_session": True
        }
    ]
    
    for session_data in sample_sessions:
        await session.execute(
            text("""
                INSERT INTO trading_sessions (session_data, created_at)
                VALUES (:session_data, NOW())
            """),
            {"session_data": json.dumps(session_data)}
        )
    
    await session.commit()
    logger.info(f"Seeded {len(sample_sessions)} sample trading sessions")


async def verify_seeded_data(session: AsyncSession):
    """Verify that data was seeded correctly"""
    logger.info("Verifying seeded data...")
    
    # Check strategies
    result = await session.execute(text("SELECT COUNT(*) FROM strategies WHERE id LIKE '%test%'"))
    strategy_count = result.scalar()
    logger.info(f"Strategies in database: {strategy_count}")
    
    # Check active strategies
    result = await session.execute(text("SELECT COUNT(*) FROM strategies WHERE is_active = true"))
    active_count = result.scalar()
    logger.info(f"Active strategies: {active_count}")
    
    # Check zerodha-enabled strategies
    result = await session.execute(text("SELECT COUNT(*) FROM strategies WHERE zerodha_trading_enabled = true"))
    zerodha_count = result.scalar()
    logger.info(f"Zerodha-enabled strategies: {zerodha_count}")
    
    # Check users
    result = await session.execute(text("SELECT COUNT(*) FROM users"))
    user_count = result.scalar()
    logger.info(f"Users in database: {user_count}")
    
    # Check trading sessions
    result = await session.execute(text("SELECT COUNT(*) FROM trading_sessions WHERE session_data->>'test_session' = 'true'"))
    session_count = result.scalar()
    logger.info(f"Test trading sessions: {session_count}")
    
    return {
        "strategies": strategy_count,
        "active_strategies": active_count,
        "zerodha_strategies": zerodha_count,
        "users": user_count,
        "sessions": session_count
    }


async def main():
    """Main function to seed test data"""
    logger.info("Alpha Panda Test Data Seeding")
    logger.info("=" * 40)
    
    engine = None
    session = None
    
    try:
        # Create engine and session
        engine = await create_engine()
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session() as session:
            # Test connection
            await session.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            
            # Seed data
            await seed_strategies(session)
            await seed_users(session)
            await seed_trading_sessions(session)
            
            # Verify seeded data
            stats = await verify_seeded_data(session)
            
            logger.info("=" * 40)
            logger.info("✅ Test data seeding completed successfully!")
            logger.info(f"   - {stats['strategies']} strategies")
            logger.info(f"   - {stats['active_strategies']} active strategies") 
            logger.info(f"   - {stats['zerodha_strategies']} zerodha-enabled strategies")
            logger.info(f"   - {stats['users']} users")
            logger.info(f"   - {stats['sessions']} sample sessions")
            
    except Exception as e:
        logger.error(f"❌ Test data seeding failed: {e}")
        sys.exit(1)
    finally:
        if engine:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
