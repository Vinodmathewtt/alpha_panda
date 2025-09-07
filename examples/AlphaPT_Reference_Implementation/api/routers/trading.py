"""Trading operations API endpoints.

Note: This example predates the standardized field name `execution_mode`.
Where it refers to a `trading_mode` concept, prefer `execution_mode`
(`paper` or `zerodha`) in new code and schemas.
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from paper_trade import paper_trading_engine
from zerodha_trade import zerodha_trading_engine  
from risk_manager import risk_manager
from core.config.settings import settings
from core.logging.logger import get_logger
from core.utils.sanitization import InputSanitizer, validate_required_fields
from ..middleware import get_current_user, require_trading_permission

logger = get_logger(__name__)

router = APIRouter()


class OrderRequest(BaseModel):
    strategy_name: str
    tradingsymbol: str
    exchange: str = "NSE"
    transaction_type: str = Field(..., pattern="^(BUY|SELL)$")
    order_type: str = Field("MARKET", pattern="^(MARKET|LIMIT|STOP_LOSS|STOP_LOSS_MARKET)$")
    quantity: int = Field(..., gt=0)
    price: Optional[Decimal] = None
    trigger_price: Optional[Decimal] = None
    product: str = Field("MIS", pattern="^(CNC|MIS|NRML)$")
    validity: str = Field("DAY", pattern="^(DAY|IOC)$")
    disclosed_quantity: Optional[int] = None
    tag: Optional[str] = None


class OrderResponse(BaseModel):
    order_id: str
    status: str
    message: str
    timestamp: datetime


class PositionResponse(BaseModel):
    strategy_name: str
    tradingsymbol: str
    exchange: str
    quantity: int
    average_price: Decimal
    current_price: Decimal
    pnl: Decimal
    unrealised_pnl: Decimal
    realised_pnl: Decimal


class PortfolioSummary(BaseModel):
    strategy_name: str
    total_pnl: Decimal
    realised_pnl: Decimal
    unrealised_pnl: Decimal
    total_value: Decimal
    positions_count: int
    open_orders_count: int


@router.post("/orders", response_model=OrderResponse)
async def place_order(
    order: OrderRequest,
    trading_mode: str = "paper",
    user=Depends(get_current_user),
    _=Depends(require_trading_permission)
):
    """Place a new trading order."""
    try:
        # Basic input sanitization
        sanitized_strategy = InputSanitizer.sanitize_strategy_name(order.strategy_name)
        sanitized_symbol = InputSanitizer.sanitize_trading_symbol(order.tradingsymbol)
        sanitized_quantity = InputSanitizer.sanitize_positive_number(
            order.quantity, "quantity", min_val=1, max_val=10000
        )
        
        # Validate trading mode
        if trading_mode not in ["paper", "zerodha"]:
            raise HTTPException(status_code=400, detail="Invalid trading mode")
        
        # Select trading engine based on mode
        if trading_mode == "paper":
            engine = paper_trading_engine
        elif trading_mode == "zerodha":
            engine = zerodha_trading_engine
        
        # Sanitize optional price fields
        sanitized_price = None
        if order.price is not None:
            sanitized_price = InputSanitizer.sanitize_positive_number(
                order.price, "price", min_val=0.01, max_val=1000000
            )
        
        sanitized_trigger_price = None
        if order.trigger_price is not None:
            sanitized_trigger_price = InputSanitizer.sanitize_positive_number(
                order.trigger_price, "trigger_price", min_val=0.01, max_val=1000000
            )
        
        # Place order with sanitized inputs
        result = await engine.place_order(
            strategy_name=sanitized_strategy,
            tradingsymbol=sanitized_symbol,
            exchange=order.exchange,
            transaction_type=order.transaction_type,
            order_type=order.order_type,
            quantity=int(sanitized_quantity),
            price=sanitized_price,
            trigger_price=sanitized_trigger_price,
            product=order.product,
            validity=order.validity,
            disclosed_quantity=order.disclosed_quantity,
            tag=order.tag
        )
        
        return OrderResponse(
            order_id=result["order_id"],
            status=result["status"],
            message=result.get("message", "Order placed successfully"),
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Failed to place order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_id}")
async def get_order_status(
    order_id: str,
    trading_mode: str = "paper",
    user=Depends(get_current_user)
):
    """Get order status and details."""
    try:
        # Select trading engine
        if trading_mode == "paper":
            engine = paper_trading_engine
        elif trading_mode == "zerodha":
            engine = zerodha_trading_engine
        else:
            raise HTTPException(status_code=400, detail="Invalid trading mode")
        
        order_details = await engine.get_order_status(order_id)
        if not order_details:
            raise HTTPException(status_code=404, detail="Order not found")
        
        return order_details
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/orders/{order_id}")
async def cancel_order(
    order_id: str,
    trading_mode: str = "paper",
    user=Depends(get_current_user),
    _=Depends(require_trading_permission)
):
    """Cancel an existing order."""
    try:
        # Select trading engine
        if trading_mode == "paper":
            engine = paper_trading_engine
        elif trading_mode == "zerodha":
            engine = zerodha_trading_engine
        else:
            raise HTTPException(status_code=400, detail="Invalid trading mode")
        
        result = await engine.cancel_order(order_id)
        return {
            "order_id": order_id,
            "status": "cancelled",
            "message": "Order cancelled successfully",
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"Failed to cancel order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(
    strategy_name: Optional[str] = None,
    trading_mode: str = "paper",
    user=Depends(get_current_user)
):
    """Get current positions."""
    try:
        # Select trading engine
        if trading_mode == "paper":
            engine = paper_trading_engine
        elif trading_mode == "zerodha":
            engine = zerodha_trading_engine
        else:
            raise HTTPException(status_code=400, detail="Invalid trading mode")
        
        positions = await engine.get_positions(strategy_name)
        
        return [
            PositionResponse(
                strategy_name=pos["strategy_name"],
                tradingsymbol=pos["tradingsymbol"],
                exchange=pos["exchange"],
                quantity=pos["quantity"],
                average_price=pos["average_price"],
                current_price=pos.get("current_price", pos["average_price"]),
                pnl=pos.get("pnl", Decimal("0")),
                unrealised_pnl=pos.get("unrealised_pnl", Decimal("0")),
                realised_pnl=pos.get("realised_pnl", Decimal("0"))
            )
            for pos in positions
        ]
        
    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio", response_model=PortfolioSummary)
async def get_portfolio_summary(
    strategy_name: str,
    trading_mode: str = "paper",
    user=Depends(get_current_user)
):
    """Get portfolio summary for a strategy."""
    try:
        # Select trading engine
        if trading_mode == "paper":
            engine = paper_trading_engine
        elif trading_mode == "zerodha":
            engine = zerodha_trading_engine
        else:
            raise HTTPException(status_code=400, detail="Invalid trading mode")
        
        summary = await engine.get_portfolio_summary(strategy_name)
        
        return PortfolioSummary(
            strategy_name=strategy_name,
            total_pnl=summary.get("total_pnl", Decimal("0")),
            realised_pnl=summary.get("realised_pnl", Decimal("0")),
            unrealised_pnl=summary.get("unrealised_pnl", Decimal("0")),
            total_value=summary.get("total_value", Decimal("0")),
            positions_count=summary.get("positions_count", 0),
            open_orders_count=summary.get("open_orders_count", 0)
        )
        
    except Exception as e:
        logger.error(f"Failed to get portfolio summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account")
async def get_account_info(
    trading_mode: str = "paper",
    user=Depends(get_current_user)
):
    """Get account information and margin details."""
    try:
        # Select trading engine
        if trading_mode == "paper":
            engine = paper_trading_engine
        elif trading_mode == "zerodha":
            engine = zerodha_trading_engine
        else:
            raise HTTPException(status_code=400, detail="Invalid trading mode")
        
        account_info = await engine.get_account_info()
        return account_info
        
    except Exception as e:
        logger.error(f"Failed to get account info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/margin/check")
async def check_margin_requirement(
    order: OrderRequest,
    trading_mode: str = "paper",
    user=Depends(get_current_user)
):
    """Check margin requirement for an order."""
    try:
        # Select trading engine
        if trading_mode == "paper":
            engine = paper_trading_engine
        elif trading_mode == "zerodha":
            engine = zerodha_trading_engine
        else:
            raise HTTPException(status_code=400, detail="Invalid trading mode")
        
        margin_info = await engine.check_margin_requirement(
            tradingsymbol=order.tradingsymbol,
            exchange=order.exchange,
            transaction_type=order.transaction_type,
            quantity=order.quantity,
            price=order.price or Decimal("0"),
            order_type=order.order_type,
            product=order.product
        )
        
        return margin_info
        
    except Exception as e:
        logger.error(f"Failed to check margin requirement: {e}")
        raise HTTPException(status_code=500, detail=str(e))
