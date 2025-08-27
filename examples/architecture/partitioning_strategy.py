"""
Partitioning Strategy & Hot Key Management Example

Demonstrates how to prevent hot partitions while maintaining
ordering guarantees for trading events.
"""

from typing import Optional, Dict

class PartitioningStrategy:
    def __init__(self, total_partitions: int = 16):
        self.total_partitions = total_partitions
        
    def market_tick_key(self, instrument_token: str, strategy_id: Optional[str] = None) -> str:
        """Per-instrument partitioning with strategy sharding for hot symbols"""
        if strategy_id:
            # For hot symbols, shard by strategy to distribute load
            return f"tick|{instrument_token}|{strategy_id}"
        return f"tick|{instrument_token}"
        
    def signal_key(self, strategy_id: str, instrument_token: str) -> str:
        """Per-strategy+instrument for signal ordering"""
        return f"signal|{strategy_id}|{instrument_token}"
        
    def order_key(self, account_id: str, strategy_id: str) -> str:
        """Per-account+strategy for order execution ordering"""
        return f"order|{account_id}|{strategy_id}"
        
    def portfolio_key(self, account_id: str) -> str:
        """Per-account for portfolio state consistency"""
        return f"portfolio|{account_id}"

# Topic partition counts (tune based on throughput testing)
TOPIC_PARTITIONS = {
    "market.ticks": 32,        # High volume, distribute by instrument
    "signals.raw": 16,         # Medium volume, distribute by strategy
    "signals.validated": 16,   # Medium volume, distribute by strategy  
    "orders.submitted": 8,     # Lower volume, distribute by account
    "orders.filled": 8,        # Lower volume, distribute by account
    "pnl.snapshots": 4,        # Low volume, distribute by account
}