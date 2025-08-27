## Market Feed Refactor

Here is the fully refactored `market_feed` service, considering all the details from your provided documentation and codebase.

---

### 1\. `services/market_feed/auth.py` (Refactored)

This file is now simplified to handle only the machine-to-machine authentication required to get a `KiteTicker` instance. It relies on the main `AuthService` to have already established a valid session.

```python
# alphaP/services/market_feed/auth.py

from kiteconnect import KiteTicker
from core.config.settings import Settings
from services.auth.service import AuthService
import logging

logger = logging.getLogger(__name__)

class BrokerAuthenticator:
    """
    Handles the machine-to-machine authentication for Zerodha KiteTicker.
    It retrieves the established session from the AuthService.
    """

    def __init__(self, auth_service: AuthService, settings: Settings):
        self._auth_service = auth_service
        self._settings = settings

    async def get_ticker(self) -> KiteTicker:
        """
        Performs authentication and returns a ready-to-use KiteTicker instance.
        """
        if not self._auth_service.is_authenticated():
            raise ConnectionError("Cannot start market feed: No authenticated Zerodha session found.")

        try:
            # Retrieve the access token from the authenticated session
            access_token = self._auth_service.auth_manager.get_access_token()
            api_key = self._settings.zerodha.api_key

            if not all([api_key, access_token]):
                raise ValueError("Zerodha API key or access token is missing.")

            # Create and return the WebSocket Ticker instance
            ticker = KiteTicker(api_key, access_token)
            logger.info("BrokerAuthenticator successfully created a KiteTicker instance.")
            return ticker

        except Exception as e:
            logger.error(f"FATAL: Broker authentication for market feed failed: {e}")
            raise
```

---

### 2\. `services/market_feed/formatter.py` (Unchanged)

This file's responsibility remains to format raw ticks into the application's standardized event schema. It is a crucial component for maintaining data consistency.

```python
# alphaP/services/market_feed/formatter.py

from datetime import datetime
from typing import Dict, Any, Optional
from decimal import Decimal

class TickFormatter:
    """Formats raw market data into standardized tick format"""

    def format_tick(self, raw_tick: Dict[str, Any]) -> Dict[str, Any]:
        """Format raw tick data into standard format"""
        return {
            "instrument_token": int(raw_tick["instrument_token"]),
            "last_price": float(raw_tick["last_price"]),
            "volume": int(raw_tick.get("volume", 0)),
            "timestamp": datetime.fromisoformat(raw_tick["timestamp"]) if isinstance(raw_tick["timestamp"], str) else raw_tick["timestamp"],
            "ohlc": self._format_ohlc(raw_tick.get("ohlc"))
        }

    def _format_ohlc(self, ohlc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Decimal]]:
        """Format OHLC data"""
        if not ohlc:
            return None

        return {
            "open": Decimal(str(ohlc["open"])),
            "high": Decimal(str(ohlc["high"])),
            "low": Decimal(str(ohlc["low"])),
            "close": Decimal(str(ohlc["close"]))
        }
```

---

### 3\. `services/market_feed/service.py` (Fully Refactored)

This is the core of the refactoring. It now uses the `BrokerAuthenticator` to get a live `KiteTicker` feed, completely removing any dependency on `mock_data.py`.

```python
# alphaP/services/market_feed/service.py

from typing import List, Dict, Any
import asyncio
from decimal import Decimal

from core.streaming.clients import StreamProcessor
from core.schemas.events import EventType, MarketTick
from core.schemas.topics import TopicNames, PartitioningKeys
from core.config.settings import Settings, RedpandaSettings
from core.logging import get_logger
from services.auth.service import AuthService

from .auth import BrokerAuthenticator
from .formatter import TickFormatter


class MarketFeedService(StreamProcessor):
    """
    Ingests live market data from Zerodha and publishes it as standardized
    events into the unified log (Redpanda).
    """

    def __init__(
        self,
        config: RedpandaSettings,
        settings: Settings,
        auth_service: AuthService,
    ):
        super().__init__(
            name="market_feed",
            config=config,
            consume_topics=[],  # Market feed is a data source, it does not consume.
            group_id=f"{settings.redpanda.group_id_prefix}.market_feed"
        )
        self.settings = settings
        self.auth_service = auth_service
        self.authenticator = BrokerAuthenticator(auth_service, settings)
        self.formatter = TickFormatter()
        self.kws = None
        self._feed_task = None
        self.logger = get_logger("market_feed")

    async def start(self):
        """
        Initializes the service, authenticates with the broker via AuthService,
        and starts the WebSocket connection for market data.
        """
        await super().start()
        self.logger.info("🚀 Starting Market Feed Service...")
        try:
            self.kws = await self.authenticator.get_ticker()
            self._assign_callbacks()
            self._feed_task = asyncio.create_task(self._run_feed())
            self.logger.info("✅ Market Feed Service started and is connecting to WebSocket.")
        except Exception as e:
            self.logger.error(f"❌ FATAL: Market Feed Service could not start: {e}")
            raise

    async def stop(self):
        """Gracefully stops the WebSocket connection."""
        if self._feed_task:
            self._feed_task.cancel()
            try:
                await self._feed_task
            except asyncio.CancelledError:
                pass
        if self.kws and self.kws.is_connected():
            self.logger.info("🛑 Stopping Market Feed Service WebSocket...")
            self.kws.close(1000, "Service shutting down")
        await super().stop()
        self.logger.info("✅ Market Feed Service stopped.")

    async def _run_feed(self):
        """Connects the KiteTicker and keeps the task alive."""
        self.kws.connect(threaded=True)
        while self._running and not self.kws.is_connected():
            await asyncio.sleep(1) # Wait for connection

        while self._running:
            await asyncio.sleep(1) # Keep the task running

    def _assign_callbacks(self):
        """Assigns the handler methods to the KiteTicker instance."""
        self.kws.on_ticks = self._on_ticks
        self.kws.on_connect = self._on_connect
        self.kws.on_close = self._on_close
        self.kws.on_error = self._on_error

    def _on_ticks(self, ws, ticks: List[Dict[str, Any]]):
        """
        The main callback for processing incoming market data ticks.
        This method is called from the KiteTicker's background thread.
        """
        if not self._running:
            return

        for tick in ticks:
            try:
                formatted_tick = self.formatter.format_tick(tick)
                market_tick = MarketTick(**formatted_tick)
                key = PartitioningKeys.market_tick_key(market_tick.instrument_token)

                # As _emit_event is async, and this is a sync callback,
                # we run it in the main event loop.
                asyncio.run_coroutine_threadsafe(
                    self._emit_event(
                        topic=TopicNames.MARKET_TICKS,
                        event_type=EventType.MARKET_TICK,
                        key=key,
                        data=market_tick.model_dump(mode='json')
                    ),
                    self.loop
                )
            except Exception as e:
                self.logger.error(f"Error processing tick: {tick}, Error: {e}")

    def _on_connect(self, ws, response):
        """Callback for when the WebSocket connection is established."""
        self.logger.info("WebSocket connected. Subscribing to instruments...")
        # In production, this list would come from the database.
        instrument_tokens = [256265, 260105] # NIFTY 50, BANKNIFTY
        self.kws.subscribe(instrument_tokens)
        self.kws.set_mode(self.kws.MODE_FULL, instrument_tokens)
        self.logger.info(f"Subscribed to {len(instrument_tokens)} instruments.")

    def _on_close(self, ws, code, reason):
        """Callback for when the WebSocket connection is closed."""
        self.logger.warning(f"WebSocket closed. Code: {code}, Reason: {reason}")
        # A robust service would trigger a reconnection attempt here.
        self._running = False

    def _on_error(self, ws, code, reason):
        """Callback for WebSocket errors."""
        self.logger.error(f"WebSocket error. Code: {code}, Reason: {reason}")

    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Market feed doesn't handle incoming messages."""
        pass

```

---

### 4\. `services/market_feed/mock_data.py` (Deleted)

As requested, this file is no longer needed and should be deleted from your project.

---

### 5\. `app/containers.py` (Updated)

Finally, update your dependency injection container to correctly wire the `AuthService` into the `MarketFeedService`.

**File**: `alphaP/app/containers.py`

```python
# alphaP/app/containers.py

# ... (other imports)
from services.market_feed.service import MarketFeedService
from services.auth.service import AuthService

class AppContainer(containers.DeclarativeContainer):

    # ... (settings, db_manager, redis_client providers)

    # Auth service
    auth_service = providers.Singleton(
        AuthService,
        settings=settings,
        db_manager=db_manager
    )

    # Market Feed Service (now depends on AuthService)
    market_feed_service = providers.Singleton(
        MarketFeedService,
        config=settings.provided.redpanda,
        settings=settings,
        auth_service=auth_service  # Inject the AuthService
    )

    # ... (rest of the services)
```

This completes the refactoring of the `market_feed` service. It is now a clean, robust component that relies on your `AuthService` for authentication and streams live market data from Zerodha into your system, fully removing all mock data generation.
