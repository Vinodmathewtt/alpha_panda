"""
Async Broker SDK Integration Example

Demonstrates how to wrap synchronous broker APIs in async context
using ThreadPoolExecutor for non-blocking operations.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

class AsyncBrokerAdapter:
    def __init__(self, sync_broker_client):
        self.sync_client = sync_broker_client
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="broker_")
        
    async def place_order_async(self, order_params: dict) -> dict:
        """Wrap sync broker API in async context"""
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self.executor, 
                self.sync_client.place_order,
                order_params
            )
            return result
        except Exception as e:
            self.logger.error("Broker API call failed", error=str(e))
            raise
            
    async def get_ticker_async(self) -> Any:
        """Async wrapper for sync ticker"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.sync_client.get_ticker)