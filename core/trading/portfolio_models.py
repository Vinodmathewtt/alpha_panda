from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Dict, Optional
from datetime import datetime


class Position(BaseModel):
    instrument_token: int
    quantity: int
    avg_price: float
    last_price: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    def calculate_unrealized_pnl(self):
        self.unrealized_pnl = (self.last_price - self.avg_price) * self.quantity


class Portfolio(BaseModel):
    portfolio_id: str
    positions: Dict[int, Position] = Field(default_factory=dict)
    total_pnl: float = 0.0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    last_modified: Optional[datetime] = None

    def update_totals(self):
        self.total_realized_pnl = sum(p.realized_pnl for p in self.positions.values())
        self.total_unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        self.total_pnl = self.total_realized_pnl + self.total_unrealized_pnl

    def update_last_modified(self):
        self.last_modified = datetime.utcnow()


class PortfolioSummary(BaseModel):
    total_positions: int
    total_pnl: float
    total_realized_pnl: float
    total_unrealized_pnl: float

