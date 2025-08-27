# Risk state management
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from core.config.settings import Settings
from core.utils.state_manager import CollectionStateManager, KeyValueStateManager


class RiskStateManager(CollectionStateManager):
    """Redis-backed risk state management for position tracking and rule evaluation"""
    
    def __init__(self, settings: Settings, redis_client=None):
        super().__init__("risk", settings, redis_client)
        
        # Also use a KV manager for simple counters and prices  
        self.kv_manager = KeyValueStateManager("risk", settings, redis_client)
    
    async def initialize(self, namespace: str = None):
        """Initialize both managers with the same namespace"""
        await super().initialize(namespace)
        await self.kv_manager.initialize(namespace)
        
    async def get_state(self) -> Dict[str, Any]:
        """Get current risk state for rule evaluation"""
        # Get all positions using collection manager
        positions = await self.get_collection("positions")
        
        # Get daily trades using KV manager pattern
        trade_pattern = f"{self.namespace}:risk:counter:daily_trades_*" if self.namespace else "risk:counter:daily_trades_*"
        trade_keys = await self._get_keys_by_pattern(trade_pattern)
        daily_trades = {}
        
        if trade_keys:
            trade_values = await self._get_multiple_values(trade_keys)
            for key, value in trade_values.items():
                if value is not None:
                    # Extract strategy_date part from key
                    key_parts = key.split(":")
                    if "daily_trades_" in key:
                        trade_key_part = key.split("daily_trades_")[1]
                        daily_trades[f"daily_trades_{trade_key_part}"] = int(value)
        
        # Get recent prices using KV manager pattern
        price_pattern = f"{self.namespace}:risk:value:recent_price_*" if self.namespace else "risk:value:recent_price_*"
        price_keys = await self._get_keys_by_pattern(price_pattern)
        recent_prices = {}
        
        if price_keys:
            price_values = await self._get_multiple_values(price_keys)
            for key, value in price_values.items():
                if value is not None:
                    # Extract instrument token from key
                    key_parts = key.split(":")
                    if "recent_price_" in key:
                        instrument_token = key.split("recent_price_")[1]
                        recent_prices[f"recent_price_{instrument_token}"] = float(value)
        
        return {
            "positions": positions,
            **daily_trades,
            **recent_prices
        }
    
    async def update_position(self, instrument_token: int, signal_type: str, quantity: int):
        """Update position tracking using collection manager"""
        current_position = await self.get_collection_item("positions", str(instrument_token))
        current_position = current_position or 0
        
        # Update position
        if signal_type == "BUY":
            new_position = current_position + quantity
        else:  # SELL
            new_position = current_position - quantity
            
        await self.set_collection_item("positions", str(instrument_token), new_position)
            
    async def increment_daily_trades(self, strategy_id: str, broker: str = None):
        """Increment daily trade counter using KV manager with optional broker context"""
        today = datetime.now().date()
        if broker:
            counter_key = f"daily_trades_{broker}_{strategy_id}_{today}"
        else:
            counter_key = f"daily_trades_{strategy_id}_{today}"
        
        # TTL = 2 days to allow for end-of-day processing
        await self.kv_manager.increment_counter(counter_key, ttl=86400 * 2)
        
    async def update_recent_price(self, instrument_token: int, price: float):
        """Update recent price using KV manager"""
        price_key = f"recent_price_{instrument_token}"
        # TTL = 1 hour for recent prices
        await self.kv_manager.set_value(price_key, price, ttl=3600)
        
    async def get_position(self, instrument_token: int) -> int:
        """Get current position for an instrument"""
        position = await self.get_collection_item("positions", str(instrument_token))
        return position or 0
        
    async def get_daily_trades(self, strategy_id: str) -> int:
        """Get daily trade count for a strategy"""
        today = datetime.now().date()
        counter_key = f"daily_trades_{strategy_id}_{today}"
        return await self.kv_manager.get_counter(counter_key)

    async def close(self):
        """Close Redis connections"""
        await super().close()
        await self.kv_manager.close()