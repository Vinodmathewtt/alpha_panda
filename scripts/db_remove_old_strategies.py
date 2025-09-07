"""
Remove or deactivate legacy/non-ML strategies from the database.

Usage:
  python scripts/db_remove_old_strategies.py --mode delete   # hard delete
  python scripts/db_remove_old_strategies.py --mode deactivate  # set is_active=false (default)
"""

import asyncio
import argparse
from core.database.connection import DatabaseManager
from core.config.settings import Settings
from core.database.models import StrategyConfiguration


ALLOWED_TYPES = {
    "ml_momentum",
    "MLMomentumProcessor",
    "ml_mean_reversion",
    "MLMeanReversionProcessor",
    "ml_breakout",
    "MLBreakoutProcessor",
}


async def main(mode: str = "deactivate"):
    settings = Settings()
    db = DatabaseManager(settings.database.postgres_url, environment=str(settings.environment.value), schema_management=settings.database.schema_management)
    await db.init(environment=str(settings.environment.value), schema_management=settings.database.schema_management)
    async with db.get_session() as session:
        # Fetch legacy strategies
        result = await session.execute(
            StrategyConfiguration.__table__.select()
        )
        rows = result.fetchall()

        removed = 0
        for row in rows:
            strategy_type = row.strategy_type
            if strategy_type not in ALLOWED_TYPES:
                if mode == "delete":
                    await session.execute(
                        StrategyConfiguration.__table__.delete().where(
                            StrategyConfiguration.id == row.id
                        )
                    )
                else:
                    await session.execute(
                        StrategyConfiguration.__table__.update()
                        .where(StrategyConfiguration.id == row.id)
                        .values(is_active=False)
                    )
                removed += 1
        await session.commit()
        print(f"Processed legacy strategies: {removed} ({mode})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["deactivate", "delete"], default="deactivate")
    args = parser.parse_args()
    asyncio.run(main(args.mode))
