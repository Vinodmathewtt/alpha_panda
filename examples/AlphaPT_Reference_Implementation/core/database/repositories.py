"""Repository classes for database operations."""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.utils.exceptions import DatabaseError
from core.database.models import (
    InstrumentMaster,
    Order,
    OrderStatus,
    Position,
    RiskMetric,
    StrategyMetadata,
    TradingSession,
)

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with common functionality."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        """Commit the current transaction."""
        try:
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Database commit failed: {e}")
            raise DatabaseError(f"Commit failed: {e}")

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        try:
            await self.session.rollback()
        except Exception as e:
            logger.error(f"Database rollback failed: {e}")


class OrderRepository(BaseRepository):
    """Repository for order operations."""

    async def create_order(self, order_data: Dict[str, Any]) -> Order:
        """Create a new order."""
        try:
            order = Order(**order_data)
            self.session.add(order)
            await self.session.flush()
            await self.session.refresh(order)
            return order
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            raise DatabaseError(f"Order creation failed: {e}")

    async def get_order_by_id(self, order_id: str) -> Optional[Order]:
        """Get order by order ID."""
        try:
            result = await self.session.execute(select(Order).where(Order.order_id == order_id))
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            raise DatabaseError(f"Order retrieval failed: {e}")

    async def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_quantity: Optional[int] = None,
        average_price: Optional[Decimal] = None,
        status_message: Optional[str] = None,
    ) -> bool:
        """Update order status and related fields."""
        try:
            update_data = {"status": status, "updated_at": datetime.now(timezone.utc)}

            if filled_quantity is not None:
                update_data["filled_quantity"] = filled_quantity
            if average_price is not None:
                update_data["average_price"] = average_price
            if status_message is not None:
                update_data["status_message"] = status_message

            result = await self.session.execute(update(Order).where(Order.order_id == order_id).values(**update_data))

            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update order {order_id}: {e}")
            raise DatabaseError(f"Order update failed: {e}")

    async def get_orders_by_strategy(
        self, strategy_name: str, limit: int = 100, status_filter: Optional[List[OrderStatus]] = None
    ) -> List[Order]:
        """Get orders by strategy name."""
        try:
            query = select(Order).where(Order.strategy_name == strategy_name)

            if status_filter:
                query = query.where(Order.status.in_(status_filter))

            query = query.order_by(Order.order_timestamp.desc()).limit(limit)

            result = await self.session.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get orders for strategy {strategy_name}: {e}")
            raise DatabaseError(f"Order retrieval failed: {e}")

    async def get_open_orders(self, strategy_name: Optional[str] = None) -> List[Order]:
        """Get all open orders."""
        try:
            query = select(Order).where(Order.status == OrderStatus.OPEN)

            if strategy_name:
                query = query.where(Order.strategy_name == strategy_name)

            result = await self.session.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            raise DatabaseError(f"Open orders retrieval failed: {e}")


class PositionRepository(BaseRepository):
    """Repository for position operations."""

    async def create_or_update_position(self, position_data: Dict[str, Any]) -> Position:
        """Create or update position."""
        try:
            # Try to find existing position
            result = await self.session.execute(
                select(Position).where(
                    and_(
                        Position.strategy_name == position_data["strategy_name"],
                        Position.tradingsymbol == position_data["tradingsymbol"],
                        Position.exchange == position_data["exchange"],
                        Position.product == position_data["product"],
                    )
                )
            )

            position = result.scalar_one_or_none()

            if position:
                # Update existing position
                for key, value in position_data.items():
                    setattr(position, key, value)
                position.updated_at = datetime.now(timezone.utc)
            else:
                # Create new position
                position = Position(**position_data)
                self.session.add(position)

            await self.session.flush()
            await self.session.refresh(position)
            return position
        except Exception as e:
            logger.error(f"Failed to create/update position: {e}")
            raise DatabaseError(f"Position operation failed: {e}")

    async def get_positions_by_strategy(self, strategy_name: str) -> List[Position]:
        """Get all positions for a strategy."""
        try:
            result = await self.session.execute(select(Position).where(Position.strategy_name == strategy_name))
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get positions for strategy {strategy_name}: {e}")
            raise DatabaseError(f"Position retrieval failed: {e}")

    async def get_position(
        self, strategy_name: str, tradingsymbol: str, exchange: str, product: str
    ) -> Optional[Position]:
        """Get specific position."""
        try:
            result = await self.session.execute(
                select(Position).where(
                    and_(
                        Position.strategy_name == strategy_name,
                        Position.tradingsymbol == tradingsymbol,
                        Position.exchange == exchange,
                        Position.product == product,
                    )
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get position: {e}")
            raise DatabaseError(f"Position retrieval failed: {e}")

    async def calculate_strategy_pnl(self, strategy_name: str) -> Decimal:
        """Calculate total PnL for a strategy."""
        try:
            result = await self.session.execute(
                select(func.sum(Position.pnl)).where(Position.strategy_name == strategy_name)
            )
            total_pnl = result.scalar_one_or_none()
            return total_pnl or Decimal("0.0")
        except Exception as e:
            logger.error(f"Failed to calculate PnL for strategy {strategy_name}: {e}")
            raise DatabaseError(f"PnL calculation failed: {e}")


class RiskMetricsRepository(BaseRepository):
    """Repository for risk metrics operations."""

    async def update_risk_metric(
        self, strategy_name: str, metric_type: str, metric_name: str, current_value: Decimal, limit_value: Decimal
    ) -> RiskMetric:
        """Update or create risk metric."""
        try:
            # Calculate utilization percentage
            utilization_pct = (current_value / limit_value * 100) if limit_value > 0 else 0

            # Determine breach status
            if utilization_pct >= 100:
                breach_status = "breached"
            elif utilization_pct >= 80:
                breach_status = "warning"
            else:
                breach_status = "safe"

            # Try to find existing metric
            result = await self.session.execute(
                select(RiskMetric).where(
                    and_(
                        RiskMetric.strategy_name == strategy_name,
                        RiskMetric.metric_type == metric_type,
                        RiskMetric.metric_name == metric_name,
                    )
                )
            )

            risk_metric = result.scalar_one_or_none()

            if risk_metric:
                # Update existing metric
                old_status = risk_metric.breach_status.value
                risk_metric.current_value = current_value
                risk_metric.limit_value = limit_value
                risk_metric.utilization_pct = utilization_pct
                risk_metric.breach_status = breach_status
                risk_metric.updated_at = datetime.now(timezone.utc)

                # Update last breach time if status changed to breached
                if old_status != "breached" and breach_status == "breached":
                    risk_metric.last_breach_at = datetime.now(timezone.utc)
            else:
                # Create new metric
                risk_metric = RiskMetric(
                    strategy_name=strategy_name,
                    metric_type=metric_type,
                    metric_name=metric_name,
                    current_value=current_value,
                    limit_value=limit_value,
                    utilization_pct=utilization_pct,
                    breach_status=breach_status,
                    last_breach_at=datetime.now(timezone.utc) if breach_status == "breached" else None,
                )
                self.session.add(risk_metric)

            await self.session.flush()
            await self.session.refresh(risk_metric)
            return risk_metric
        except Exception as e:
            logger.error(f"Failed to update risk metric: {e}")
            raise DatabaseError(f"Risk metric update failed: {e}")

    async def get_risk_metrics_by_strategy(self, strategy_name: str) -> List[RiskMetric]:
        """Get all risk metrics for a strategy."""
        try:
            result = await self.session.execute(select(RiskMetric).where(RiskMetric.strategy_name == strategy_name))
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get risk metrics for strategy {strategy_name}: {e}")
            raise DatabaseError(f"Risk metrics retrieval failed: {e}")

    async def get_breached_risk_metrics(self) -> List[RiskMetric]:
        """Get all breached risk metrics."""
        try:
            result = await self.session.execute(select(RiskMetric).where(RiskMetric.breach_status == "breached"))
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get breached risk metrics: {e}")
            raise DatabaseError(f"Breached risk metrics retrieval failed: {e}")


class InstrumentRepository(BaseRepository):
    """Repository for instrument operations."""

    async def create_or_update_instrument(self, instrument_data: Dict[str, Any]) -> InstrumentMaster:
        """Create or update instrument."""
        try:
            instrument_token = instrument_data["instrument_token"]

            # Try to find existing instrument
            result = await self.session.execute(
                select(InstrumentMaster).where(InstrumentMaster.instrument_token == instrument_token)
            )

            instrument = result.scalar_one_or_none()

            if instrument:
                # Update existing instrument
                for key, value in instrument_data.items():
                    setattr(instrument, key, value)
                instrument.updated_at = datetime.now(timezone.utc)
            else:
                # Create new instrument
                instrument = InstrumentMaster(**instrument_data)
                self.session.add(instrument)

            await self.session.flush()
            await self.session.refresh(instrument)
            return instrument
        except Exception as e:
            logger.error(f"Failed to create/update instrument: {e}")
            raise DatabaseError(f"Instrument operation failed: {e}")

    async def get_instrument_by_token(self, instrument_token: int) -> Optional[InstrumentMaster]:
        """Get instrument by token."""
        try:
            result = await self.session.execute(
                select(InstrumentMaster).where(InstrumentMaster.instrument_token == instrument_token)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get instrument {instrument_token}: {e}")
            raise DatabaseError(f"Instrument retrieval failed: {e}")

    async def get_instruments_by_exchange(self, exchange: str) -> List[InstrumentMaster]:
        """Get all instruments for an exchange."""
        try:
            result = await self.session.execute(select(InstrumentMaster).where(InstrumentMaster.exchange == exchange))
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get instruments for exchange {exchange}: {e}")
            raise DatabaseError(f"Instruments retrieval failed: {e}")

    async def search_instruments(self, query: str, limit: int = 50) -> List[InstrumentMaster]:
        """Search instruments by symbol or name."""
        try:
            result = await self.session.execute(
                select(InstrumentMaster)
                .where(
                    or_(InstrumentMaster.tradingsymbol.ilike(f"%{query}%"), InstrumentMaster.name.ilike(f"%{query}%"))
                )
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to search instruments: {e}")
            raise DatabaseError(f"Instrument search failed: {e}")
