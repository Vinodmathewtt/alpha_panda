"""Paper trading order management."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from decimal import Decimal
from collections import defaultdict

from core.utils.exceptions import TradingError, ValidationError
from core.config.settings import settings
from core.events import EventBusCore
from core.events.event_types import EventFactory, EventType
from core.logging.logger import get_logger

from .models import PaperOrder, OrderFill
from .types import (
    OrderType,
    OrderStatus,
    OrderSide,
    TimeInForce,
    FillType,
    ProductType,
    ExchangeType,
    Price,
    Quantity
)


class PaperOrderManager:
    """Manages paper trading orders with realistic simulation."""
    
    def __init__(self, event_bus: Optional[EventBusCore] = None):
        """Initialize order manager."""
        self.logger = get_logger(__name__)
        self.event_bus = event_bus
        
        # Order storage
        self.orders: Dict[str, PaperOrder] = {}
        self.active_orders: Dict[str, PaperOrder] = {}
        
        # Market data for order execution
        self.market_data: Dict[int, Dict[str, Any]] = {}
        
        # Order execution settings - use configuration for realism
        self.slippage_percentage = settings.paper_slippage  # Use configured slippage percentage
        self.transaction_cost_percentage = settings.paper_transaction_cost  # Use configured transaction cost
        self.slippage_bps = 5  # Legacy fallback 
        self.commission_bps = 3  # Legacy fallback
        self.market_impact_threshold = 0.1  # 10% of volume threshold
        
        # Stop loss settings
        self.enable_stop_loss = settings.paper_enable_stop_loss
        self.default_stop_loss_percentage = settings.paper_stop_loss_percentage
        
        # Execution simulation
        self.fill_probability = 0.95  # 95% fill probability for limit orders
        self.partial_fill_probability = 0.1  # 10% chance of partial fills
        
        # Order processing state
        self.processing_enabled = True
        self.last_process_time = datetime.utcnow()
        
        self.logger.info("PaperOrderManager initialized")
    
    async def initialize(self) -> None:
        """Initialize order manager."""
        try:
            # Start order processing loop
            if self.processing_enabled:
                asyncio.create_task(self._order_processing_loop())
            
            self.logger.info("Paper order manager initialization completed")
        except Exception as e:
            self.logger.error(f"Paper order manager initialization failed: {e}")
            raise TradingError(f"Failed to initialize order manager: {e}")
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        try:
            self.processing_enabled = False
            # Cancel all pending orders
            for order in list(self.active_orders.values()):
                await self.cancel_order(order.order_id)
            
            self.logger.info("Paper order manager shutdown completed")
        except Exception as e:
            self.logger.error(f"Paper order manager shutdown failed: {e}")
    
    # Order Placement
    
    async def place_order(
        self,
        strategy_name: str,
        instrument_token: int,
        tradingsymbol: str,
        exchange: ExchangeType,
        side: OrderSide,
        order_type: OrderType,
        quantity: Quantity,
        price: Optional[Price] = None,
        trigger_price: Optional[Price] = None,
        product: ProductType = ProductType.MIS,
        disclosed_quantity: Optional[Quantity] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        tag: Optional[str] = None
    ) -> PaperOrder:
        """Place a paper trading order."""
        try:
            # Validate order parameters
            await self._validate_order_params(
                instrument_token, side, order_type, quantity, price, trigger_price
            )
            
            # Generate order ID
            order_id = f"PT{int(datetime.utcnow().timestamp() * 1000000)}"
            
            # Create order
            order = PaperOrder(
                order_id=order_id,
                strategy_name=strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                product=product,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                disclosed_quantity=disclosed_quantity,
                time_in_force=time_in_force,
                tag=tag
            )
            
            # Store order
            self.orders[order_id] = order
            
            # Handle immediate execution for market orders
            if order_type == OrderType.MARKET:
                await self._execute_market_order(order)
            else:
                # Add to active orders for processing
                order.status = OrderStatus.OPEN
                self.active_orders[order_id] = order
            
            order.updated_at = datetime.utcnow()
            
            # Publish order placed event
            if self.event_bus:
                await self._publish_order_event(order, "order_placed")
            
            self.logger.info(f"Order placed: {order_id} - {side.value} {quantity} {tradingsymbol}")
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to place order: {e}")
            raise TradingError(f"Failed to place order: {e}")
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            order = self.orders.get(order_id)
            if not order:
                raise TradingError(f"Order not found: {order_id}")
            
            if not order.is_active:
                raise TradingError(f"Order {order_id} is not active")
            
            # Cancel the order
            order.cancel()
            
            # Remove from active orders
            if order_id in self.active_orders:
                del self.active_orders[order_id]
            
            # Publish order cancelled event
            if self.event_bus:
                await self._publish_order_event(order, "order_cancelled")
            
            self.logger.info(f"Order cancelled: {order_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            raise TradingError(f"Failed to cancel order: {e}")
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[Quantity] = None,
        price: Optional[Price] = None,
        trigger_price: Optional[Price] = None
    ) -> PaperOrder:
        """Modify an existing order."""
        try:
            order = self.orders.get(order_id)
            if not order:
                raise TradingError(f"Order not found: {order_id}")
            
            if not order.is_active:
                raise TradingError(f"Order {order_id} is not active")
            
            # Update order parameters
            if quantity is not None:
                if quantity <= order.filled_quantity:
                    raise TradingError("New quantity must be greater than filled quantity")
                order.quantity = quantity
                order.pending_quantity = quantity - order.filled_quantity
            
            if price is not None:
                order.price = price
            
            if trigger_price is not None:
                order.trigger_price = trigger_price
            
            order.updated_at = datetime.utcnow()
            
            # Publish order modified event
            if self.event_bus:
                await self._publish_order_event(order, "order_modified")
            
            self.logger.info(f"Order modified: {order_id}")
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to modify order {order_id}: {e}")
            raise TradingError(f"Failed to modify order: {e}")
    
    # Order Query
    
    async def get_order(self, order_id: str) -> Optional[PaperOrder]:
        """Get order by ID."""
        return self.orders.get(order_id)
    
    async def get_orders(
        self,
        strategy_name: Optional[str] = None,
        instrument_token: Optional[int] = None,
        status: Optional[OrderStatus] = None
    ) -> List[PaperOrder]:
        """Get orders with optional filters."""
        orders = list(self.orders.values())
        
        if strategy_name:
            orders = [o for o in orders if o.strategy_name == strategy_name]
        
        if instrument_token:
            orders = [o for o in orders if o.instrument_token == instrument_token]
        
        if status:
            orders = [o for o in orders if o.status == status]
        
        return sorted(orders, key=lambda o: o.placed_at, reverse=True)
    
    async def get_active_orders(self, strategy_name: Optional[str] = None) -> List[PaperOrder]:
        """Get active orders."""
        orders = list(self.active_orders.values())
        
        if strategy_name:
            orders = [o for o in orders if o.strategy_name == strategy_name]
        
        return sorted(orders, key=lambda o: o.placed_at)
    
    # Market Data Updates
    
    async def update_market_data(self, instrument_token: int, market_data: Dict[str, Any]) -> None:
        """Update market data for order execution."""
        try:
            self.market_data[instrument_token] = {
                **market_data,
                "updated_at": datetime.utcnow()
            }
            
            # Process orders that might be triggered by this update
            await self._process_orders_for_instrument(instrument_token)
            
        except Exception as e:
            self.logger.error(f"Failed to update market data for {instrument_token}: {e}")
    
    # Order Execution Simulation
    
    async def _execute_market_order(self, order: PaperOrder) -> None:
        """Execute market order immediately."""
        try:
            market_data = self.market_data.get(order.instrument_token)
            if not market_data:
                # Use a default price if no market data available
                execution_price = order.price or Decimal("100.0")
            else:
                execution_price = Decimal(str(market_data.get("last_price", order.price or 100.0)))
            
            # Apply slippage for market orders
            slippage = self._calculate_slippage(execution_price, order.side, order.quantity)
            execution_price += slippage
            
            # Calculate commission
            commission = self._calculate_commission(order.quantity, execution_price)
            
            # Create fill
            fill = OrderFill(
                fill_id=str(uuid.uuid4()),
                order_id=order.order_id,
                fill_type=FillType.COMPLETE,
                quantity=order.quantity,
                price=execution_price,
                value=Decimal(str(order.quantity)) * execution_price,
                commission=commission,
                market_price=market_data.get("last_price") if market_data else None,
                slippage=slippage
            )
            
            # Apply fill to order
            order.add_fill(fill)
            
            # Remove from active orders
            if order.order_id in self.active_orders:
                del self.active_orders[order.order_id]
            
            # Publish order filled event
            if self.event_bus:
                await self._publish_order_event(order, "order_filled")
            
            self.logger.info(
                f"Market order executed: {order.order_id} - "
                f"{order.quantity} @ {execution_price}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to execute market order {order.order_id}: {e}")
            order.status = OrderStatus.REJECTED
            order.notes = f"Execution failed: {e}"
    
    async def _order_processing_loop(self) -> None:
        """Background order processing loop."""
        while self.processing_enabled:
            try:
                await self._process_all_orders()
                await asyncio.sleep(0.1)  # Process every 100ms
            except Exception as e:
                self.logger.error(f"Order processing loop error: {e}")
                await asyncio.sleep(1)  # Wait longer on errors
    
    async def _process_all_orders(self) -> None:
        """Process all active orders."""
        for order in list(self.active_orders.values()):
            try:
                await self._process_order(order)
            except Exception as e:
                self.logger.error(f"Failed to process order {order.order_id}: {e}")
    
    async def _process_orders_for_instrument(self, instrument_token: int) -> None:
        """Process orders for specific instrument."""
        relevant_orders = [
            order for order in self.active_orders.values()
            if order.instrument_token == instrument_token
        ]
        
        for order in relevant_orders:
            try:
                await self._process_order(order)
            except Exception as e:
                self.logger.error(f"Failed to process order {order.order_id}: {e}")
    
    async def _process_order(self, order: PaperOrder) -> None:
        """Process individual order for potential execution."""
        try:
            # Check if order has expired
            if await self._is_order_expired(order):
                order.status = OrderStatus.EXPIRED
                if order.order_id in self.active_orders:
                    del self.active_orders[order.order_id]
                return
            
            # Get market data
            market_data = self.market_data.get(order.instrument_token)
            if not market_data:
                return  # No market data to process against
            
            current_price = Decimal(str(market_data.get("last_price", 0)))
            if current_price <= 0:
                return
            
            # Check if order should be executed
            should_execute = await self._should_execute_order(order, current_price, market_data)
            
            if should_execute:
                await self._execute_limit_order(order, current_price, market_data)
            
        except Exception as e:
            self.logger.error(f"Failed to process order {order.order_id}: {e}")
    
    async def _should_execute_order(
        self,
        order: PaperOrder,
        current_price: Price,
        market_data: Dict[str, Any]
    ) -> bool:
        """Determine if order should be executed."""
        if order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY:
                return current_price <= Decimal(str(order.price))
            else:
                return current_price >= Decimal(str(order.price))
        
        elif order.order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_MARKET]:
            if order.side == OrderSide.BUY:
                return current_price >= Decimal(str(order.trigger_price))
            else:
                return current_price <= Decimal(str(order.trigger_price))
        
        return False
    
    async def _execute_limit_order(
        self,
        order: PaperOrder,
        current_price: Price,
        market_data: Dict[str, Any]
    ) -> None:
        """Execute limit order with realistic simulation."""
        try:
            # Determine execution price
            if order.order_type == OrderType.LIMIT:
                execution_price = Decimal(str(order.price))
            else:
                execution_price = current_price
            
            # Simulate partial fills
            fill_quantity = order.pending_quantity
            if (self.partial_fill_probability > 0 and 
                asyncio.get_running_loop().time() % 1 < self.partial_fill_probability):
                # Partial fill
                fill_quantity = min(
                    order.pending_quantity,
                    max(1, int(order.pending_quantity * 0.3))  # 30% partial fill
                )
            
            # Calculate commission
            commission = self._calculate_commission(fill_quantity, execution_price)
            
            # Create fill
            fill = OrderFill(
                fill_id=str(uuid.uuid4()),
                order_id=order.order_id,
                fill_type=FillType.PARTIAL if fill_quantity < order.pending_quantity else FillType.COMPLETE,
                quantity=fill_quantity,
                price=execution_price,
                value=Decimal(str(fill_quantity)) * execution_price,
                commission=commission,
                market_price=current_price
            )
            
            # Apply fill to order
            order.add_fill(fill)
            
            # Remove from active orders if completely filled
            if order.status == OrderStatus.FILLED:
                if order.order_id in self.active_orders:
                    del self.active_orders[order.order_id]
            
            # Publish order filled event
            if self.event_bus:
                await self._publish_order_event(order, "order_filled")
            
            self.logger.info(
                f"Limit order {'partially ' if fill.fill_type == FillType.PARTIAL else ''}filled: "
                f"{order.order_id} - {fill_quantity} @ {execution_price}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to execute limit order {order.order_id}: {e}")
    
    # Helper Methods
    
    async def _validate_order_params(
        self,
        instrument_token: int,
        side: OrderSide,
        order_type: OrderType,
        quantity: Quantity,
        price: Optional[Price],
        trigger_price: Optional[Price]
    ) -> None:
        """Validate order parameters."""
        if quantity <= 0:
            raise ValidationError("Quantity must be positive")
        
        if order_type == OrderType.LIMIT and price is None:
            raise ValidationError("Limit orders require a price")
        
        if order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_MARKET] and trigger_price is None:
            raise ValidationError("Stop orders require a trigger price")
        
        if price is not None and price <= 0:
            raise ValidationError("Price must be positive")
        
        if trigger_price is not None and trigger_price <= 0:
            raise ValidationError("Trigger price must be positive")
    
    async def _is_order_expired(self, order: PaperOrder) -> bool:
        """Check if order has expired."""
        if order.time_in_force == TimeInForce.DAY:
            # Day orders expire at market close (3:30 PM IST)
            # For simplicity, using 24 hours
            return (datetime.utcnow() - order.placed_at) > timedelta(hours=24)
        
        elif order.time_in_force == TimeInForce.IOC:
            # Immediate or Cancel - expire after 1 minute if not filled
            return (datetime.utcnow() - order.placed_at) > timedelta(minutes=1)
        
        return False
    
    def _calculate_slippage(self, price: Price, side: OrderSide, quantity: Quantity) -> Price:
        """Calculate realistic slippage using configured percentage."""
        # Use new percentage-based slippage if available, otherwise fallback to bps
        if hasattr(self, 'slippage_percentage'):
            base_slippage = Decimal(str(price)) * Decimal(str(self.slippage_percentage)) / Decimal("100")
        else:
            base_slippage = Decimal(str(price)) * (Decimal(str(self.slippage_bps)) / Decimal("10000"))
        
        # Apply direction-based slippage
        if side == OrderSide.BUY:
            return base_slippage  # Slippage increases price for buys
        else:
            return -base_slippage  # Slippage decreases price for sells
    
    def _calculate_commission(self, quantity: Quantity, price: Price) -> Decimal:
        """Calculate trading commission using configured percentage."""
        trade_value = Decimal(str(quantity)) * Decimal(str(price))
        
        # Use new percentage-based transaction cost if available, otherwise fallback to bps
        if hasattr(self, 'transaction_cost_percentage'):
            commission = trade_value * (Decimal(str(self.transaction_cost_percentage)) / Decimal("100"))
        else:
            commission = trade_value * (Decimal(str(self.commission_bps)) / Decimal("10000"))
        
        # Minimum commission (e.g., ₹20)
        min_commission = Decimal("20")
        
        return max(commission, min_commission)
    
    async def _publish_order_event(self, order: PaperOrder, event_type: str) -> None:
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
                    action=order.side.value,
                    quantity=order.quantity,
                    price=Decimal(str(order.price)) if order.price else None,
                    data=order.to_dict()
                )
                
                await self.event_bus.publish(f"trading.order.{event_type}", event)
        
        except Exception as e:
            self.logger.error(f"Failed to publish order event: {e}")
    
    # Statistics and Monitoring
    
    async def get_order_statistics(self, strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """Get order execution statistics."""
        try:
            orders = await self.get_orders(strategy_name=strategy_name)
            
            if not orders:
                return {"total_orders": 0}
            
            filled_orders = [o for o in orders if o.status == OrderStatus.FILLED]
            cancelled_orders = [o for o in orders if o.status == OrderStatus.CANCELLED]
            rejected_orders = [o for o in orders if o.status == OrderStatus.REJECTED]
            
            total_volume = sum(o.filled_quantity * (o.average_price or 0) for o in filled_orders)
            total_commission = sum(o.total_commission for o in filled_orders)
            
            return {
                "total_orders": len(orders),
                "filled_orders": len(filled_orders),
                "cancelled_orders": len(cancelled_orders),
                "rejected_orders": len(rejected_orders),
                "active_orders": len(self.active_orders),
                "fill_rate": len(filled_orders) / len(orders) * 100 if orders else 0,
                "total_volume": float(total_volume),
                "total_commission": float(total_commission),
                "avg_commission_per_order": float(total_commission / len(filled_orders)) if filled_orders else 0
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get order statistics: {e}")
            return {"error": str(e)}