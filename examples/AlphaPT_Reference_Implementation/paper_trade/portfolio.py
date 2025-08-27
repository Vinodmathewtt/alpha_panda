"""Paper trading portfolio management."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
from collections import defaultdict

from core.utils.exceptions import TradingError
from core.config.settings import settings
from core.events import EventBusCore
from core.events.event_types import EventFactory, EventType
from core.logging.logger import get_logger

from .models import PaperPosition, PaperAccount, PaperTrade, OrderFill
from .types import OrderSide, ExchangeType, ProductType
from .orders import PaperOrderManager


class PaperPortfolio:
    """Manages paper trading portfolio and positions."""
    
    def __init__(
        self,
        initial_capital: Decimal = Decimal("1000000"),  # 10L default
        order_manager: Optional[PaperOrderManager] = None,
        event_bus: Optional[EventBusCore] = None
    ):
        """Initialize portfolio manager."""
        self.logger = get_logger(__name__)
        self.event_bus = event_bus
        self.order_manager = order_manager
        
        # Portfolio state
        self.accounts: Dict[str, PaperAccount] = {}
        self.positions: Dict[str, Dict[int, PaperPosition]] = defaultdict(dict)
        self.trades: Dict[str, List[PaperTrade]] = defaultdict(list)
        
        # Configuration
        self.initial_capital = initial_capital
        self.margin_multiplier = Decimal("5")  # 5x margin
        self.position_tracking_enabled = True
        
        # Market data cache
        self.market_data: Dict[int, Dict[str, Any]] = {}
        
        # Performance tracking
        self.portfolio_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.last_update_time = datetime.utcnow()
        
        self.logger.info("PaperPortfolio initialized")
    
    async def initialize(self) -> None:
        """Initialize portfolio manager."""
        try:
            # Start portfolio monitoring
            if self.position_tracking_enabled:
                asyncio.create_task(self._portfolio_monitoring_loop())
            
            self.logger.info("Paper portfolio initialization completed")
        except Exception as e:
            self.logger.error(f"Paper portfolio initialization failed: {e}")
            raise TradingError(f"Failed to initialize portfolio: {e}")
    
    async def _publish_event(self, subject: str, event):
        """Helper method to publish events using the new event publisher service."""
        from core.events import get_event_publisher
        from core.config.settings import Settings
        try:
            settings = Settings()
            event_publisher = get_event_publisher(settings)
            await event_publisher.publish(subject, event)
        except Exception as e:
            self.logger.error(f"Failed to publish event to {subject}: {e}")
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        try:
            self.position_tracking_enabled = False
            await self._save_portfolio_state()
            
            self.logger.info("Paper portfolio shutdown completed")
        except Exception as e:
            self.logger.error(f"Paper portfolio shutdown failed: {e}")
    
    # Account Management
    
    async def create_account(
        self,
        strategy_name: str,
        initial_capital: Optional[Decimal] = None
    ) -> PaperAccount:
        """Create paper trading account for strategy."""
        try:
            if strategy_name in self.accounts:
                raise TradingError(f"Account already exists for strategy: {strategy_name}")
            
            capital = initial_capital or self.initial_capital
            
            account = PaperAccount(
                account_id=f"PA_{strategy_name}_{int(datetime.utcnow().timestamp())}",
                strategy_name=strategy_name,
                initial_capital=capital,
                current_capital=capital,
                available_margin=capital * self.margin_multiplier
            )
            
            self.accounts[strategy_name] = account
            
            self.logger.info(f"Created paper account for {strategy_name} with capital {capital}")
            return account
            
        except Exception as e:
            self.logger.error(f"Failed to create account for {strategy_name}: {e}")
            raise TradingError(f"Failed to create account: {e}")
    
    async def get_account(self, strategy_name: str) -> Optional[PaperAccount]:
        """Get account for strategy."""
        return self.accounts.get(strategy_name)
    
    async def get_or_create_account(self, strategy_name: str) -> PaperAccount:
        """Get existing account or create new one."""
        account = await self.get_account(strategy_name)
        if not account:
            account = await self.create_account(strategy_name)
        return account
    
    # Position Management
    
    async def update_position_from_fill(self, fill: OrderFill, order_data: Dict[str, Any]) -> None:
        """Update position from order fill."""
        try:
            strategy_name = order_data["strategy_name"]
            instrument_token = order_data["instrument_token"]
            tradingsymbol = order_data["tradingsymbol"]
            exchange = ExchangeType(order_data["exchange"])
            side = OrderSide(order_data["side"])
            product = ProductType(order_data.get("product", "MIS"))
            
            # Get or create position
            position = await self._get_or_create_position(
                strategy_name, instrument_token, tradingsymbol, exchange, product
            )
            
            # Update position from trade
            position.update_from_trade(
                side=side,
                quantity=fill.quantity,
                price=fill.price,
                is_day_trade=True
            )
            
            # Update account
            account = await self.get_or_create_account(strategy_name)
            
            # Calculate trade impact on account
            trade_value = fill.value + fill.commission
            if side == OrderSide.BUY:
                account.used_margin += trade_value
                account.available_margin -= trade_value
            else:
                account.used_margin -= trade_value
                account.available_margin += trade_value
                
                # Add realized P&L from sell
                if position.quantity >= 0:  # Was long, now selling
                    account.realized_pnl += fill.value - (fill.quantity * position.average_price)
            
            account.updated_at = datetime.utcnow()
            
            # Check for completed trades (round trips)
            await self._check_for_completed_trades(strategy_name, position, fill, order_data)
            
            # Publish position update event
            if self.event_bus:
                await self._publish_position_event(position)
            
            self.logger.debug(
                f"Position updated: {strategy_name} {tradingsymbol} - "
                f"Qty: {position.quantity}, Avg: {position.average_price}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to update position from fill: {e}")
            raise TradingError(f"Failed to update position: {e}")
    
    async def get_position(
        self,
        strategy_name: str,
        instrument_token: int
    ) -> Optional[PaperPosition]:
        """Get position for strategy and instrument."""
        return self.positions[strategy_name].get(instrument_token)
    
    async def get_positions(
        self,
        strategy_name: str,
        include_zero: bool = False
    ) -> List[PaperPosition]:
        """Get all positions for strategy."""
        positions = list(self.positions[strategy_name].values())
        
        if not include_zero:
            positions = [p for p in positions if p.quantity != 0]
        
        return sorted(positions, key=lambda p: p.updated_at, reverse=True)
    
    async def update_position_market_price(
        self,
        strategy_name: str,
        instrument_token: int,
        market_price: Decimal
    ) -> None:
        """Update position with current market price."""
        try:
            position = await self.get_position(strategy_name, instrument_token)
            if position:
                position.update_market_price(market_price)
                
                # Update account unrealized P&L
                await self._update_account_unrealized_pnl(strategy_name)
        
        except Exception as e:
            self.logger.error(f"Failed to update position market price: {e}")
    
    # Market Data Updates
    
    async def update_market_data(self, instrument_token: int, market_data: Dict[str, Any]) -> None:
        """Update market data and position P&L."""
        try:
            self.market_data[instrument_token] = {
                **market_data,
                "updated_at": datetime.utcnow()
            }
            
            last_price = Decimal(str(market_data.get("last_price", 0)))
            if last_price > 0:
                # Update all positions for this instrument
                for strategy_name in self.positions.keys():
                    await self.update_position_market_price(
                        strategy_name, instrument_token, last_price
                    )
            
        except Exception as e:
            self.logger.error(f"Failed to update market data for {instrument_token}: {e}")
    
    # Trade Tracking
    
    async def get_trades(
        self,
        strategy_name: str,
        limit: Optional[int] = None
    ) -> List[PaperTrade]:
        """Get trades for strategy."""
        trades = self.trades[strategy_name]
        
        if limit:
            trades = trades[-limit:]  # Get most recent trades
        
        return sorted(trades, key=lambda t: t.trade_date, reverse=True)
    
    # Portfolio Analytics
    
    async def get_portfolio_summary(self, strategy_name: str) -> Dict[str, Any]:
        """Get comprehensive portfolio summary."""
        try:
            account = await self.get_account(strategy_name)
            if not account:
                return {"error": "Account not found"}
            
            positions = await self.get_positions(strategy_name, include_zero=False)
            trades = await self.get_trades(strategy_name)
            
            # Calculate portfolio metrics
            total_position_value = sum(p.market_value for p in positions)
            total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)
            total_realized_pnl = sum(t.profit for t in trades)
            
            # Risk metrics
            max_position_size = max([abs(p.market_value) for p in positions], default=0)
            concentration_risk = (max_position_size / account.equity * 100) if account.equity != 0 else 0
            
            # Performance metrics
            winning_trades = [t for t in trades if t.profit > 0]
            losing_trades = [t for t in trades if t.profit <= 0]
            
            return {
                "strategy_name": strategy_name,
                "account": account.to_dict(),
                "portfolio_metrics": {
                    "total_position_value": float(total_position_value),
                    "total_unrealized_pnl": float(total_unrealized_pnl),
                    "total_realized_pnl": float(total_realized_pnl),
                    "equity": float(account.equity),
                    "available_margin": float(account.available_margin),
                    "used_margin": float(account.used_margin),
                    "margin_utilization_pct": float((account.used_margin / account.available_margin) * 100) if account.available_margin != 0 else 0
                },
                "positions": {
                    "count": len(positions),
                    "long_positions": len([p for p in positions if p.is_long]),
                    "short_positions": len([p for p in positions if p.is_short]),
                    "positions": [p.to_dict() for p in positions]
                },
                "trades": {
                    "total_trades": len(trades),
                    "winning_trades": len(winning_trades),
                    "losing_trades": len(losing_trades),
                    "win_rate": (len(winning_trades) / len(trades) * 100) if trades else 0,
                    "avg_profit": float(sum(t.profit for t in trades) / len(trades)) if trades else 0,
                    "best_trade": float(max([t.profit for t in trades], default=0)),
                    "worst_trade": float(min([t.profit for t in trades], default=0))
                },
                "risk_metrics": {
                    "max_position_size": float(max_position_size),
                    "concentration_risk_pct": float(concentration_risk),
                    "max_drawdown": float(account.max_drawdown),
                    "current_drawdown": float(max(0, getattr(account, '_peak_capital', account.initial_capital) - account.current_capital))
                },
                "updated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get portfolio summary for {strategy_name}: {e}")
            return {"error": str(e)}
    
    async def get_performance_metrics(
        self,
        strategy_name: str,
        period_days: int = 30
    ) -> Dict[str, Any]:
        """Get performance metrics for specified period."""
        try:
            account = await self.get_account(strategy_name)
            if not account:
                return {"error": "Account not found"}
            
            # Get historical performance data
            history = self.portfolio_history[strategy_name]
            cutoff_date = datetime.utcnow() - timedelta(days=period_days)
            
            period_history = [
                h for h in history 
                if datetime.fromisoformat(h["timestamp"]) >= cutoff_date
            ]
            
            if not period_history:
                return {"error": "No historical data available for period"}
            
            # Calculate metrics
            start_value = period_history[0]["equity"]
            end_value = period_history[-1]["equity"]
            max_value = max(h["equity"] for h in period_history)
            min_value = min(h["equity"] for h in period_history)
            
            total_return = end_value - start_value
            total_return_pct = (total_return / start_value * 100) if start_value != 0 else 0
            max_drawdown = max_value - min_value
            max_drawdown_pct = (max_drawdown / max_value * 100) if max_value != 0 else 0
            
            # Calculate volatility (daily returns standard deviation)
            daily_returns = []
            for i in range(1, len(period_history)):
                prev_value = period_history[i-1]["equity"]
                curr_value = period_history[i]["equity"]
                if prev_value != 0:
                    daily_return = (curr_value - prev_value) / prev_value
                    daily_returns.append(daily_return)
            
            volatility = 0
            if daily_returns:
                mean_return = sum(daily_returns) / len(daily_returns)
                variance = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns)
                volatility = (variance ** 0.5) * (252 ** 0.5)  # Annualized volatility
            
            # Sharpe ratio (assuming 6% risk-free rate)
            risk_free_rate = 0.06
            avg_daily_return = sum(daily_returns) / len(daily_returns) if daily_returns else 0
            annualized_return = avg_daily_return * 252
            sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility != 0 else 0
            
            return {
                "strategy_name": strategy_name,
                "period_days": period_days,
                "start_date": period_history[0]["timestamp"],
                "end_date": period_history[-1]["timestamp"],
                "start_value": start_value,
                "end_value": end_value,
                "total_return": total_return,
                "total_return_pct": total_return_pct,
                "max_value": max_value,
                "min_value": min_value,
                "max_drawdown": max_drawdown,
                "max_drawdown_pct": max_drawdown_pct,
                "volatility": volatility,
                "sharpe_ratio": sharpe_ratio,
                "data_points": len(period_history)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get performance metrics for {strategy_name}: {e}")
            return {"error": str(e)}
    
    # Private Methods
    
    async def _get_or_create_position(
        self,
        strategy_name: str,
        instrument_token: int,
        tradingsymbol: str,
        exchange: ExchangeType,
        product: ProductType
    ) -> PaperPosition:
        """Get existing position or create new one."""
        position = self.positions[strategy_name].get(instrument_token)
        
        if not position:
            position = PaperPosition(
                strategy_name=strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                product=product
            )
            self.positions[strategy_name][instrument_token] = position
        
        return position
    
    async def _check_for_completed_trades(
        self,
        strategy_name: str,
        position: PaperPosition,
        fill: OrderFill,
        order_data: Dict[str, Any]
    ) -> None:
        """Check for completed round-trip trades."""
        # For now, we'll track trades when positions are closed
        # This is a simplified implementation - a more sophisticated version
        # would track individual buy/sell pairs
        pass
    
    async def _update_account_unrealized_pnl(self, strategy_name: str) -> None:
        """Update account unrealized P&L from all positions."""
        try:
            account = await self.get_account(strategy_name)
            if not account:
                return
            
            positions = await self.get_positions(strategy_name, include_zero=True)
            total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)
            
            account.update_unrealized_pnl(total_unrealized_pnl)
            
        except Exception as e:
            self.logger.error(f"Failed to update account unrealized P&L: {e}")
    
    async def _portfolio_monitoring_loop(self) -> None:
        """Background portfolio monitoring loop."""
        while self.position_tracking_enabled:
            try:
                await self._update_portfolio_history()
                await asyncio.sleep(60)  # Update every minute
            except Exception as e:
                self.logger.error(f"Portfolio monitoring loop error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on errors
    
    async def _update_portfolio_history(self) -> None:
        """Update portfolio performance history."""
        try:
            for strategy_name, account in self.accounts.items():
                # Update unrealized P&L first
                await self._update_account_unrealized_pnl(strategy_name)
                
                # Record snapshot
                snapshot = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "equity": float(account.equity),
                    "current_capital": float(account.current_capital),
                    "unrealized_pnl": float(account.unrealized_pnl),
                    "realized_pnl": float(account.realized_pnl),
                    "total_pnl": float(account.total_pnl),
                    "used_margin": float(account.used_margin),
                    "available_margin": float(account.available_margin)
                }
                
                self.portfolio_history[strategy_name].append(snapshot)
                
                # Keep only last 1000 entries (for memory efficiency)
                if len(self.portfolio_history[strategy_name]) > 1000:
                    self.portfolio_history[strategy_name] = self.portfolio_history[strategy_name][-1000:]
        
        except Exception as e:
            self.logger.error(f"Failed to update portfolio history: {e}")
    
    async def _publish_position_event(self, position: PaperPosition) -> None:
        """Publish position update event."""
        try:
            if self.event_bus:
                event = EventFactory.create_system_event(
                    component="paper_portfolio",
                    severity="INFO",
                    message=f"Position updated: {position.tradingsymbol}",
                    event_type=EventType.TRADING_SIGNAL_GENERATED,  # Using signal for position updates
                    details=position.to_dict()
                )
                await self._publish_event("trading.position.updated", event)
        
        except Exception as e:
            self.logger.error(f"Failed to publish position event: {e}")
    
    async def _save_portfolio_state(self) -> None:
        """Save portfolio state (placeholder for persistence)."""
        # In production, this would save to database
        pass