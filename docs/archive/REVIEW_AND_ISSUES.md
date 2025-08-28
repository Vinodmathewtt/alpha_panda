### Root Cause Analysis

The primary issue lies in how Kafka messages are being handled after consumption, specifically in the commit process. The error message `Failed to commit offset: 'ConsumerRecord' object has no attribute 'topic_partition'` indicates that the `commit` method in your `MessageConsumer` class is receiving an object it doesn't expect.

Here’s a step-by-step breakdown of what's happening:

1.  **Message Consumption**: In `core/streaming/infrastructure/message_consumer.py`, the `consume` method iterates over messages from the Kafka consumer and yields a dictionary containing the message details. However, the `_raw_message` key holds the original `ConsumerRecord` object from the `aiokafka` library, not a dictionary.
2.  **Processing Layer**: The `ReliabilityLayer` in `core/streaming/reliability/reliability_layer.py` receives this dictionary. When it processes a message successfully, it calls `self.consumer.commit(raw_message)`, passing the entire dictionary back.
3.  **Commit Failure**: The `commit` method in `MessageConsumer` expects a dictionary with a `_raw_message` key that contains a `topic_partition` attribute. However, it's receiving the `ConsumerRecord` object directly, which does not have this attribute, leading to the `AttributeError`.

### Code-Level Issues and Solutions

Here are the specific files that need to be updated to resolve the errors:

#### 1\. `core/streaming/infrastructure/message_consumer.py`

- **Issue**: The `commit` method is attempting to access `message['_raw_message'].topic_partition`, but `message['_raw_message']` is the `ConsumerRecord` object itself, which lacks a `topic_partition` attribute.
- **Solution**: You need to access the `topic` and `partition` from the `ConsumerRecord` object directly and create a `TopicPartition` object.

**Replace this:**

```python
await self._consumer.commit({
    message['_raw_message'].topic_partition: message['_raw_message'].offset + 1
})
```

**With this:**

```python
from aiokafka.structs import TopicPartition

# ... inside the commit method ...
tp = TopicPartition(message['_raw_message'].topic, message['_raw_message'].partition)
await self._consumer.commit({tp: message['_raw_message'].offset + 1})
```

#### 2\. `services/strategy_runner/service.py`

- **Issue**: In `_handle_market_tick`, the code fetches a `strategy_config` for each tick, which is inefficient and unnecessary since these configurations are loaded at startup.
- **Solution**: Remove the `await self._get_strategy_config(strategy_id)` call from the loop. You can access the strategy's broker configuration directly from the `runner.strategy` object.

**Replace this:**

```python
strategy_config = await self._get_strategy_config(strategy_id)
# ...
for broker in self.active_brokers:
    if self._should_process_strategy_for_broker(strategy_config, broker):
        # ...
```

**With this:**

```python
for broker in runner.strategy.brokers:
    if broker in self.active_brokers:
        for signal in signals:
            await self._emit_signal(signal, broker, strategy_id)
```

#### 3\. `services/trading_engine/service.py` & `services/risk_manager/service.py`

- **Issue**: Both services have a `_get_producer` method that can be simplified. The current implementation includes redundant checks.
- **Solution**: You can directly access the first producer since your `StreamServiceBuilder` is configured to add a single producer.

**Replace this:**

```python
if not self.orchestrator.producers:
    raise RuntimeError(f"No producers available for {self.__class__.__name__}")
if len(self.orchestrator.producers) == 0:
    raise RuntimeError(f"Producers list is empty for {self.__class__.__name__}")
return self.orchestrator.producers[0]
```

**With this:**

```python
if not self.orchestrator.producers:
    raise RuntimeError(f"No producers available for {self.__class__.__name__}")
return self.orchestrator.producers[0]
```

### Summary of Recommendations

The critical fix is in `message_consumer.py`. The other changes will improve the efficiency and robustness of your services. By implementing these fixes, you should see the `AttributeError` resolved and a more stable system.

I'm ready to help with any other questions you may have.

## Additional issues

I've conducted a more in-depth review of your codebase to identify other potential issues that are similar in nature to the `AttributeError` you were seeing. While the `topic_partition` bug was the most critical, I found a few other areas that could be improved for better robustness and consistency.

Here’s a summary of my findings:

### 1\. Inconsistent Dictionary Key Access

A recurring pattern in the codebase is the direct access of dictionary keys (e.g., `message['data']`) without handling the possibility of the key not being present. This can lead to `KeyError` exceptions if the message format changes or if an unexpected message type is received.

- **Files Affected**:

  - `services/risk_manager/service.py`
  - `services/trading_engine/service.py`
  - `services/strategy_runner/service.py`

- **Example from `RiskManagerService`**:

  ```python
  # In _handle_trading_signal
  signal_data = message.get("data", {}) # This is good

  # But later...
  key = f"{signal_data['strategy_id']}:{signal_data['instrument_token']}" # This is risky
  ```

- **Recommendation**:
  Use the `.get()` method with a default value to safely access dictionary keys. This will prevent `KeyError` exceptions and make your code more resilient to variations in message structure.

  **Corrected Example**:

  ```python
  strategy_id = signal_data.get("strategy_id", "")
  instrument_token = signal_data.get("instrument_token", "")
  key = f"{strategy_id}:{instrument_token}"
  ```

### 2\. Potential for `None` Values in `MessageConsumer`

In `core/streaming/infrastructure/message_consumer.py`, you have a potential issue where `message.key` could be `None`. While you handle this with a conditional, the `.decode()` method could still be called on a `None` value if the logic were ever changed.

- **File Affected**: `core/streaming/infrastructure/message_consumer.py`

- **Current Code**:

  ```python
  'key': message.key.decode('utf-8') if message.key else None,
  ```

- **Recommendation**:
  The current code is correct, but it's worth being mindful of this pattern. A slightly safer, though more verbose, approach would be:

  ```python
  'key': message.key.decode('utf-8') if message.key is not None else None,
  ```

  This doesn't change the functionality but makes the intent clearer and guards against an empty byte string being treated as `False`.

### 3\. Redundant Code in `_get_producer` Methods

As I mentioned in my previous review, the `_get_producer` method in your service classes is a bit redundant. While not a bug, it’s an area for code simplification.

- **Files Affected**:

  - `services/trading_engine/service.py`
  - `services/risk_manager/service.py`
  - `services/strategy_runner/service.py`

- **Recommendation**:
  Simplifying this method to a single check will make the code cleaner and easier to maintain.

  **Simplified Code**:

  ```python
  async def _get_producer(self):
      """Safely get producer with error handling"""
      if not self.orchestrator.producers:
          raise RuntimeError(f"No producers available for {self.__class__.__name__}")
      return self.orchestrator.producers[0]
  ```

### Summary of Additional Findings

The most significant of these additional findings is the **inconsistent dictionary key access**. Adopting a defensive approach with `.get()` will significantly improve the stability of your services. The other points are more about code quality and maintainability, but they are worth addressing to keep your codebase clean and robust.

By addressing these points, you'll be hardening your system against a class of errors that are very common in message-driven architectures. Let me know if you have any other questions\!
