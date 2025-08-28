import asyncio
from typing import Dict, Any
from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.logging import get_trading_logger_safe
from ..interfaces.base_portfolio_manager import BasePortfolioManager
from ..models import Portfolio, Position
from ..cache import PortfolioCache
from ..reconciliation.broker_reconciler import BrokerReconciler
from ..persistence.database_persister import DatabasePersister


class ZerodhaPortfolioManager(BasePortfolioManager):
    """Manages live Zerodha portfolios with robust persistence and reconciliation."""
    
    def __init__(self, settings: Settings, redis_client, db_manager: DatabaseManager):
        self.settings = settings
        self.db_manager = db_manager
        self.cache = PortfolioCache(settings, redis_client)
        self.portfolios: Dict[str, Portfolio] = {}
        self.logger = get_trading_logger_safe("zerodha_portfolio_manager")
        
        # Reconciliation component
        self.reconciler = BrokerReconciler(settings)
        
        # Persistence component
        self.persister = DatabasePersister(db_manager, settings)
        
        # Concurrency control
        self._portfolio_locks: Dict[str, asyncio.Lock] = {}
        self._portfolio_locks_lock = asyncio.Lock()
        
        # Persistence settings
        self.auto_persist = True
        self.reconciliation_interval = settings.portfolio_manager.reconciliation_interval_seconds
        self._reconciliation_task = None
    
    async def start(self) -> None:
        """Initialize Zerodha portfolio manager."""
        self.logger.info("Starting Zerodha Portfolio Manager")
        await self.cache.initialize(namespace="zerodha")
        
        # Initialize reconciler
        await self.reconciler.initialize()
        
        # Recovery from database
        await self._recover_portfolios_from_database()
        
        # Start reconciliation task
        if self.reconciliation_interval > 0:
            self._reconciliation_task = asyncio.create_task(
                self._periodic_reconciliation_loop()
            )
        
        self.logger.info("Zerodha Portfolio Manager started")
    
    async def initialize(self) -> None:
        """Initialize Zerodha portfolio manager (alias for start)."""
        await self.start()
    
    async def shutdown(self) -> None:
        """Shutdown Zerodha portfolio manager."""
        self.logger.info("Stopping Zerodha Portfolio Manager")
        
        # Cancel reconciliation task
        if self._reconciliation_task:
            self._reconciliation_task.cancel()
            try:
                await self._reconciliation_task
            except asyncio.CancelledError:
                pass
        
        # Persist final state
        await self._persist_all_portfolios()
        await self.cache.close()
        
        self.logger.info("Zerodha Portfolio Manager stopped")
    
    async def stop(self) -> None:
        """Stop Zerodha portfolio manager (alias for shutdown)."""
        await self.shutdown()
    
    async def handle_fill(self, fill_data: Dict[str, Any]) -> None:
        """Process fill event with transactional persistence."""
        strategy_id = fill_data.get('strategy_id')
        if not strategy_id:
            self.logger.warning("Fill missing strategy_id", fill_data=fill_data)
            return
        
        portfolio_id = f"zerodha_{strategy_id}"
        portfolio = await self._get_or_create_portfolio(portfolio_id)
        
        # Transactional processing
        try:
            # Update portfolio state
            await self._process_fill(portfolio, fill_data)
            
            # Persist to database first (source of truth)
            if self.auto_persist:
                await self.persister.persist_portfolio(portfolio)
            
            # Then update cache for fast reads
            await self.cache.save_portfolio(portfolio)
            
            self.logger.info("Updated Zerodha portfolio", 
                           portfolio_id=portfolio_id,
                           total_pnl=portfolio.total_pnl)
            
        except Exception as e:
            self.logger.error("Failed to process Zerodha fill", 
                            portfolio_id=portfolio_id, error=str(e))
            # TODO: Implement retry/DLQ logic here
            raise
    
    async def handle_tick(self, tick_data: Dict[str, Any]) -> None:
        """Update unrealized P&L (cache only for performance)."""
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')
        
        if not all([instrument_token, last_price]):
            return
        
        updated_portfolios = []
        for portfolio in self.portfolios.values():
            if instrument_token in portfolio.positions:
                position = portfolio.positions[instrument_token]
                if self._update_unrealized_pnl(position, last_price):
                    portfolio.update_totals()
                    updated_portfolios.append(portfolio)
        
        # Only cache update for ticks (database persistence handled separately)
        for portfolio in updated_portfolios:
            await self.cache.save_portfolio(portfolio)
    
    async def get_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Get portfolio with option to reconcile."""
        portfolio = await self._get_or_create_portfolio(portfolio_id)
        return portfolio.model_dump()
    
    async def reconcile_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Reconcile portfolio with Zerodha broker state."""
        try:
            portfolio = await self._get_or_create_portfolio(portfolio_id)
            reconciliation_result = await self.reconciler.reconcile_portfolio(
                portfolio_id, portfolio
            )
            
            if reconciliation_result.get("discrepancies_found"):
                # Update portfolio with reconciled data
                reconciled_portfolio = reconciliation_result.get("reconciled_portfolio")
                if reconciled_portfolio:
                    self.portfolios[portfolio_id] = reconciled_portfolio
                    await self.persister.persist_portfolio(reconciled_portfolio)
                    await self.cache.save_portfolio(reconciled_portfolio)
                    
                    self.logger.warning("Portfolio reconciliation found discrepancies",
                                      portfolio_id=portfolio_id,
                                      discrepancies=reconciliation_result.get("discrepancies"))
            
            return reconciliation_result
            
        except Exception as e:
            self.logger.error("Portfolio reconciliation failed",
                            portfolio_id=portfolio_id, error=str(e))
            return {"status": "reconciliation_failed", "error": str(e)}
    
    async def _periodic_reconciliation_loop(self) -> None:
        """Periodic reconciliation with broker."""
        while True:
            try:
                await asyncio.sleep(self.reconciliation_interval)
                
                for portfolio_id in list(self.portfolios.keys()):
                    await self.reconcile_portfolio(portfolio_id)
                    # Small delay between reconciliations to avoid rate limits
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in reconciliation loop", error=str(e))
    
    async def _get_or_create_portfolio(self, portfolio_id: str) -> Portfolio:
        """Thread-safe portfolio creation."""
        # Fast path: portfolio exists
        if portfolio_id in self.portfolios:
            return self.portfolios[portfolio_id]
        
        # Get or create lock
        async with self._portfolio_locks_lock:
            if portfolio_id not in self._portfolio_locks:
                self._portfolio_locks[portfolio_id] = asyncio.Lock()
            lock = self._portfolio_locks[portfolio_id]
        
        # Create portfolio under lock
        async with lock:
            if portfolio_id not in self.portfolios:
                # Try cache first, then database
                portfolio = await self.cache.get_portfolio(portfolio_id)
                if not portfolio:
                    portfolio = await self.persister.load_portfolio(portfolio_id)
                    if not portfolio:
                        portfolio = Portfolio(
                            portfolio_id=portfolio_id,
                            cash=self.settings.zerodha.starting_cash if hasattr(self.settings, 'zerodha') else 1000000.0
                        )
                        self.logger.info("Created new Zerodha portfolio", 
                                       portfolio_id=portfolio_id)
                
                self.portfolios[portfolio_id] = portfolio
            
            return self.portfolios[portfolio_id]
    
    async def _process_fill(self, portfolio: Portfolio, fill_data: Dict[str, Any]) -> None:
        """Process fill with Zerodha trading specific logic."""
        instrument_token = fill_data.get('instrument_token')
        signal_type = fill_data.get('signal_type')
        quantity = fill_data.get('quantity', 0)
        fill_price = fill_data.get('fill_price', 0.0)
        
        position = portfolio.positions.get(
            instrument_token, 
            Position(instrument_token=instrument_token)
        )
        
        trade_value = quantity * fill_price
        
        if signal_type == 'BUY':
            self._update_buy_position(position, quantity, fill_price)
            portfolio.cash -= trade_value
        else:  # SELL
            pnl = self._update_sell_position(position, quantity, fill_price)
            portfolio.total_realized_pnl += pnl
            portfolio.cash += trade_value
        
        portfolio.positions[instrument_token] = position
        portfolio.update_last_modified()
        portfolio.update_totals()
    
    def _update_buy_position(self, position: Position, quantity: int, fill_price: float) -> None:
        """Update position for buy order."""
        if position.quantity > 0:
            total_cost = (position.average_price * position.quantity) + (quantity * fill_price)
            position.quantity += quantity
            position.average_price = total_cost / position.quantity
        else:
            position.quantity = quantity
            position.average_price = fill_price
    
    def _update_sell_position(self, position: Position, quantity: int, fill_price: float) -> float:
        """Update position for sell order and return realized P&L."""
        pnl = 0.0
        if position.quantity > 0:
            pnl = (fill_price - position.average_price) * quantity
            position.realized_pnl += pnl
        
        position.quantity -= quantity
        return pnl
    
    def _update_unrealized_pnl(self, position: Position, last_price: float) -> bool:
        """Update position's unrealized P&L. Returns True if changed."""
        old_pnl = position.unrealized_pnl
        position.last_price = last_price
        position.calculate_unrealized_pnl()
        return position.unrealized_pnl != old_pnl
    
    async def _recover_portfolios_from_database(self) -> None:
        """Recover portfolio states from database snapshots if cache is empty"""
        try:
            portfolios = await self.persister.load_all_portfolios("zerodha")
            recovered_count = 0
            
            for portfolio in portfolios:
                # Check if portfolio exists in cache
                cached_portfolio = await self.cache.get_portfolio(portfolio.portfolio_id)
                if cached_portfolio:
                    continue  # Cache is up-to-date
                
                # Store in memory and cache
                self.portfolios[portfolio.portfolio_id] = portfolio
                await self.cache.save_portfolio(portfolio)
                recovered_count += 1
                
                self.logger.info("Recovered Zerodha portfolio from database",
                               portfolio_id=portfolio.portfolio_id,
                               total_pnl=portfolio.total_pnl,
                               positions=len(portfolio.positions))
            
            if recovered_count > 0:
                self.logger.info(f"Recovered {recovered_count} Zerodha portfolios from database")
            else:
                self.logger.info("No Zerodha portfolio recovery needed - cache is current")
                
        except Exception as e:
            self.logger.error("Failed to recover Zerodha portfolios from database", error=str(e))
    
    async def _persist_all_portfolios(self) -> None:
        """Persist all portfolios to database."""
        if not self.portfolios:
            return
        
        try:
            saved_count = 0
            for portfolio in self.portfolios.values():
                await self.persister.persist_portfolio(portfolio)
                saved_count += 1
            
            self.logger.info("Persisted all Zerodha portfolios to database", count=saved_count)
            
        except Exception as e:
            self.logger.error("Failed to persist Zerodha portfolios", error=str(e))