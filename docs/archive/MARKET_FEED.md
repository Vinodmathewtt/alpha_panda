Excellent. With a dedicated `auth` service for user management, the `market_feed` service can now be simplified and focused on its core mission: **ingesting broker data reliably**.

The plan is to make the `market_feed` service a self-contained, robust component that handles only **broker authentication** and data publishing. It will be completely unaware of user sessions or API-level concerns. This clear separation of responsibilities makes the system much cleaner and more secure.

Here is the revised, complete code.

---

### \#\# 1. `services/market_feed/auth.py`

This file now exclusively handles the **machine-to-machine authentication** with the Zerodha Kite Connect API. It's responsible for securely fetching the broker's API keys and access tokens to establish a connection.

```python
# AlphasPT_v2/services/market_feed/auth.py

from kiteconnect import KiteConnect, KiteTicker
from core.config.settings import Settings
from core.database.connection import DatabaseManager # Used to fetch credentials

# Note: The one-time login flow to get the initial request_token is a separate,
# manual process. This authenticator assumes a valid access_token is stored.

class BrokerAuthenticator:
    """
    Handles the machine-to-machine authentication flow for Zerodha Kite Connect.
    """

    def __init__(self, db_manager: DatabaseManager, settings: Settings):
        self._db_manager = db_manager
        self._settings = settings
        self.kite_http_client = None

    async def _get_broker_credentials(self) -> dict:
        """
        Fetches Zerodha API credentials securely from the database.
        This is a placeholder for your actual credential retrieval logic.
        """
        # In a real system, you would query the database for the encrypted credentials.
        # For this example, we'll use the settings loaded from environment variables,
        # which is a common practice for containerized services.
        return {
            "api_key": self._settings.zerodha.api_key,
            "api_secret": self._settings.zerodha.api_secret,
            "access_token": self._settings.zerodha.access_token,
        }

    async def get_ticker(self) -> KiteTicker:
        """
        Performs the full authentication flow and returns a ready-to-use
        KiteTicker instance for the WebSocket connection.

        Raises:
            ValueError: If credentials are not found.
            Exception: If the session validation fails.
        """
        creds = await self._get_broker_credentials()
        if not all([creds.get("api_key"), creds.get("access_token")]):
            raise ValueError("Zerodha API key or access token is missing in configuration.")

        try:
            # 1. Initialize the HTTP client to verify the session
            self.kite_http_client = KiteConnect(api_key=creds["api_key"])
            self.kite_http_client.set_access_token(creds["access_token"])

            # 2. Make a test call to ensure the access token is valid
            profile = self.kite_http_client.profile()
            print(f"Broker session validated for user: {profile.get('user_id')}")

            # 3. If valid, create and return the WebSocket Ticker instance
            return KiteTicker(creds["api_key"], creds["access_token"])

        except Exception as e:
            print(f"FATAL: Broker authentication failed. Please check access token. Error: {e}")
            # This is a critical failure; the service cannot run without a valid session.
            raise

```

**Explanation:**

- **Clear Responsibility**: This class now has one job: authenticate with the broker. It's completely separate from user logins.
- **Secure Credential Handling**: It's designed to fetch credentials from a secure source (the database, as defined in the architecture). Using `settings` is a secure alternative in containerized environments where secrets are injected.
- **Session Validation**: The code now explicitly validates the session with a `profile()` call before creating the WebSocket client. This is a robust pattern that prevents the service from starting if the broker credentials have expired.

---

### \#\# 2. `services/market_feed/formatter.py`

This file remains unchanged but is still a crucial part of the design. It's a pure function that transforms the raw, broker-specific tick data into your application's standardized event format.

```python
# AlphasPT_v2/services/market_feed/formatter.py

from datetime import datetime

def format_tick_to_event(tick: dict) -> dict:
    """
    Transforms a raw tick from the KiteTicker library into a standardized
    event dictionary for the unified log.

    Args:
        tick: A single tick dictionary from the on_ticks callback.

    Returns:
        A standardized dictionary representing a market data event.
    """
    return {
        "event_type": "market_tick",
        "source": "zerodha_feed",
        "instrument_token": tick.get("instrument_token"),
        "timestamp": tick.get("exchange_timestamp") or datetime.now(),
        "last_price": tick.get("last_price"),
        "last_quantity": tick.get("last_quantity"),
        "average_price": tick.get("average_price"),
        "volume": tick.get("volume"),
        "buy_quantity": tick.get("buy_quantity"),
        "sell_quantity": tick.get("sell_quantity"),
        "ohlc": {
            "open": tick.get("ohlc", {}).get("open"),
            "high": tick.get("ohlc", {}).get("high"),
            "low": tick.get("ohlc", {}).get("low"),
            "close": tick.get("ohlc", {}).get("close"),
        },
    }
```

**Explanation:**

- **Data Consistency**: This function acts as a gateway, ensuring that all data entering your unified log is clean, consistent, and follows a predictable schema. This is vital for the reliability of all downstream services (strategies, analytics, etc.).

---

### \#\# 3. `services/market_feed/service.py`

This is the main service file. It's now cleaner, using the dedicated `BrokerAuthenticator` and focusing solely on managing the WebSocket lifecycle and publishing data.

```python
# AlphasPT_v2/services/market_feed/service.py

from typing import List

from app.services import LifespanService
from core.streaming.clients import RedpandaProducer
from core.database.connection import DatabaseManager
from core.config.settings import Settings

from .auth import BrokerAuthenticator
from .formatter import format_tick_to_event


class MarketFeedService(LifespanService):
    """
    The market feed service ingests live market data from a broker and
    publishes it as standardized events into the unified log (Redpanda).
    """

    def __init__(
        self,
        producer: RedpandaProducer,
        db_manager: DatabaseManager,
        settings: Settings,
    ):
        self.producer = producer
        self.settings = settings
        self.authenticator = BrokerAuthenticator(db_manager, settings)
        self.kws = None
        self._is_running = False

    async def start(self):
        """
        Initializes the service, authenticates with the broker, and starts
        the WebSocket connection for market data.
        """
        print("🚀 Starting Market Feed Service...")
        try:
            self.kws = await self.authenticator.get_ticker()
            self._assign_callbacks()

            # The WebSocket client runs in its own thread, so we call connect
            # and our main asyncio application loop continues without blocking.
            self.kws.connect(threaded=True)
            self._is_running = True
            print("✅ Market Feed Service started and is connecting to WebSocket.")

        except Exception as e:
            print(f"❌ FATAL: Market Feed Service could not start due to auth failure: {e}")
            # This is a critical failure. The app should not continue if the feed can't start.
            # A proper orchestrator would handle this and shut down gracefully.
            raise

    async def stop(self):
        """Gracefully stops the WebSocket connection."""
        if self._is_running and self.kws and self.kws.is_connected():
            print("🛑 Stopping Market Feed Service...")
            self.kws.close(1000, "Service shutting down")
        self._is_running = False
        print("✅ Market Feed Service stopped.")

    def _assign_callbacks(self):
        """Assigns the handler methods to the KiteTicker instance."""
        self.kws.on_ticks = self._on_ticks
        self.kws.on_connect = self._on_connect
        self.kws.on_close = self._on_close
        self.kws.on_error = self._on_error

    def _on_ticks(self, ws, ticks: List[dict]):
        """
        The main callback for processing incoming market data ticks.
        This method is called from the KiteTicker's background thread.
        """
        if not self._is_running:
            return

        for tick in ticks:
            try:
                # 1. Format the raw tick into our standard event format
                formatted_event = format_tick_to_event(tick)

                # 2. Produce the standardized event to the Redpanda log
                self.producer.produce("market.ticks", formatted_event)

            except Exception as e:
                print(f"Error processing tick: {tick}, Error: {e}")

    def _on_connect(self, ws, response):
        """Callback for when the WebSocket connection is established."""
        print("WebSocket connected. Subscribing to instruments...")
        # In a production system, this list would come from the database
        # or a configuration service.
        instrument_tokens = self.settings.market_feed.instrument_tokens
        self.kws.subscribe(instrument_tokens)
        self.kws.set_mode(self.kws.MODE_FULL, instrument_tokens)
        print(f"Subscribed to {len(instrument_tokens)} instruments.")

    def _on_close(self, ws, code, reason):
        """Callback for when the WebSocket connection is closed."""
        print(f"WebSocket closed. Code: {code}, Reason: {reason}")
        # A robust service would trigger a reconnection attempt here.
        self._is_running = False

    def _on_error(self, ws, code, reason):
        """Callback for WebSocket errors."""
        print(f"WebSocket error. Code: {code}, Reason: {reason}")
        # Log the error for monitoring and potential alerting.
```

**Explanation:**

- **Simplified `__init__`**: The service now receives a pre-configured `RedpandaProducer` and `DatabaseManager` from the DI container, making it cleaner and easier to test.
- **Robust Startup**: The `start` method is now more robust. It uses the dedicated `BrokerAuthenticator`, and if authentication fails, it raises a clear exception, preventing the service from running in a broken state.
- **Configuration-Driven Subscriptions**: The list of instruments to subscribe to is now driven by the central `Settings` object, making it easy to change which instruments you're tracking without touching the code.
