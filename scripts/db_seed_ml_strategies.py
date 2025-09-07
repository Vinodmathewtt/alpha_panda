"""
Seed strategies from YAML templates into the database (temporary/manual).

Usage:
  python scripts/db_seed_ml_strategies.py --files \
    strategies/configs/ml_momentum.yaml \
    strategies/configs/ml_mean_reversion.yaml \
    strategies/configs/low_frequency_demo.yaml

YAML keys:
- strategy_name: unique id (string)
- strategy_type: implementation key (alias: strategy_class)
- enabled: bool
- instrument_tokens: list[int]
- parameters: dict
- brokers: ["paper"] or ["zerodha"] (sets zerodha_trading_enabled)
"""

import asyncio
import argparse
import yaml
from pathlib import Path
from typing import List
from core.database.connection import DatabaseManager
from core.config.settings import Settings
from core.database.models import StrategyConfiguration


async def upsert_strategy_from_yaml(path: Path, settings: Settings):
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)

    strategy_id = cfg["strategy_name"]
    # Accept both keys for clarity
    strategy_type = cfg.get("strategy_type") or cfg.get("strategy_class")
    if not strategy_type:
        raise ValueError("YAML must include 'strategy_type' (or 'strategy_class')")
    instruments = cfg.get("instrument_tokens", [])
    parameters = cfg.get("parameters", {})
    is_active = cfg.get("enabled", True)
    zerodha_only = any(str(b).strip().lower() == "zerodha" for b in cfg.get("brokers", []))

    db = DatabaseManager(settings.database.postgres_url, environment=str(settings.environment.value), schema_management=settings.database.schema_management)
    async with db.get_session() as session:
        # upsert by id
        existing = await session.get(StrategyConfiguration, strategy_id)
        if existing:
            await session.execute(
                StrategyConfiguration.__table__.update()
                .where(StrategyConfiguration.id == strategy_id)
                .values(
                    strategy_type=strategy_type,
                    instruments=instruments,
                    parameters=parameters,
                    is_active=is_active,
                    zerodha_trading_enabled=zerodha_only,
                    use_composition=True,
                )
            )
        else:
            session.add(
                StrategyConfiguration(
                    id=strategy_id,
                    strategy_type=strategy_type,
                    instruments=instruments,
                    parameters=parameters,
                    is_active=is_active,
                    zerodha_trading_enabled=zerodha_only,
                    use_composition=True,
                )
            )
        await session.commit()
        print(f"Upserted strategy: {strategy_id} ({strategy_type})")


async def main(files: List[str]):
    settings = Settings()
    for f in files:
        await upsert_strategy_from_yaml(Path(f), settings)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.files))
