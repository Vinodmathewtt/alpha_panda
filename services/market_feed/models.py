# Market Feed Service Models
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal


class TickerSubscription(BaseModel):
    """Configuration for ticker subscription"""
    instrument_tokens: List[int]
    mode: str = "full"  # full, ltp, quote
    
    
class ConnectionStats(BaseModel):
    """WebSocket connection statistics"""
    connection_attempts: int = 0
    successful_connections: int = 0
    disconnections: int = 0
    last_connection_time: Optional[datetime] = None
    last_disconnection_time: Optional[datetime] = None
    current_status: str = "disconnected"  # connected, disconnected, reconnecting
    

class MarketDataMetrics(BaseModel):
    """Market data processing metrics"""
    ticks_processed: int = 0
    ticks_per_second: float = 0.0
    last_tick_time: Optional[datetime] = None
    error_count: int = 0
    instruments_subscribed: int = 0
    bytes_received: int = 0
    

class ReconnectionConfig(BaseModel):
    """Configuration for reconnection behavior"""
    max_attempts: int = 5
    base_delay: int = 1
    max_delay: int = 60
    backoff_multiplier: float = 2.0
    timeout: int = 30