"""Zerodha live trading engine - main orchestrator for live trading."""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal

from core.utils.exceptions import TradingError, AuthenticationError
from core.config.settings import settings
from core.events import EventBusCore, get_event_publisher, subscriber
from core.events.event_types import TradingEvent, RiskEvent
from core.logging import get_trading_logger
from core.auth.auth_manager import AuthManager
from risk_manager.risk_manager import RiskManager

from .orders import ZerodhaOrderManager
from .positions import ZerodhaPositionManager
from .models import ZerodhaOrder, ZerodhaPosition, ZerodhaAccount


# Global Zerodha trading engine instance for decorator handlers
_zerodha_trading_engine_instance: Optional['ZerodhaTradeEngine'] = None


@subscriber.on_event("trading.signal.*", durable_name="zerodha-trading-signals")
async def handle_trading_signal_zerodha(event: TradingEvent) -> None:
    """Handle trading signal events for Zerodha live trading execution.
    
    This decorator-based handler routes trading signals to the Zerodha trading engine.
    """
    global _zerodha_trading_engine_instance
    if _zerodha_trading_engine_instance:
        await _zerodha_trading_engine_instance._handle_trading_signal_event(event)


@subscriber.on_event("risk.alert.*", durable_name="zerodha-trading-risk")
async def handle_risk_alert_zerodha(event: RiskEvent) -> None:
    """Handle risk alert events for Zerodha trading."""
    global _zerodha_trading_engine_instance
    if _zerodha_trading_engine_instance:
        await _zerodha_trading_engine_instance._handle_risk_alert_event(event)


class ZerodhaTradeEngine:
    """Main Zerodha trading engine for live trading operations."""
    
    def __init__(
        self,
        auth_manager: AuthManager,
        risk_manager: Optional[RiskManager] = None,
        event_bus: Optional[EventBusCore] = None
    ):
        """Initialize Zerodha trading engine."""
        self.logger = get_trading_logger("zerodha_trade_engine")
        self.event_bus = event_bus
        self.auth_manager = auth_manager
        self.risk_manager = risk_manager
        
        # Core components
        self.order_manager = ZerodhaOrderManager(
            auth_manager=auth_manager,
            event_bus=event_bus
        )
        self.position_manager = ZerodhaPositionManager(
            auth_manager=auth_manager,
            event_bus=event_bus
        )
        
        # Engine state
        self.is_running = False
        self.trading_enabled = True
        
        # Trading settings
        self.auto_risk_check = True
        self.auto_position_sync = True
        self.max_orders_per_minute = 100  # Rate limiting
        
        # Statistics
        self.engine_stats = {
            "start_time": None,
            "orders_processed": 0,
            "positions_synced": 0,
            "risk_checks_performed": 0,
            "api_calls": 0,
            "uptime_seconds": 0
        }
        
        # Rate limiting
        self.order_timestamps = []
        
        self.logger.info("ZerodhaTradeEngine initialized")
    
    async def initialize(self) -> None:
        """Initialize the Zerodha trading engine."""
        try:
            # Ensure authentication first
            await self.auth_manager.ensure_authenticated()
            
            # Initialize components
            await self.order_manager.initialize()
            await self.position_manager.initialize()
            
            # Setup risk profiles if risk manager is available
            if self.risk_manager:
                await self._setup_risk_integration()
            
            # Setup event subscriptions
            await self._setup_event_subscriptions()
            
            self.is_running = True
            self.engine_stats["start_time"] = datetime.utcnow()
            
            self.logger.info("Zerodha trading engine initialization completed")
            
        except Exception as e:
            self.logger.error(f"Zerodha trading engine initialization failed: {e}")
            raise TradingError(f"Failed to initialize Zerodha trading engine: {e}")

    async def start(self) -> None:
        """Start the Zerodha trading engine."""
        try:
            if not self.is_running:
                self.logger.warning("Zerodha trading engine not properly initialized - calling initialize first")
                await self.initialize()
            
            # Set global instance for decorator handlers
            global _zerodha_trading_engine_instance
            _zerodha_trading_engine_instance = self
            self.logger.info("✅ Zerodha trading engine registered for event subscriptions")
            
            self.logger.info("Zerodha trading engine started successfully")
            self.logger.info("💰 Zerodha trading engine is now ready to process live trading signals")
            
        except Exception as e:
            self.logger.error(f"Zerodha trading engine start failed: {e}")
            raise TradingError(f"Failed to start Zerodha trading engine: {e}")
    
    async def stop(self) -> None:
        """Stop the Zerodha trading engine (alias for shutdown)."""
        await self.shutdown()
    
    async def shutdown(self) -> None:
        """Graceful shutdown of the trading engine."""
        try:
            self.is_running = False
            self.trading_enabled = False
            
            # Clear global instance
            global _zerodha_trading_engine_instance
            _zerodha_trading_engine_instance = None
            self.logger.info("Zerodha trading engine unregistered from event subscriptions")
            
            # Shutdown components
            await self.order_manager.shutdown()
            await self.position_manager.shutdown()
            
            # Update final statistics
            if self.engine_stats["start_time"]:
                uptime = datetime.utcnow() - self.engine_stats["start_time"]
                self.engine_stats["uptime_seconds"] = uptime.total_seconds()
            
            self.logger.info("Zerodha trading engine shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Zerodha trading engine shutdown failed: {e}")
    
    # Trading Interface
    
    async def place_order(
        self,
        strategy_name: str,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        order_type: str,
        quantity: int,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        product: str = "MIS",
        validity: str = "DAY",
        variety: str = "regular",
        tag: Optional[str] = None,
        bypass_risk_check: bool = False
    ) -> ZerodhaOrder:
        """Place live trading order."""
        try:
            if not self.is_running:
                raise TradingError("Zerodha trading engine is not running")
            
            if not self.trading_enabled:
                raise TradingError("Trading is currently disabled")
            
            # Rate limiting check
            await self._check_rate_limits()
            
            # Risk check if enabled
            if self.auto_risk_check and self.risk_manager and not bypass_risk_check:
                risk_check = await self.risk_manager.check_order_risk(
                    strategy_name=strategy_name,
                    instrument_token=0,  # Will be fetched from instruments
                    action=transaction_type,
                    quantity=quantity,
                    price=price or 0,
                    order_value=Decimal(str(quantity * (price or 100)))  # Estimate value
                )
                
                self.engine_stats["risk_checks_performed"] += 1
                
                if not risk_check.passed:
                    self.logger.warning(f"Risk check failed for order: {risk_check.violations}")
                    raise TradingError(f"Risk check failed: {[v.message for v in risk_check.violations]}")
            
            # Place order
            order = await self.order_manager.place_order(
                strategy_name=strategy_name,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                transaction_type=transaction_type,
                order_type=order_type,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                product=product,
                validity=validity,
                variety=variety,
                tag=tag
            )
            
            self.engine_stats["orders_processed"] += 1
            self.engine_stats["api_calls"] += 1
            
            # Track order timestamp for rate limiting
            self.order_timestamps.append(datetime.utcnow())
            
            # Auto-sync positions if enabled
            if self.auto_position_sync:
                asyncio.create_task(self._delayed_position_sync())
            
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to place order: {e}")
            raise TradingError(f"Failed to place order: {e}")
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
        validity: Optional[str] = None
    ) -> ZerodhaOrder:
        """Modify existing order."""
        try:
            if not self.trading_enabled:
                raise TradingError("Trading is currently disabled")
            
            order = await self.order_manager.modify_order(
                order_id=order_id,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                order_type=order_type,
                validity=validity
            )
            
            self.engine_stats["api_calls"] += 1
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to modify order {order_id}: {e}")
            raise TradingError(f"Failed to modify order: {e}")
    
    async def cancel_order(self, order_id: str, variety: Optional[str] = None) -> bool:
        """Cancel order."""
        try:
            if not self.trading_enabled:
                raise TradingError("Trading is currently disabled")
            
            result = await self.order_manager.cancel_order(order_id, variety)
            self.engine_stats["api_calls"] += 1
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            raise TradingError(f"Failed to cancel order: {e}")
    
    # Position and Account Interface
    
    async def get_positions(self, strategy_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get positions."""
        try:
            if strategy_name:
                positions = await self.position_manager.get_positions(strategy_name)
            else:
                positions = await self.position_manager.get_all_positions()
            
            return [pos.to_dict() for pos in positions]
            
        except Exception as e:
            self.logger.error(f"Failed to get positions: {e}")
            return []
    
    async def get_account(self) -> Optional[Dict[str, Any]]:
        """Get account information."""
        try:
            account = await self.position_manager.get_account()
            return account.to_dict() if account else None
            
        except Exception as e:
            self.logger.error(f"Failed to get account: {e}")
            return None
    
    async def refresh_positions(self) -> None:
        """Manually refresh positions."""
        try:
            await self.position_manager.refresh_positions()
            self.engine_stats["positions_synced"] += 1
            self.engine_stats["api_calls"] += 1
            
        except Exception as e:
            self.logger.error(f"Failed to refresh positions: {e}")
    
    async def refresh_account(self) -> None:
        """Manually refresh account."""
        try:
            await self.position_manager.refresh_account()
            self.engine_stats["api_calls"] += 1
            
        except Exception as e:
            self.logger.error(f"Failed to refresh account: {e}")
    
    # Order and Trade Query
    
    async def get_orders(
        self,
        strategy_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get orders."""
        try:
            orders = await self.order_manager.get_orders(strategy_name=strategy_name)
            return [order.to_dict() for order in orders]
            
        except Exception as e:
            self.logger.error(f"Failed to get orders: {e}")
            return []
    
    async def get_trades(
        self,
        strategy_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get trades."""
        try:
            trades = await self.order_manager.get_trades(strategy_name=strategy_name)
            return [trade.to_dict() for trade in trades]
            
        except Exception as e:
            self.logger.error(f"Failed to get trades: {e}")
            return []
    
    async def get_order_history(self, order_id: str) -> List[Dict[str, Any]]:
        """Get order history."""
        try:
            history = await self.order_manager.get_order_history(order_id)
            return history
            
        except Exception as e:
            self.logger.error(f"Failed to get order history: {e}")
            return []
    
    # Portfolio Analysis
    
    async def get_portfolio_summary(self, strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """Get comprehensive portfolio summary."""
        try:
            return await self.position_manager.get_portfolio_summary(strategy_name)
            
        except Exception as e:
            self.logger.error(f"Failed to get portfolio summary: {e}")
            return {"error": str(e)}
    
    async def get_position_pnl(self, strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """Get position P&L breakdown."""
        try:
            return await self.position_manager.get_position_pnl(strategy_name)
            
        except Exception as e:
            self.logger.error(f"Failed to get position P&L: {e}")
            return {"error": str(e)}
    
    # Risk and Margin
    
    async def check_margin_requirement(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        price: float,
        product: str = "MIS"
    ) -> Dict[str, Any]:
        """Check margin requirement for potential order."""
        try:
            return await self.position_manager.check_margin_requirement(
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                transaction_type=transaction_type,
                quantity=quantity,
                price=price,
                product=product
            )
            
        except Exception as e:
            self.logger.error(f"Failed to check margin requirement: {e}")
            return {"error": str(e)}
    
    async def get_risk_status(self, strategy_name: str) -> Dict[str, Any]:
        """Get risk status for strategy."""
        if not self.risk_manager:
            return {"status": "risk_manager_disabled"}
        
        return await self.risk_manager.get_risk_status(strategy_name)
    
    # Engine Configuration
    
    def configure_trading_settings(
        self,
        trading_enabled: Optional[bool] = None,
        auto_risk_check: Optional[bool] = None,
        auto_position_sync: Optional[bool] = None,
        max_orders_per_minute: Optional[int] = None
    ) -> None:
        """Configure trading engine settings."""
        if trading_enabled is not None:
            self.trading_enabled = trading_enabled
            self.logger.info(f"Trading {'enabled' if trading_enabled else 'disabled'}")
        
        if auto_risk_check is not None:
            self.auto_risk_check = auto_risk_check
            self.logger.info(f"Auto risk check {'enabled' if auto_risk_check else 'disabled'}")
        
        if auto_position_sync is not None:
            self.auto_position_sync = auto_position_sync
            self.logger.info(f"Auto position sync {'enabled' if auto_position_sync else 'disabled'}")
        
        if max_orders_per_minute is not None:
            self.max_orders_per_minute = max_orders_per_minute
            self.logger.info(f"Max orders per minute set to {max_orders_per_minute}")
    
    # Statistics and Monitoring
    
    async def get_engine_statistics(self) -> Dict[str, Any]:
        """Get engine performance statistics."""
        try:
            current_time = datetime.utcnow()
            uptime = 0
            
            if self.engine_stats["start_time"]:
                uptime = (current_time - self.engine_stats["start_time"]).total_seconds()
            
            order_stats = await self.order_manager.get_order_statistics()
            position_stats = await self.position_manager.get_position_statistics()
            
            return {
                "engine_status": "running" if self.is_running else "stopped",
                "trading_enabled": self.trading_enabled,
                "start_time": self.engine_stats["start_time"].isoformat() if self.engine_stats["start_time"] else None,
                "uptime_seconds": uptime,
                "orders_processed": self.engine_stats["orders_processed"],
                "positions_synced": self.engine_stats["positions_synced"],
                "risk_checks_performed": self.engine_stats["risk_checks_performed"],
                "api_calls": self.engine_stats["api_calls"],
                "order_statistics": order_stats,
                "position_statistics": position_stats,
                "rate_limiting": {
                    "max_orders_per_minute": self.max_orders_per_minute,
                    "recent_orders": len([t for t in self.order_timestamps if (current_time - t).total_seconds() < 60])
                },
                "components_status": {
                    "order_manager": "running" if self.order_manager.monitoring_enabled else "stopped",
                    "position_manager": "running" if self.position_manager.monitoring_enabled else "stopped",
                    "risk_manager": "enabled" if self.risk_manager else "disabled"
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get engine statistics: {e}")
            return {"error": str(e)}
    
    # Private Methods
    
    async def _check_rate_limits(self) -> None:
        """Check rate limits for order placement."""
        try:
            current_time = datetime.utcnow()
            
            # Clean old timestamps (older than 1 minute)
            self.order_timestamps = [
                t for t in self.order_timestamps
                if (current_time - t).total_seconds() < 60
            ]
            
            # Check if we're exceeding rate limits
            if len(self.order_timestamps) >= self.max_orders_per_minute:
                raise TradingError(
                    f"Rate limit exceeded: {len(self.order_timestamps)} orders in last minute "
                    f"(max: {self.max_orders_per_minute})"
                )
        
        except Exception as e:
            if "Rate limit exceeded" in str(e):
                raise
            self.logger.error(f"Failed to check rate limits: {e}")
    
    async def _delayed_position_sync(self) -> None:
        """Delayed position sync to allow order processing."""
        try:
            # Wait a bit for order to be processed
            await asyncio.sleep(2)
            await self.refresh_positions()
        except Exception as e:
            self.logger.error(f"Failed delayed position sync: {e}")
    
    async def _setup_risk_integration(self) -> None:
        """Setup risk manager integration."""
        try:
            if self.risk_manager:
                # Create default risk profiles if needed
                # This could be enhanced to load specific profiles
                pass
        except Exception as e:
            self.logger.error(f"Failed to setup risk integration: {e}")
    
    async def _setup_event_subscriptions(self) -> None:
        """Setup event bus subscriptions."""
        try:
            if self.event_bus:
                # Subscribe to relevant events
                # This could include market data updates, position changes, etc.
                pass
        except Exception as e:
            self.logger.error(f"Failed to setup event subscriptions: {e}")
    
    async def _handle_trading_signal_event(self, event: TradingEvent) -> None:
        """Handle trading signal events for Zerodha live trading execution.
        
        Args:
            event: Trading signal event from new event system
        """
        try:
            self.logger.info(f"Received trading signal for Zerodha live trading: {event.source}")
            
            # Extract signal data from event
            if hasattr(event, 'data') and event.data:
                signal_data = event.data
                
                # Process the trading signal - this would typically involve:
                # 1. Validating authentication
                # 2. Risk management checks
                # 3. Converting to live order
                # 4. Executing via Zerodha API
                
                self.logger.info(f"Processing Zerodha live trading signal: {signal_data}")
                
                if not self.is_authenticated:
                    self.logger.error("Cannot process trading signal - not authenticated with Zerodha")
                    return
                    
                if not self.trading_enabled:
                    self.logger.warning("Trading is disabled - signal ignored")
                    return
                
        except Exception as e:
            self.logger.error(f"Error handling trading signal for Zerodha trading: {e}")
    
    async def _handle_risk_alert_event(self, event: RiskEvent) -> None:
        """Handle risk alert events for Zerodha trading.
        
        Args:
            event: Risk alert event from new event system
        """
        try:
            self.logger.warning(f"Risk alert received for Zerodha trading: {event.source}")
            
            # Handle risk alerts for live trading - this is critical:
            # 1. Stop all trading if critical alert
            # 2. Cancel pending orders
            # 3. Reduce position sizes
            # 4. Alert monitoring systems
            
            if hasattr(event, 'data') and event.data:
                alert_data = event.data
                self.logger.warning(f"Risk alert details: {alert_data}")
                
                # If critical risk alert, disable trading immediately
                if alert_data.get('severity') == 'critical':
                    self.logger.error("CRITICAL RISK ALERT - Disabling trading immediately")
                    self.trading_enabled = False
                
        except Exception as e:
            self.logger.error(f"Error handling risk alert for Zerodha trading: {e}")
    
    # Context Manager Support
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()