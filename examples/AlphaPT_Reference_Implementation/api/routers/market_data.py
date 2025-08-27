"""Market data API endpoints."""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from storage import storage_manager
from mock_market_feed import mock_feed_manager
from zerodha_market_feed import zerodha_market_feed_manager
from core.config.settings import settings
from core.logging.logger import get_logger
from ..middleware import get_current_user

logger = get_logger(__name__)

router = APIRouter()


class MarketTickResponse(BaseModel):
    instrument_token: int
    timestamp: datetime
    last_price: float
    last_traded_quantity: int
    volume_traded: int
    total_buy_quantity: int
    total_sell_quantity: int
    ohlc: Dict[str, float]


class InstrumentInfo(BaseModel):
    instrument_token: int
    tradingsymbol: str
    name: str
    exchange: str
    segment: str
    instrument_type: str
    tick_size: float
    lot_size: int


@router.get("/ticks", response_model=List[MarketTickResponse])
async def get_recent_ticks(
    instrument_token: Optional[int] = None,
    limit: int = Query(default=100, le=1000),
    user=Depends(get_current_user)
):
    """Get recent market ticks."""
    try:
        ticks = await storage_manager.get_recent_ticks(
            instrument_token=instrument_token,
            limit=limit
        )
        
        return [
            MarketTickResponse(
                instrument_token=tick["instrument_token"],
                timestamp=tick["timestamp"],
                last_price=tick["last_price"],
                last_traded_quantity=tick["last_traded_quantity"],
                volume_traded=tick["volume_traded"],
                total_buy_quantity=tick["total_buy_quantity"],
                total_sell_quantity=tick["total_sell_quantity"],
                ohlc={
                    "open": tick.get("open", 0.0),
                    "high": tick.get("high", 0.0),
                    "low": tick.get("low", 0.0),
                    "close": tick.get("close", 0.0)
                }
            )
            for tick in ticks
        ]
        
    except Exception as e:
        logger.error(f"Failed to get recent ticks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/instruments", response_model=List[InstrumentInfo])
async def get_instruments(
    exchange: Optional[str] = None,
    segment: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Get available instruments."""
    try:
        instruments = await storage_manager.get_instruments(
            exchange=exchange,
            segment=segment
        )
        
        return [
            InstrumentInfo(
                instrument_token=inst["instrument_token"],
                tradingsymbol=inst["tradingsymbol"],
                name=inst.get("name", ""),
                exchange=inst["exchange"],
                segment=inst["segment"],
                instrument_type=inst["instrument_type"],
                tick_size=inst["tick_size"],
                lot_size=inst["lot_size"]
            )
            for inst in instruments
        ]
        
    except Exception as e:
        logger.error(f"Failed to get instruments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quote/{instrument_token}")
async def get_quote(
    instrument_token: int,
    user=Depends(get_current_user)
):
    """Get current market quote for an instrument."""
    try:
        quote = await storage_manager.get_latest_quote(instrument_token)
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")
        
        return quote
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ohlc/{instrument_token}")
async def get_ohlc_data(
    instrument_token: int,
    interval: str = Query(default="1m", regex="^(1m|5m|15m|1h|1d)$"),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    user=Depends(get_current_user)
):
    """Get OHLC data for an instrument."""
    try:
        # Set default date range if not provided
        if not to_date:
            to_date = datetime.now()
        if not from_date:
            from_date = to_date - timedelta(days=1)
        
        ohlc_data = await storage_manager.get_ohlc_data(
            instrument_token=instrument_token,
            interval=interval,
            from_date=from_date,
            to_date=to_date
        )
        
        return ohlc_data
        
    except Exception as e:
        logger.error(f"Failed to get OHLC data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feed/status")
async def get_feed_status(user=Depends(get_current_user)):
    """Get market feed status."""
    try:
        if settings.mock_market_feed:
            feed_manager = mock_feed_manager
        else:
            feed_manager = zerodha_market_feed_manager
        
        status = feed_manager.get_statistics()
        
        return {
            "feed_type": "mock" if settings.mock_market_feed else "zerodha",
            "status": status,
            "is_streaming": getattr(feed_manager, 'streaming', False),
            "connection_status": status.get("connection_status", "unknown")
        }
        
    except Exception as e:
        logger.error(f"Failed to get feed status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feed/subscribe")
async def subscribe_instruments(
    instrument_tokens: List[int],
    user=Depends(get_current_user)
):
    """Subscribe to instruments for real-time data."""
    try:
        if settings.mock_market_feed:
            feed_manager = mock_feed_manager
        else:
            feed_manager = zerodha_market_feed_manager
        
        success = await feed_manager.subscribe_instruments(instrument_tokens)
        
        return {
            "success": success,
            "subscribed_tokens": instrument_tokens,
            "message": f"Subscribed to {len(instrument_tokens)} instruments"
        }
        
    except Exception as e:
        logger.error(f"Failed to subscribe to instruments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feed/unsubscribe")
async def unsubscribe_instruments(
    instrument_tokens: List[int],
    user=Depends(get_current_user)
):
    """Unsubscribe from instruments."""
    try:
        if settings.mock_market_feed:
            feed_manager = mock_feed_manager
        else:
            feed_manager = zerodha_market_feed_manager
        
        success = await feed_manager.unsubscribe_instruments(instrument_tokens)
        
        return {
            "success": success,
            "unsubscribed_tokens": instrument_tokens,
            "message": f"Unsubscribed from {len(instrument_tokens)} instruments"
        }
        
    except Exception as e:
        logger.error(f"Failed to unsubscribe from instruments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/depth/{instrument_token}")
async def get_market_depth(
    instrument_token: int,
    user=Depends(get_current_user)
):
    """Get market depth (order book) for an instrument."""
    try:
        depth = await storage_manager.get_market_depth(instrument_token)
        if not depth:
            raise HTTPException(status_code=404, detail="Market depth not found")
        
        return depth
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get market depth: {e}")
        raise HTTPException(status_code=500, detail=str(e))