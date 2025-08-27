from pydantic import BaseModel, Field
from typing import Dict, Optional, List
from datetime import datetime
from decimal import Decimal


class Position(BaseModel):
    """
    Represents a single position held in a portfolio.
    """
    instrument_token: int
    quantity: int = 0
    average_price: float = 0.0
    last_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    def calculate_unrealized_pnl(self):
        """Calculates the unrealized P&L based on the last known price."""
        if self.last_price is not None and self.quantity != 0:
            self.unrealized_pnl = (self.last_price - self.average_price) * self.quantity


class Portfolio(BaseModel):
    """
    Represents the complete state of a single trading portfolio (e.g., for one strategy).
    """
    portfolio_id: str  # e.g., "paper_momentum_test_1" or "live_overall"
    positions: Dict[int, Position] = Field(default_factory=dict)
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    cash: float = 1_000_000.0  # Starting cash
    realized_pnl: float = 0.0  # Alias for consistency
    last_modified: Optional[float] = None  # Timestamp of last modification

    def update_totals(self):
        """Recalculates the portfolio's total P&L."""
        self.total_unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        self.total_pnl = self.total_realized_pnl + self.total_unrealized_pnl
        # Keep realized_pnl in sync
        self.realized_pnl = self.total_realized_pnl
    
    def update_last_modified(self):
        """Update the last modified timestamp."""
        import time
        self.last_modified = time.time()


class PortfolioSummary(BaseModel):
    """Portfolio summary model for API responses"""
    total_value: Decimal
    cash_balance: Decimal
    positions: List[Position]
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    created_at: datetime
    updated_at: datetime