"""Paper trading engine - main orchestrator for simulated trading."""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal

from core.utils.exceptions import TradingError, ValidationError
from core.config.settings import settings
from core.events import EventBusCore, get_event_publisher, subscriber
from core.events.event_types import TradingEvent, RiskEvent
from core.events.event_types import EventFactory, EventType
from core.logging.logger import get_logger
from risk_manager.risk_manager import RiskManager

from .orders import PaperOrderManager
from .portfolio import PaperPortfolio
from .models import PaperOrder, PaperAccount
from .types import (
    OrderType,
    OrderSide,
    ProductType,
    ExchangeType,
    TimeInForce
)


# Global paper trading engine instance for decorator handlers
_paper_trading_engine_instance: Optional['PaperTradingEngine'] = None


@subscriber.on_event("trading.signal.*", durable_name="paper-trading-signals")
async def handle_trading_signal_paper(event: TradingEvent) -> None:
    """Handle trading signal events for paper trading execution.
    
    This decorator-based handler routes trading signals to the paper trading engine.
    """
    global _paper_trading_engine_instance
    if _paper_trading_engine_instance:
        await _paper_trading_engine_instance._handle_trading_signal_event(event)


@subscriber.on_event("risk.alert.*", durable_name="paper-trading-risk")
async def handle_risk_alert_paper(event: RiskEvent) -> None:
    """Handle risk alert events for paper trading."""
    global _paper_trading_engine_instance
    if _paper_trading_engine_instance:
        await _paper_trading_engine_instance._handle_risk_alert_event(event)


class PaperTradingEngine:
    """Main paper trading engine coordinating all trading activities."""
    
    def __init__(
        self,
        initial_capital: Decimal = Decimal("1000000"),
        risk_manager: Optional[RiskManager] = None,
        event_bus: Optional[EventBusCore] = None
    ):
        """Initialize paper trading engine."""
        self.logger = get_logger(__name__)
        self.event_bus = event_bus
        
        # Core components
        self.order_manager = PaperOrderManager(event_bus=event_bus)
        self.portfolio = PaperPortfolio(
            initial_capital=initial_capital,
            order_manager=self.order_manager,
            event_bus=event_bus
        )
        self.risk_manager = risk_manager
        
        # Engine state
        self.is_running = False
        self.market_data_subscriptions: Dict[int, List[Callable]] = {}
        
        # Trading settings
        self.auto_risk_check = True
        self.auto_position_update = True
        self.market_hours_only = False
        
        # Statistics
        self.engine_stats = {
            "start_time": None,
            "orders_processed": 0,
            "trades_executed": 0,
            "risk_checks_performed": 0,
            "uptime_seconds": 0
        }
        
        self.logger.info("PaperTradingEngine initialized")
    
    async def initialize(self) -> bool:
        """Initialize the paper trading engine."""
        try:
            # Initialize components
            await self.order_manager.initialize()
            await self.portfolio.initialize()
            
            if self.risk_manager:
                # Create default risk profiles if none exist
                await self._setup_default_risk_profiles()
            
            # Setup event subscriptions
            await self._setup_event_subscriptions()
            
            self.is_running = True
            self.engine_stats["start_time"] = datetime.utcnow()
            
            self.logger.info("Paper trading engine initialization completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Paper trading engine initialization failed: {e}")
            return False

    async def _publish_event(self, subject: str, event):
        """Helper method to publish events using the new event publisher service."""
        from core.events import get_event_publisher
        from core.config.settings import Settings
        try:
            settings = Settings()  # Get settings instance for event publisher
            event_publisher = get_event_publisher(settings)
            await event_publisher.publish(subject, event)
        except Exception as e:
            self.logger.error(f"Failed to publish event to {subject}: {e}")
            # Don't raise exception to avoid breaking main functionality

    async def start(self) -> None:
        """Start the paper trading engine."""
        try:
            if not self.is_running:
                self.logger.warning("Paper trading engine not properly initialized - calling initialize first")
                if not await self.initialize():
                    raise TradingError("Failed to initialize paper trading engine")
            
            # Set global instance for decorator handlers
            global _paper_trading_engine_instance
            _paper_trading_engine_instance = self
            self.logger.info("✅ Paper trading engine registered for event subscriptions")
            
            self.logger.info("Paper trading engine started successfully")
            self.logger.info("📄 Paper trading engine is now ready to process trading signals")
            
        except Exception as e:
            self.logger.error(f"Paper trading engine start failed: {e}")
            raise TradingError(f"Failed to start paper trading engine: {e}")
    
    async def stop(self) -> None:
        """Stop the trading engine (alias for shutdown)."""
        await self.shutdown()
    
    async def shutdown(self) -> None:
        """Graceful shutdown of the trading engine."""
        try:
            self.is_running = False
            
            # Clear global instance
            global _paper_trading_engine_instance
            _paper_trading_engine_instance = None
            self.logger.info("Paper trading engine unregistered from event subscriptions")
            
            # Shutdown components
            await self.order_manager.shutdown()
            await self.portfolio.shutdown()
            
            # Update final statistics
            if self.engine_stats["start_time"]:
                uptime = datetime.utcnow() - self.engine_stats["start_time"]
                self.engine_stats["uptime_seconds"] = uptime.total_seconds()
            
            self.logger.info("Paper trading engine shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Paper trading engine shutdown failed: {e}")
    
    # Trading Interface
    
    async def place_order(
        self,
        strategy_name: str,
        instrument_token: int,
        tradingsymbol: str,
        exchange: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        product: str = "MIS",
        tag: Optional[str] = None,
        bypass_risk_check: bool = False
    ) -> PaperOrder:
        """Place a paper trading order."""
        try:
            if not self.is_running:
                raise TradingError("Paper trading engine is not running")
            
            # Convert types
            exchange_enum = ExchangeType(exchange)
            side_enum = OrderSide(side)
            order_type_enum = OrderType(order_type)
            product_enum = ProductType(product)
            
            # Risk check if enabled
            if self.auto_risk_check and self.risk_manager and not bypass_risk_check:
                risk_check = await self.risk_manager.check_order_risk(
                    strategy_name=strategy_name,
                    instrument_token=instrument_token,
                    action=side,
                    quantity=quantity,
                    price=price or 0,
                    order_value=Decimal(str(quantity * (price or 100)))  # Estimate value
                )
                
                self.engine_stats["risk_checks_performed"] += 1
                
                if not risk_check.passed:
                    self.logger.warning(f"Risk check failed for order: {risk_check.violations}")
                    raise TradingError(f"Risk check failed: {[v.message for v in risk_check.violations]}")
            
            # Ensure account exists
            await self.portfolio.get_or_create_account(strategy_name)
            
            # Place order
            order = await self.order_manager.place_order(
                strategy_name=strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange_enum,
                side=side_enum,
                order_type=order_type_enum,
                quantity=quantity,
                price=Decimal(str(price)) if price else None,
                trigger_price=Decimal(str(trigger_price)) if trigger_price else None,
                product=product_enum,
                tag=tag
            )
            
            self.engine_stats["orders_processed"] += 1
            
            # Setup order fill monitoring
            await self._monitor_order_fills(order)
            
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to place order: {e}")
            raise TradingError(f"Failed to place order: {e}")
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            return await self.order_manager.cancel_order(order_id)
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            raise TradingError(f"Failed to cancel order: {e}")
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> PaperOrder:
        """Modify an existing order."""
        try:
            return await self.order_manager.modify_order(
                order_id=order_id,
                quantity=quantity,
                price=Decimal(str(price)) if price else None,
                trigger_price=Decimal(str(trigger_price)) if trigger_price else None
            )
        except Exception as e:
            self.logger.error(f"Failed to modify order {order_id}: {e}")
            raise TradingError(f"Failed to modify order: {e}")
    
    # Market Data Interface
    
    async def update_market_data(self, instrument_token: int, market_data: Dict[str, Any]) -> None:
        """Update market data for trading simulation."""
        try:
            # Update order manager (for order execution)
            await self.order_manager.update_market_data(instrument_token, market_data)
            
            # Update portfolio (for position P&L)
            await self.portfolio.update_market_data(instrument_token, market_data)
            
            # Update risk manager positions if enabled
            if self.risk_manager and "last_price" in market_data:
                # This would update position values for risk calculations
                # Implementation depends on risk manager interface
                pass
            
            # Notify subscribers
            if instrument_token in self.market_data_subscriptions:
                for callback in self.market_data_subscriptions[instrument_token]:
                    try:
                        await callback(instrument_token, market_data)
                    except Exception as e:
                        self.logger.error(f"Market data callback error: {e}")
            
        except Exception as e:
            self.logger.error(f"Failed to update market data for {instrument_token}: {e}")
    
    def subscribe_market_data(self, instrument_token: int, callback: Callable) -> None:
        """Subscribe to market data updates for an instrument."""
        if instrument_token not in self.market_data_subscriptions:
            self.market_data_subscriptions[instrument_token] = []
        
        self.market_data_subscriptions[instrument_token].append(callback)
        self.logger.debug(f"Subscribed to market data for instrument {instrument_token}")
    
    def unsubscribe_market_data(self, instrument_token: int, callback: Callable) -> None:
        """Unsubscribe from market data updates."""
        if instrument_token in self.market_data_subscriptions:
            try:
                self.market_data_subscriptions[instrument_token].remove(callback)
                self.logger.debug(f"Unsubscribed from market data for instrument {instrument_token}")
            except ValueError:
                pass  # Callback not found
    
    # Query Interface
    
    async def get_orders(
        self,
        strategy_name: Optional[str] = None,
        instrument_token: Optional[int] = None
    ) -> List[PaperOrder]:
        """Get orders with optional filters."""
        return await self.order_manager.get_orders(
            strategy_name=strategy_name,
            instrument_token=instrument_token
        )
    
    async def get_positions(self, strategy_name: str) -> List[Dict[str, Any]]:
        """Get positions for strategy."""
        positions = await self.portfolio.get_positions(strategy_name)
        return [pos.to_dict() for pos in positions]
    
    async def get_account(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """Get account information for strategy."""
        account = await self.portfolio.get_account(strategy_name)
        return account.to_dict() if account else None
    
    async def get_portfolio_summary(self, strategy_name: str) -> Dict[str, Any]:
        """Get comprehensive portfolio summary."""
        return await self.portfolio.get_portfolio_summary(strategy_name)
    
    async def get_performance_metrics(
        self,
        strategy_name: str,
        period_days: int = 30
    ) -> Dict[str, Any]:
        """Get performance metrics for specified period."""
        return await self.portfolio.get_performance_metrics(strategy_name, period_days)
    
    # Statistics and Monitoring
    
    async def get_engine_statistics(self) -> Dict[str, Any]:
        """Get engine performance statistics."""
        try:
            current_time = datetime.utcnow()
            uptime = 0
            
            if self.engine_stats["start_time"]:
                uptime = (current_time - self.engine_stats["start_time"]).total_seconds()
            
            order_stats = await self.order_manager.get_order_statistics()
            
            return {
                "engine_status": "running" if self.is_running else "stopped",
                "start_time": self.engine_stats["start_time"].isoformat() if self.engine_stats["start_time"] else None,
                "uptime_seconds": uptime,
                "orders_processed": self.engine_stats["orders_processed"],
                "trades_executed": self.engine_stats["trades_executed"],
                "risk_checks_performed": self.engine_stats["risk_checks_performed"],
                "active_subscriptions": len(self.market_data_subscriptions),
                "order_statistics": order_stats,
                "components_status": {
                    "order_manager": "running" if self.order_manager.processing_enabled else "stopped",
                    "portfolio": "running" if self.portfolio.position_tracking_enabled else "stopped",
                    "risk_manager": "enabled" if self.risk_manager else "disabled"
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get engine statistics: {e}")
            return {"error": str(e)}
    
    async def get_risk_status(self, strategy_name: str) -> Dict[str, Any]:
        """Get risk status for strategy."""
        if not self.risk_manager:
            return {"status": "risk_manager_disabled"}
        
        return await self.risk_manager.get_risk_status(strategy_name)
    
    # Configuration
    
    def configure_trading_settings(
        self,
        auto_risk_check: Optional[bool] = None,
        auto_position_update: Optional[bool] = None,
        market_hours_only: Optional[bool] = None
    ) -> None:
        """Configure trading engine settings."""
        if auto_risk_check is not None:
            self.auto_risk_check = auto_risk_check
            self.logger.info(f"Auto risk check {'enabled' if auto_risk_check else 'disabled'}")
        
        if auto_position_update is not None:
            self.auto_position_update = auto_position_update
            self.logger.info(f"Auto position update {'enabled' if auto_position_update else 'disabled'}")
        
        if market_hours_only is not None:
            self.market_hours_only = market_hours_only
            self.logger.info(f"Market hours only {'enabled' if market_hours_only else 'disabled'}")
    
    def configure_order_execution(
        self,
        slippage_bps: Optional[int] = None,
        commission_bps: Optional[int] = None,
        fill_probability: Optional[float] = None,
        partial_fill_probability: Optional[float] = None
    ) -> None:
        """Configure order execution simulation parameters."""
        if slippage_bps is not None:
            self.order_manager.slippage_bps = slippage_bps
            self.logger.info(f"Slippage set to {slippage_bps} bps")
        
        if commission_bps is not None:
            self.order_manager.commission_bps = commission_bps
            self.logger.info(f"Commission set to {commission_bps} bps")
        
        if fill_probability is not None:
            self.order_manager.fill_probability = fill_probability
            self.logger.info(f"Fill probability set to {fill_probability}")
        
        if partial_fill_probability is not None:
            self.order_manager.partial_fill_probability = partial_fill_probability
            self.logger.info(f"Partial fill probability set to {partial_fill_probability}")
    
    # Private Methods
    
    async def _setup_default_risk_profiles(self) -> None:
        """Setup default risk profiles for common strategies."""
        try:
            if self.risk_manager:
                # Create a default profile if none exist
                default_exists = await self.risk_manager.get_risk_profile("default")
                if not default_exists:
                    from risk_manager.models import PositionLimit, LossLimit
                    
                    await self.risk_manager.create_risk_profile(
                        strategy_name="default",
                        position_limits=[
                            PositionLimit(
                                strategy_name="default",
                                max_value=Decimal("50000"),  # 50k max position
                                max_percentage=5.0  # 5% of portfolio
                            )
                        ],
                        loss_limits=[
                            LossLimit(
                                strategy_name="default",
                                max_daily_loss=Decimal("5000"),  # 5k daily loss limit
                                max_drawdown_pct=10.0  # 10% max drawdown
                            )
                        ]
                    )
                    
                    self.logger.info("Default risk profile created")
        
        except Exception as e:
            self.logger.error(f"Failed to setup default risk profiles: {e}")
    
    async def _setup_event_subscriptions(self) -> None:
        """Setup event bus subscriptions."""
        try:
            # Event subscriptions are now handled by decorator-based handlers
            # @subscriber.on_event decorators at module level handle all subscriptions
            # No manual subscription needed here
            self.logger.info("Event subscriptions setup completed via decorator handlers")
        
        except Exception as e:
            self.logger.error(f"Failed to setup event subscriptions: {e}")
    
    async def _handle_order_fill_event(self, event_data: str) -> None:
        """Handle order fill events."""
        try:
            # Parse event data and update portfolio
            import json
            event = json.loads(event_data)
            
            # This would extract order fill information and update positions
            # Implementation depends on event structure
            
        except Exception as e:
            self.logger.error(f"Failed to handle order fill event: {e}")
    
    async def _monitor_order_fills(self, order: PaperOrder) -> None:
        """Monitor order for fills and update portfolio accordingly."""
        try:
            # This would setup monitoring for when the order gets filled
            # and automatically update portfolio positions
            
            # For now, we'll use a simple callback approach
            original_add_fill = order.add_fill
            
            async def enhanced_add_fill(fill):
                # Call original method
                original_add_fill(fill)
                
                # Update portfolio
                if self.auto_position_update:
                    await self.portfolio.update_position_from_fill(
                        fill, order.to_dict()
                    )
                
                # Update statistics
                if order.status.value in ["FILLED", "PARTIALLY_FILLED"]:
                    self.engine_stats["trades_executed"] += 1
                
                # Update risk manager if available
                if self.risk_manager:
                    await self.risk_manager.update_position(
                        strategy_name=order.strategy_name,
                        instrument_token=order.instrument_token,
                        quantity=order.filled_quantity if order.side == OrderSide.BUY else -order.filled_quantity,
                        value=order.total_value
                    )
            
            # Replace the method (this is a simple approach)
            order.add_fill = enhanced_add_fill
            
        except Exception as e:
            self.logger.error(f"Failed to setup order fill monitoring: {e}")
    
    async def _handle_trading_signal_event(self, event: TradingEvent) -> None:
        """Handle trading signal events for paper trading execution.
        
        Args:
            event: Trading signal event from new event system
        """
        try:
            self.logger.info(f"Received trading signal for paper trading: {event.source}")
            
            # Extract signal data from event
            if hasattr(event, 'data') and event.data:
                signal_data = event.data
                
                # Process the trading signal - this would typically involve:
                # 1. Validating the signal
                # 2. Converting to paper order
                # 3. Executing the order
                
                self.logger.info(f"Processing paper trading signal: {signal_data}")
                
        except Exception as e:
            self.logger.error(f"Error handling trading signal for paper trading: {e}")
    
    async def _handle_risk_alert_event(self, event: RiskEvent) -> None:
        """Handle risk alert events for paper trading.
        
        Args:
            event: Risk alert event from new event system
        """
        try:
            self.logger.warning(f"Risk alert received for paper trading: {event.source}")
            
            # Handle risk alerts - this could involve:
            # 1. Stopping trading if critical alert
            # 2. Reducing position sizes
            # 3. Logging for monitoring
            
            if hasattr(event, 'data') and event.data:
                alert_data = event.data
                self.logger.warning(f"Risk alert details: {alert_data}")
                
        except Exception as e:
            self.logger.error(f"Error handling risk alert for paper trading: {e}")
    
    # Context Manager Support
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()