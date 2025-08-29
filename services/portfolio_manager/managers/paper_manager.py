import asyncio
from typing import Dict, Any
from core.config.settings import Settings
from core.logging import get_trading_logger_safe
from ..interfaces.base_portfolio_manager import BasePortfolioManager
from ..models import Portfolio, Position
from ..cache import PortfolioCache


class PaperPortfolioManager(BasePortfolioManager):
    """Manages virtual (paper trading) portfolios with simple, fast logic."""
    
    def __init__(self, settings: Settings, redis_client):
        self.settings = settings
        self.cache = PortfolioCache(settings, redis_client)
        self.portfolios: Dict[str, Portfolio] = {}
        self.logger = get_trading_logger_safe("paper_portfolio_manager")
        
        # Concurrency control
        self._portfolio_locks: Dict[str, asyncio.Lock] = {}
        self._portfolio_locks_lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize paper portfolio manager."""
        self.logger.info("Starting Paper Portfolio Manager")
        await self.cache.initialize(namespace="paper")
        
        # Load existing paper portfolios from cache
        await self._load_portfolios_from_cache()
        
        self.logger.info("Paper Portfolio Manager started")
    
    async def start(self) -> None:
        """Start paper portfolio manager (alias for initialize)."""
        await self.initialize()
    
    async def shutdown(self) -> None:
        """Shutdown paper portfolio manager."""
        self.logger.info("Stopping Paper Portfolio Manager")
        
        # Persist final state to cache
        for portfolio in self.portfolios.values():
            await self.cache.save_portfolio(portfolio)
        
        await self.cache.close()
        self.logger.info("Paper Portfolio Manager stopped")
    
    async def stop(self) -> None:
        """Stop paper portfolio manager (alias for shutdown)."""
        await self.shutdown()
    
    async def handle_fill(self, fill_data: Dict[str, Any]) -> None:
        """Process fill event for paper portfolio."""
        strategy_id = fill_data.get('strategy_id')
        if not strategy_id:
            self.logger.warning("Fill missing strategy_id", fill_data=fill_data)
            return
        
        portfolio_id = f"paper_{strategy_id}"
        portfolio = await self._get_or_create_portfolio(portfolio_id)
        
        # Process fill with simplified paper trading logic
        await self._process_fill(portfolio, fill_data)
        
        # Save to cache immediately
        await self.cache.save_portfolio(portfolio)
        
        self.logger.info("Updated paper portfolio", 
                        portfolio_id=portfolio_id,
                        total_pnl=portfolio.total_pnl)
    
    async def handle_tick(self, tick_data: Dict[str, Any]) -> None:
        """Update unrealized P&L for all paper portfolios."""
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
        
        # Batch save updated portfolios
        for portfolio in updated_portfolios:
            await self.cache.save_portfolio(portfolio)
    
    async def get_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Get portfolio state."""
        portfolio = await self._get_or_create_portfolio(portfolio_id)
        return portfolio.model_dump()
    
    async def reconcile_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """For paper portfolios, reconciliation is a no-op."""
        self.logger.debug("Paper portfolio reconciliation not required", 
                         portfolio_id=portfolio_id)
        return {"status": "no_reconciliation_needed", "reason": "paper_trading"}
    
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
                portfolio = await self.cache.get_portfolio(portfolio_id)
                if not portfolio:
                    portfolio = Portfolio(
                        portfolio_id=portfolio_id,
                        cash=self.settings.paper_trading.starting_cash
                    )
                    self.logger.info("Created new paper portfolio", 
                                   portfolio_id=portfolio_id)
                
                self.portfolios[portfolio_id] = portfolio
            
            return self.portfolios[portfolio_id]
    
    async def _process_fill(self, portfolio: Portfolio, fill_data: Dict[str, Any]) -> None:
        """Process fill with paper trading specific logic."""
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
    
    async def _load_portfolios_from_cache(self) -> None:
        """Load existing paper portfolios from cache on startup."""
        # Implementation depends on cache design
        # For now, portfolios will be loaded on-demand
        pass
    
    # CRITICAL FIX: Add missing process_* methods for service compatibility
    async def process_fill(self, fill_data: Dict[str, Any]) -> None:
        """Process an order fill event (delegated to handle_fill)."""
        await self.handle_fill(fill_data)
    
    async def process_failure(self, failure_data: Dict[str, Any]) -> None:
        """Process an order failure event."""
        strategy_id = failure_data.get('strategy_id')
        error_message = failure_data.get('error_message', 'Unknown error')
        self.logger.warning("Order failure processed", 
                          strategy_id=strategy_id, 
                          error=error_message)
    
    async def process_submission(self, submission_data: Dict[str, Any]) -> None:
        """Process an order submission event."""
        strategy_id = submission_data.get('strategy_id')
        order_id = submission_data.get('order_id')
        self.logger.info("Order submission processed", 
                        strategy_id=strategy_id, 
                        order_id=order_id)
    
    def get_current_portfolio(self) -> Dict[str, Any]:
        """Get current portfolio state for PnL snapshots."""
        # Aggregate all portfolio data
        aggregated_data = {
            "total_portfolios": len(self.portfolios),
            "portfolios": {}
        }
        
        for portfolio_id, portfolio in self.portfolios.items():
            aggregated_data["portfolios"][portfolio_id] = portfolio.model_dump()
        
        return aggregated_data