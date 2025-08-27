from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from core.database.connection import DatabaseManager
from core.database.models import PortfolioSnapshot
from core.config.settings import Settings
from core.logging import get_trading_logger_safe
from ..models import Portfolio, Position


class DatabasePersister:
    """Handles portfolio persistence to PostgreSQL database."""
    
    def __init__(self, db_manager: DatabaseManager, settings: Settings):
        self.db_manager = db_manager
        self.settings = settings
        self.logger = get_trading_logger_safe("database_persister")
    
    async def persist_portfolio(self, portfolio: Portfolio) -> None:
        """Persist single portfolio to database."""
        try:
            async with self.db_manager.get_session() as session:
                # Extract broker and strategy from portfolio ID
                # Format: "paper_strategy_id" or "zerodha_strategy_id"
                parts = portfolio.portfolio_id.split('_', 1)
                broker_namespace = parts[0] if len(parts) > 1 else "unknown"
                strategy_id = parts[1] if len(parts) > 1 else portfolio.portfolio_id
                
                # Convert positions to JSON-serializable format
                positions_data = {
                    str(token): pos.model_dump()
                    for token, pos in portfolio.positions.items()
                }
                
                # Use upsert to handle existing snapshots
                stmt = pg_insert(PortfolioSnapshot).values(
                    portfolio_id=portfolio.portfolio_id,
                    broker_namespace=broker_namespace,
                    strategy_id=strategy_id,
                    positions=positions_data,
                    total_realized_pnl=portfolio.total_realized_pnl,
                    total_unrealized_pnl=portfolio.total_unrealized_pnl,
                    total_pnl=portfolio.total_pnl,
                    cash=portfolio.cash,
                    snapshot_time=datetime.utcnow()
                )
                
                # Update on conflict (latest snapshot wins)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['portfolio_id'],
                    set_={
                        'positions': stmt.excluded.positions,
                        'total_realized_pnl': stmt.excluded.total_realized_pnl,
                        'total_unrealized_pnl': stmt.excluded.total_unrealized_pnl,
                        'total_pnl': stmt.excluded.total_pnl,
                        'cash': stmt.excluded.cash,
                        'snapshot_time': stmt.excluded.snapshot_time
                    }
                )
                
                await session.execute(stmt)
                await session.commit()
                
                self.logger.debug("Persisted portfolio to database",
                               portfolio_id=portfolio.portfolio_id,
                               broker_namespace=broker_namespace)
                
        except Exception as e:
            self.logger.error("Failed to persist portfolio", 
                            portfolio_id=portfolio.portfolio_id, error=str(e))
            raise
    
    async def load_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Load single portfolio from database."""
        try:
            async with self.db_manager.get_session() as session:
                stmt = select(PortfolioSnapshot).where(
                    PortfolioSnapshot.portfolio_id == portfolio_id
                ).order_by(PortfolioSnapshot.snapshot_time.desc()).limit(1)
                
                result = await session.execute(stmt)
                snapshot = result.scalar_one_or_none()
                
                if not snapshot:
                    return None
                
                # Reconstruct portfolio from snapshot
                portfolio = Portfolio(
                    portfolio_id=snapshot.portfolio_id,
                    total_realized_pnl=snapshot.total_realized_pnl,
                    total_unrealized_pnl=snapshot.total_unrealized_pnl,
                    total_pnl=snapshot.total_pnl,
                    cash=snapshot.cash
                )
                
                # Reconstruct positions
                for token_str, pos_data in snapshot.positions.items():
                    instrument_token = int(token_str)
                    position = Position(**pos_data)
                    portfolio.positions[instrument_token] = position
                
                self.logger.debug("Loaded portfolio from database",
                               portfolio_id=portfolio_id,
                               positions=len(portfolio.positions))
                
                return portfolio
                
        except Exception as e:
            self.logger.error("Failed to load portfolio", 
                            portfolio_id=portfolio_id, error=str(e))
            return None
    
    async def load_all_portfolios(self, broker_namespace: str) -> List[Portfolio]:
        """Load all portfolios for a broker namespace from database."""
        try:
            async with self.db_manager.get_session() as session:
                # Get latest snapshots for each portfolio in this broker namespace
                stmt = select(PortfolioSnapshot).where(
                    PortfolioSnapshot.broker_namespace == broker_namespace
                ).order_by(PortfolioSnapshot.snapshot_time.desc())
                
                result = await session.execute(stmt)
                snapshots = result.scalars().all()
                
                portfolios = []
                portfolio_ids = set()
                
                for snapshot in snapshots:
                    # Skip if we already processed this portfolio
                    if snapshot.portfolio_id in portfolio_ids:
                        continue
                    
                    # Reconstruct portfolio from snapshot
                    portfolio = Portfolio(
                        portfolio_id=snapshot.portfolio_id,
                        total_realized_pnl=snapshot.total_realized_pnl,
                        total_unrealized_pnl=snapshot.total_unrealized_pnl,
                        total_pnl=snapshot.total_pnl,
                        cash=snapshot.cash
                    )
                    
                    # Reconstruct positions
                    for token_str, pos_data in snapshot.positions.items():
                        instrument_token = int(token_str)
                        position = Position(**pos_data)
                        portfolio.positions[instrument_token] = position
                    
                    portfolios.append(portfolio)
                    portfolio_ids.add(snapshot.portfolio_id)
                
                self.logger.info(f"Loaded {len(portfolios)} portfolios from database",
                               broker_namespace=broker_namespace)
                
                return portfolios
                
        except Exception as e:
            self.logger.error("Failed to load portfolios from database", 
                            broker_namespace=broker_namespace, error=str(e))
            return []
    
    async def delete_portfolio(self, portfolio_id: str) -> bool:
        """Delete portfolio from database."""
        try:
            async with self.db_manager.get_session() as session:
                stmt = select(PortfolioSnapshot).where(
                    PortfolioSnapshot.portfolio_id == portfolio_id
                )
                result = await session.execute(stmt)
                snapshot = result.scalar_one_or_none()
                
                if snapshot:
                    await session.delete(snapshot)
                    await session.commit()
                    self.logger.info("Deleted portfolio from database", 
                                   portfolio_id=portfolio_id)
                    return True
                else:
                    self.logger.warning("Portfolio not found for deletion", 
                                      portfolio_id=portfolio_id)
                    return False
                    
        except Exception as e:
            self.logger.error("Failed to delete portfolio", 
                            portfolio_id=portfolio_id, error=str(e))
            return False