"""Zerodha order management for live trading."""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal

from core.utils.exceptions import TradingError, AuthenticationError
from core.config.settings import settings
from core.events import EventBusCore
from core.events.event_types import EventFactory, EventType
from core.logging.logger import get_logger
from core.auth.auth_manager import AuthManager

from .models import ZerodhaOrder, ZerodhaTrade
from .types import (
    ZerodhaOrderType,
    ZerodhaOrderStatus,
    ZerodhaProductType,
    ZerodhaValidityType,
    ZerodhaVarietyType,
    ZerodhaTransactionType,
    ZerodhaExchange
)


class ZerodhaOrderManager:
    """Manages live trading orders with Zerodha KiteConnect."""
    
    def __init__(
        self,
        auth_manager: AuthManager,
        event_bus: Optional[EventBusCore] = None
    ):
        """Initialize Zerodha order manager."""
        self.logger = get_logger(__name__)
        self.event_bus = event_bus
        self.auth_manager = auth_manager
        
        # Order storage
        self.orders: Dict[str, ZerodhaOrder] = {}
        self.trades: Dict[str, List[ZerodhaTrade]] = {}
        
        # KiteConnect client (will be set after authentication)
        self.kite = None
        
        # Order monitoring
        self.monitoring_enabled = True
        self.order_update_interval = 1.0  # Check orders every second
        
        # Statistics
        self.stats = {
            "orders_placed": 0,
            "orders_filled": 0,
            "orders_cancelled": 0,
            "orders_rejected": 0,
            "api_calls": 0,
            "api_errors": 0
        }
        
        self.logger.info("ZerodhaOrderManager initialized")
    
    async def initialize(self) -> None:
        """Initialize order manager with authentication."""
        try:
            # Ensure authentication
            await self.auth_manager.ensure_authenticated()
            self.kite = self.auth_manager.get_kite_client()
            
            if not self.kite:
                raise AuthenticationError("Zerodha authentication required for live trading")
            
            # Start order monitoring
            if self.monitoring_enabled:
                asyncio.create_task(self._order_monitoring_loop())
            
            self.logger.info("Zerodha order manager initialization completed")
            
        except Exception as e:
            self.logger.error(f"Zerodha order manager initialization failed: {e}")
            raise TradingError(f"Failed to initialize Zerodha order manager: {e}")
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        try:
            self.monitoring_enabled = False
            self.logger.info("Zerodha order manager shutdown completed")
        except Exception as e:
            self.logger.error(f"Zerodha order manager shutdown failed: {e}")
    
    # Order Placement
    
    async def place_order(
        self,
        strategy_name: str,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        order_type: str,
        quantity: int,
        product: str = "MIS",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        validity: str = "DAY",
        variety: str = "regular",
        disclosed_quantity: Optional[int] = None,
        tag: Optional[str] = None
    ) -> ZerodhaOrder:
        """Place order with Zerodha."""
        try:
            if not self.kite:
                raise TradingError("Zerodha client not initialized")
            
            # Convert types
            exchange_enum = ZerodhaExchange(exchange)
            transaction_type_enum = ZerodhaTransactionType(transaction_type)
            order_type_enum = ZerodhaOrderType(order_type)
            product_enum = ZerodhaProductType(product)
            validity_enum = ZerodhaValidityType(validity)
            variety_enum = ZerodhaVarietyType(variety)
            
            # Create order object
            order = ZerodhaOrder(
                order_id="",  # Will be set after placing
                strategy_name=strategy_name,
                tradingsymbol=tradingsymbol,
                exchange=exchange_enum,
                instrument_token=0,  # Will be fetched from instruments
                transaction_type=transaction_type_enum,
                order_type=order_type_enum,
                product=product_enum,
                variety=variety_enum,
                quantity=quantity,
                price=Decimal(str(price)) if price else None,
                trigger_price=Decimal(str(trigger_price)) if trigger_price else None,
                validity=validity_enum,
                disclosed_quantity=disclosed_quantity,
                tag=tag
            )
            
            # Prepare order parameters
            order_params = order.to_kite_params()
            
            # Place order with Kite
            try:
                self.stats["api_calls"] += 1
                order_id = await self._call_kite_api(
                    self.kite.place_order,
                    **order_params
                )
                
                # Update order with received ID
                order.order_id = order_id
                
                # Try to get instrument token
                try:
                    instruments = await self._get_instruments(exchange)
                    for instrument in instruments:
                        if instrument.get("tradingsymbol") == tradingsymbol:
                            order.instrument_token = instrument.get("instrument_token", 0)
                            break
                except Exception as e:
                    self.logger.warning(f"Failed to get instrument token: {e}")
                
                # Store order
                self.orders[order_id] = order
                self.stats["orders_placed"] += 1
                
                # Publish order placed event
                if self.event_bus:
                    await self._publish_order_event(order, "order_placed")
                
                self.logger.info(f"Order placed: {order_id} - {transaction_type} {quantity} {tradingsymbol}")
                return order
                
            except Exception as kite_error:
                self.stats["api_errors"] += 1
                self.stats["orders_rejected"] += 1
                
                # Update order status
                order.status = ZerodhaOrderStatus.REJECTED
                order.status_message = str(kite_error)
                
                # Still store for tracking
                order.order_id = f"REJ_{int(datetime.utcnow().timestamp() * 1000000)}"
                self.orders[order.order_id] = order
                
                self.logger.error(f"Order placement failed: {kite_error}")
                raise TradingError(f"Order placement failed: {kite_error}")
            
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
            if not self.kite:
                raise TradingError("Zerodha client not initialized")
            
            order = self.orders.get(order_id)
            if not order:
                raise TradingError(f"Order not found: {order_id}")
            
            if order.status not in [ZerodhaOrderStatus.OPEN, ZerodhaOrderStatus.TRIGGER_PENDING]:
                raise TradingError(f"Order {order_id} cannot be modified in status: {order.status}")
            
            # Prepare modification parameters
            modify_params = {}
            
            if quantity is not None:
                modify_params["quantity"] = quantity
                order.quantity = quantity
            
            if price is not None:
                modify_params["price"] = price
                order.price = Decimal(str(price))
            
            if trigger_price is not None:
                modify_params["trigger_price"] = trigger_price
                order.trigger_price = Decimal(str(trigger_price))
            
            if order_type is not None:
                modify_params["order_type"] = order_type
                order.order_type = ZerodhaOrderType(order_type)
            
            if validity is not None:
                modify_params["validity"] = validity
                order.validity = ZerodhaValidityType(validity)
            
            # Modify order with Kite
            self.stats["api_calls"] += 1
            result = await self._call_kite_api(
                self.kite.modify_order,
                variety=order.variety.value,
                order_id=order_id,
                **modify_params
            )
            
            # Update order status
            order.status = ZerodhaOrderStatus.MODIFY_PENDING
            
            # Publish order modified event
            if self.event_bus:
                await self._publish_order_event(order, "order_modified")
            
            self.logger.info(f"Order modified: {order_id}")
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to modify order {order_id}: {e}")
            self.stats["api_errors"] += 1
            raise TradingError(f"Failed to modify order: {e}")
    
    async def cancel_order(
        self,
        order_id: str,
        variety: Optional[str] = None
    ) -> bool:
        """Cancel order."""
        try:
            if not self.kite:
                raise TradingError("Zerodha client not initialized")
            
            order = self.orders.get(order_id)
            if not order:
                raise TradingError(f"Order not found: {order_id}")
            
            if order.status not in [ZerodhaOrderStatus.OPEN, ZerodhaOrderStatus.TRIGGER_PENDING]:
                raise TradingError(f"Order {order_id} cannot be cancelled in status: {order.status}")
            
            # Use order's variety if not specified
            variety_to_use = variety or order.variety.value
            
            # Cancel order with Kite
            self.stats["api_calls"] += 1
            result = await self._call_kite_api(
                self.kite.cancel_order,
                variety=variety_to_use,
                order_id=order_id
            )
            
            # Update order status
            order.status = ZerodhaOrderStatus.CANCEL_PENDING
            self.stats["orders_cancelled"] += 1
            
            # Publish order cancelled event
            if self.event_bus:
                await self._publish_order_event(order, "order_cancelled")
            
            self.logger.info(f"Order cancelled: {order_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            self.stats["api_errors"] += 1
            raise TradingError(f"Failed to cancel order: {e}")
    
    # Order Query
    
    async def get_order(self, order_id: str) -> Optional[ZerodhaOrder]:
        """Get order by ID."""
        return self.orders.get(order_id)
    
    async def get_orders(
        self,
        strategy_name: Optional[str] = None,
        status: Optional[ZerodhaOrderStatus] = None
    ) -> List[ZerodhaOrder]:
        """Get orders with optional filters."""
        orders = list(self.orders.values())
        
        if strategy_name:
            orders = [o for o in orders if o.strategy_name == strategy_name]
        
        if status:
            orders = [o for o in orders if o.status == status]
        
        return sorted(orders, key=lambda o: o.order_timestamp, reverse=True)
    
    async def get_order_history(self, order_id: str) -> List[Dict[str, Any]]:
        """Get order history from Kite."""
        try:
            if not self.kite:
                raise TradingError("Zerodha client not initialized")
            
            self.stats["api_calls"] += 1
            history = await self._call_kite_api(
                self.kite.order_history,
                order_id=order_id
            )
            
            return history
            
        except Exception as e:
            self.logger.error(f"Failed to get order history for {order_id}: {e}")
            self.stats["api_errors"] += 1
            return []
    
    async def get_trades(
        self,
        strategy_name: Optional[str] = None
    ) -> List[ZerodhaTrade]:
        """Get trades with optional filter."""
        all_trades = []
        for trades in self.trades.values():
            all_trades.extend(trades)
        
        if strategy_name:
            all_trades = [t for t in all_trades if t.strategy_name == strategy_name]
        
        return sorted(all_trades, key=lambda t: t.fill_timestamp, reverse=True)
    
    # Order Updates and Monitoring
    
    async def refresh_orders(self) -> None:
        """Refresh all orders from Kite API."""
        try:
            if not self.kite:
                return
            
            self.stats["api_calls"] += 1
            kite_orders = await self._call_kite_api(self.kite.orders)
            
            for kite_order in kite_orders:
                order_id = kite_order.get("order_id")
                if order_id and order_id in self.orders:
                    order = self.orders[order_id]
                    old_status = order.status
                    
                    # Update order from Kite data
                    order.update_from_kite_order(kite_order)
                    
                    # Check for status changes
                    if old_status != order.status:
                        await self._handle_order_status_change(order, old_status)
            
        except Exception as e:
            self.logger.error(f"Failed to refresh orders: {e}")
            self.stats["api_errors"] += 1
    
    async def refresh_trades(self) -> None:
        """Refresh trades from Kite API."""
        try:
            if not self.kite:
                return
            
            self.stats["api_calls"] += 1
            kite_trades = await self._call_kite_api(self.kite.trades)
            
            for kite_trade in kite_trades:
                trade_id = kite_trade.get("trade_id")
                order_id = kite_trade.get("order_id")
                
                if trade_id and order_id and order_id in self.orders:
                    order = self.orders[order_id]
                    
                    # Check if we already have this trade
                    existing_trades = self.trades.get(order_id, [])
                    if not any(t.trade_id == trade_id for t in existing_trades):
                        # Create new trade
                        trade = ZerodhaTrade(
                            trade_id=trade_id,
                            strategy_name=order.strategy_name,
                            order_id=order_id,
                            exchange_order_id=kite_trade.get("exchange_order_id", ""),
                            tradingsymbol=order.tradingsymbol,
                            exchange=order.exchange,
                            instrument_token=order.instrument_token,
                            transaction_type=order.transaction_type,
                            product=order.product,
                            quantity=kite_trade.get("quantity", 0),
                            price=Decimal(str(kite_trade.get("price", 0))),
                            value=Decimal(str(kite_trade.get("value", 0))),
                            fill_timestamp=datetime.utcnow()  # Will be updated from API
                        )
                        
                        trade.update_from_kite_trade(kite_trade)
                        
                        # Store trade
                        if order_id not in self.trades:
                            self.trades[order_id] = []
                        self.trades[order_id].append(trade)
                        
                        # Publish trade event
                        if self.event_bus:
                            await self._publish_trade_event(trade)
            
        except Exception as e:
            self.logger.error(f"Failed to refresh trades: {e}")
            self.stats["api_errors"] += 1
    
    # Private Methods
    
    async def _order_monitoring_loop(self) -> None:
        """Background order monitoring loop."""
        while self.monitoring_enabled:
            try:
                await self.refresh_orders()
                await self.refresh_trades()
                await asyncio.sleep(self.order_update_interval)
            except Exception as e:
                self.logger.error(f"Order monitoring loop error: {e}")
                await asyncio.sleep(5)  # Wait longer on errors
    
    async def _handle_order_status_change(
        self,
        order: ZerodhaOrder,
        old_status: ZerodhaOrderStatus
    ) -> None:
        """Handle order status changes."""
        try:
            if order.status == ZerodhaOrderStatus.COMPLETE:
                self.stats["orders_filled"] += 1
                await self._publish_order_event(order, "order_filled")
            
            elif order.status == ZerodhaOrderStatus.CANCELLED:
                if old_status != ZerodhaOrderStatus.CANCEL_PENDING:
                    self.stats["orders_cancelled"] += 1
                await self._publish_order_event(order, "order_cancelled")
            
            elif order.status == ZerodhaOrderStatus.REJECTED:
                if old_status != ZerodhaOrderStatus.REJECTED:
                    self.stats["orders_rejected"] += 1
                await self._publish_order_event(order, "order_rejected")
            
            self.logger.debug(f"Order status changed: {order.order_id} {old_status} -> {order.status}")
            
        except Exception as e:
            self.logger.error(f"Failed to handle order status change: {e}")
    
    async def _call_kite_api(self, method, **kwargs):
        """Call Kite API method with error handling."""
        try:
            # For async operations, we need to handle this differently
            # This is a placeholder for proper async Kite integration
            return method(**kwargs)
        except Exception as e:
            self.logger.error(f"Kite API call failed: {e}")
            raise
    
    async def _get_instruments(self, exchange: str) -> List[Dict[str, Any]]:
        """Get instruments for exchange."""
        try:
            if not self.kite:
                return []
            
            self.stats["api_calls"] += 1
            instruments = await self._call_kite_api(
                self.kite.instruments,
                exchange=exchange
            )
            
            return instruments
            
        except Exception as e:
            self.logger.error(f"Failed to get instruments for {exchange}: {e}")
            return []
    
    async def _publish_order_event(self, order: ZerodhaOrder, event_type: str) -> None:
        """Publish order event."""
        try:
            if self.event_bus:
                event_map = {
                    "order_placed": EventType.ORDER_PLACED,
                    "order_filled": EventType.ORDER_FILLED,
                    "order_cancelled": EventType.ORDER_CANCELLED,
                    "order_modified": EventType.ORDER_FILLED,  # Using filled for modifications
                    "order_rejected": EventType.ORDER_REJECTED
                }
                
                event = EventFactory.create_order_event(
                    event_type=event_map.get(event_type, EventType.ORDER_PLACED),
                    strategy_name=order.strategy_name,
                    order_id=order.order_id,
                    instrument_token=order.instrument_token,
                    action=order.transaction_type.value,
                    quantity=order.quantity,
                    price=order.price,
                    data=order.to_dict()
                )
                
                await self.event_bus.publish(f"trading.order.{event_type}", event)
        
        except Exception as e:
            self.logger.error(f"Failed to publish order event: {e}")
    
    async def _publish_trade_event(self, trade: ZerodhaTrade) -> None:
        """Publish trade event."""
        try:
            if self.event_bus:
                event = EventFactory.create_system_event(
                    component="zerodha_order_manager",
                    severity="INFO",
                    message=f"Trade executed: {trade.tradingsymbol}",
                    event_type=EventType.ORDER_FILLED,
                    details=trade.to_dict()
                )
                
                await self.event_bus.publish("trading.trade.executed", event)
        
        except Exception as e:
            self.logger.error(f"Failed to publish trade event: {e}")
    
    # Statistics
    
    async def get_order_statistics(self) -> Dict[str, Any]:
        """Get order execution statistics."""
        try:
            total_orders = len(self.orders)
            active_orders = len([o for o in self.orders.values() if o.status == ZerodhaOrderStatus.OPEN])
            
            return {
                **self.stats,
                "total_orders": total_orders,
                "active_orders": active_orders,
                "fill_rate": (self.stats["orders_filled"] / total_orders * 100) if total_orders > 0 else 0,
                "rejection_rate": (self.stats["orders_rejected"] / total_orders * 100) if total_orders > 0 else 0,
                "api_error_rate": (self.stats["api_errors"] / max(1, self.stats["api_calls"]) * 100)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get order statistics: {e}")
            return {"error": str(e)}