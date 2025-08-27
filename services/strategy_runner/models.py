# Strategy Runner Service Models
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


class StrategyState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class StrategyMetrics(BaseModel):
    """Runtime metrics for a strategy"""
    strategy_id: str
    ticks_processed: int = 0
    signals_generated: int = 0
    errors_count: int = 0
    last_execution_time: Optional[datetime] = None
    average_execution_time_ms: float = 0.0
    success_rate: float = 100.0
    

class StrategyInstance(BaseModel):
    """Runtime representation of a strategy"""
    strategy_id: str
    strategy_type: str
    state: StrategyState = StrategyState.ACTIVE
    instruments: List[int]
    parameters: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    

class StrategyError(BaseModel):
    """Strategy execution error record"""
    strategy_id: str
    error_type: str
    error_message: str
    instrument_token: Optional[int] = None
    tick_data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = False
    

class ExecutionResult(BaseModel):
    """Result of strategy execution"""
    strategy_id: str
    success: bool
    execution_time_ms: float
    signals_generated: int = 0
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)