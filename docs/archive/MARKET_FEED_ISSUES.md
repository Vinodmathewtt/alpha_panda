# Market Feed Issues

### **2. Critical Flaw: Broker Field Derivation**

This is the most significant issue in the `market_feed` service. The `StreamProcessor._emit_event` method derives the `broker` from the topic name. For a topic like `"paper.orders"`, this works fine, as it correctly extracts `"paper"`. However, for `"market.ticks"`, it incorrectly sets the broker to `"market"`.

This breaks the data contract for any downstream service that consumes these ticks. For example, a strategy running in a `"paper"` or `"zerodha"` context won't be able to correctly attribute the market data to its own broker namespace.

**Recommendation:**

The `MarketFeedService` should explicitly set the `broker` when emitting events. The `broker_namespace` from the settings is the perfect candidate for this.

Here's how you can modify the `_on_ticks` method in `services/market_feed/service.py`:

```python
# services/market_feed/service.py

    def _on_ticks(self, ws, ticks: List[Dict[str, Any]]):
        """
        The main callback for processing incoming market data ticks.
        This method is called from the KiteTicker's background thread.
        Captures COMPLETE PyKiteConnect data including market depth.
        """
        if not self._running:
            return

        for tick in ticks:
            try:
                # ... (rest of the tick processing)

                # As _emit_event is async, and this is a sync callback,
                # we run it in the main event loop.
                emit_coro = self._emit_event(
                    topic=TopicNames.MARKET_TICKS,
                    event_type=EventType.MARKET_TICK,
                    key=key,
                    data=market_tick.model_dump(mode='json'),
                    # Explicitly set the broker
                    broker=self.settings.broker_namespace
                )

                # ... (rest of the method)
```

### **3. Graceful Shutdown and Resource Management**

The `stop` method in `market_feed/service.py` is well-implemented. It correctly cancels the `_feed_task` and closes the WebSocket connection. This is crucial for preventing resource leaks and ensuring a clean shutdown of the service.

However, the `_on_close` method logs a warning but doesn't attempt to reconnect. In a production environment, you would want a more robust reconnection strategy with exponential backoff.

**Recommendation:**

Implement a reconnection mechanism in the `_on_close` callback.

```python
# services/market_feed/service.py

    def _on_close(self, ws, code, reason):
        """Callback for when the WebSocket connection is closed."""
        self.logger.warning(f"WebSocket closed. Code: {code}, Reason: {reason}")
        if self._running:
            self.logger.info("Attempting to reconnect...")
            # Implement reconnection logic here
```

### **4. Hardcoded Fallbacks**

The service has hardcoded fallback instrument tokens in both `_load_instruments_from_csv` and `_on_connect`. While this is acceptable for development, it's not ideal for a production system.

**Recommendation:**

Make the instrument list a mandatory configuration. If the CSV file is not found or is empty, the service should fail to start. This "fail-fast" approach is generally safer than running with potentially incorrect or incomplete data.

### **5. Integration with `InstrumentRegistryService`**

The `MarketFeedService` correctly uses the `InstrumentRegistryService` to load instruments into the database. This is a good example of service-to-service communication and ensures that the rest of the application has access to the same instrument data.

### **Summary**

The `market_feed` service is a solid foundation for your market data pipeline. It correctly handles WebSocket communication, data formatting, and publishing to Redpanda. However, the incorrect broker derivation is a critical flaw that needs to be addressed immediately. By implementing the recommendations above, you can make the service more robust, reliable, and production-ready.
