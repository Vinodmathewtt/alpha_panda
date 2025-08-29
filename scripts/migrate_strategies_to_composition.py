#!/usr/bin/env python3
"""
Database Migration Script: Legacy to Composition Strategy Migration
Migrates all strategy configurations from legacy to composition architecture
"""
import asyncio
import sys
from pathlib import Path
from typing import Dict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.database.models import StrategyConfiguration
from sqlalchemy import select, update

# Migration mapping
STRATEGY_TYPE_MIGRATION = {
    "SimpleMomentumStrategy": "MomentumProcessor",
    "MomentumStrategy": "MomentumProcessor",
    "MeanReversionStrategy": "MeanReversionProcessor",
}

# Parameter migrations (CRITICAL FIX: singular -> plural)
PARAMETER_MIGRATIONS = {
    "MomentumProcessor": {
        "lookback_period": "lookback_periods",  # singular -> plural (CRITICAL FIX)
        # momentum_threshold stays the same
    },
    "MeanReversionProcessor": {
        "lookback_period": "lookback_periods",         # singular -> plural (CRITICAL FIX) 
        "window_size": "lookback_periods",             # YAML uses window_size
        "std_dev_threshold": "std_deviation_threshold", # abbreviated -> full name (CRITICAL FIX)
        "entry_threshold": "std_deviation_threshold",   # YAML uses entry_threshold
    }
}

async def migrate_strategy_configurations():
    """Migrate all strategy configurations to composition architecture"""
    
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    await db_manager.init()
    
    migration_count = 0
    
    async with db_manager.get_session() as session:
        # Get all strategy configurations
        stmt = select(StrategyConfiguration)
        result = await session.execute(stmt)
        strategies = result.scalars().all()
        
        print(f"Found {len(strategies)} strategies to migrate")
        
        for strategy in strategies:
            old_type = strategy.strategy_type
            
            if old_type in STRATEGY_TYPE_MIGRATION:
                new_type = STRATEGY_TYPE_MIGRATION[old_type]
                
                # Migrate strategy type
                strategy.strategy_type = new_type
                
                # Migrate parameters if needed
                if new_type in PARAMETER_MIGRATIONS:
                    old_params = strategy.parameters.copy()
                    new_params = {}
                    
                    for old_key, value in old_params.items():
                        # Check if parameter needs renaming
                        new_key = PARAMETER_MIGRATIONS[new_type].get(old_key, old_key)
                        new_params[new_key] = value
                    
                    strategy.parameters = new_params
                
                # Add composition flag
                if not hasattr(strategy, 'use_composition'):
                    # Add as a parameter for now (later add as column)
                    strategy.parameters['use_composition'] = True
                
                print(f"✓ Migrated {strategy.id}: {old_type} -> {new_type}")
                migration_count += 1
            else:
                print(f"? Unknown strategy type: {old_type} (skipping)")
        
        # Commit all changes
        await session.commit()
        print(f"✓ Migration complete: {migration_count} strategies migrated")
    
    await db_manager.shutdown()

async def rollback_migration():
    """Rollback migration if needed"""
    
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    await db_manager.init()
    
    # Reverse migration mapping
    REVERSE_MIGRATION = {v: k for k, v in STRATEGY_TYPE_MIGRATION.items()}
    
    rollback_count = 0
    
    async with db_manager.get_session() as session:
        stmt = select(StrategyConfiguration)
        result = await session.execute(stmt)
        strategies = result.scalars().all()
        
        for strategy in strategies:
            if strategy.strategy_type in REVERSE_MIGRATION:
                old_type = strategy.strategy_type
                new_type = REVERSE_MIGRATION[old_type]
                
                strategy.strategy_type = new_type
                
                # Remove composition flag
                if 'use_composition' in strategy.parameters:
                    del strategy.parameters['use_composition']
                
                # Reverse parameter migrations
                if old_type in PARAMETER_MIGRATIONS:
                    old_params = strategy.parameters.copy()
                    new_params = {}
                    
                    # Reverse the parameter mapping
                    reverse_param_mapping = {v: k for k, v in PARAMETER_MIGRATIONS[old_type].items()}
                    
                    for old_key, value in old_params.items():
                        # Check if parameter needs reverse renaming
                        new_key = reverse_param_mapping.get(old_key, old_key)
                        new_params[new_key] = value
                    
                    strategy.parameters = new_params
                
                print(f"✓ Rolled back {strategy.id}: {old_type} -> {new_type}")
                rollback_count += 1
        
        await session.commit()
        print(f"✓ Rollback complete: {rollback_count} strategies rolled back")
    
    await db_manager.shutdown()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        print("🔄 Starting migration rollback...")
        asyncio.run(rollback_migration())
    else:
        print("🚀 Starting strategy migration to composition architecture...")
        asyncio.run(migrate_strategy_configurations())