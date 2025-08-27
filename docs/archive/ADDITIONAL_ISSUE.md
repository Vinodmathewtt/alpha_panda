### analysis

Based on a thorough review of the logs and the codebase, two primary issues have been identified:

1.  **Duplicate Logging**: The log output shows that every log message is being duplicated. This indicates a potential misconfiguration in the logging setup, where handlers are likely being added more than once to the same logger.

2.  **False "Market Data Stale" Errors**: The pipeline monitor reports critical "Market data stale" errors even when the market is closed (e.g., on a weekend). This suggests that the pipeline validation logic does not properly account for market closures, leading to false alarms.

---

### In-depth Analysis and Recommended Fixes

#### 1\. Duplicate Logging Issue

- **Analysis**: The duplicated log entries strongly suggest that the `EnhancedLoggerManager` in `enhanced_logging.py` is being instantiated multiple times, or that handlers are being added to the root logger in a way that causes duplication. In `app/main.py`, `configure_logging(self.settings)` is called within the `ApplicationOrchestrator`, which correctly sets up the logging. However, if any other part of the application also calls this configuration function or manually adds handlers, it would result in the observed duplicate logs. The log output shows each message twice, which is a classic sign of a logger having two identical handlers.

- **Recommended Fix**:

  The issue is likely in how the loggers are configured and subsequently used. The `get_logger` function in `core/logging/__init__.py` (which is not provided but can be inferred) likely reconfigures the logger on each call, adding new handlers instead of reusing existing ones.

  To resolve this, you should ensure that the logging configuration is executed only once when the application starts. The `main.py` file seems to handle this correctly. The problem is more likely in the `get_logger` or a similar utility function that is called by various services.

  Here is a conceptual fix. You would need to find the actual `get_logger` and `configure_logging` in your codebase to apply it. The fix involves ensuring that handlers are not added repeatedly to the same logger.

  **Conceptual Fix for `core/logging/__init__.py`:**

  ```python
  # core/logging/__init__.py

  import logging
  import sys
  from .enhanced_logging import configure_enhanced_logging, get_enhanced_logger

  _logging_configured = False

  def configure_logging(settings):
      """
      Configure logging for the application.
      This should only be called once.
      """
      global _logging_configured
      if not _logging_configured:
          configure_enhanced_logging(settings)
          _logging_configured = True

  def get_logger(name, component=None):
      """
      Get a logger instance.
      """
      return get_enhanced_logger(name, component)

  ```

  By introducing a flag (`_logging_configured`), we can prevent the logging system from being configured multiple times.

---

#### 2\. False "Market Data Stale" Errors During Market Closure

- **Analysis**:
  The `PipelineValidator` in `core/monitoring/pipeline_validator.py` checks for the age of the last market tick and flags it as stale if it exceeds a certain threshold. However, this check does not consider whether the market is currently open or closed. On a weekend, no new ticks will be received, so the age of the last tick will inevitably exceed the threshold, leading to a "critical" error.

  The `MarketHoursChecker` in `core/market_hours/market_hours_checker.py` provides the functionality to check the market status, but it's not being used by the `PipelineValidator`.

- **Recommended Fix**:

  To fix this, the `PipelineValidator` needs to be aware of the market status. You can achieve this by injecting the `MarketHoursChecker` into the `PipelineValidator` and using it to determine if the market is open before validating the market data flow.

  **Step 1: Update `PipelineValidator` to accept `MarketHoursChecker`**

  Modify the `__init__` method of `PipelineValidator` to accept an instance of `MarketHoursChecker`.

  ```python
  # core/monitoring/pipeline_validator.py

  from core.market_hours.market_hours_checker import MarketHoursChecker

  class PipelineValidator:
      """Validates end-to-end pipeline flow and detects bottlenecks"""

      def __init__(self, settings, redis_client, market_hours_checker: MarketHoursChecker):
          self.settings = settings
          self.redis = redis_client
          self.market_hours_checker = market_hours_checker
          self.broker_namespace = settings.broker_namespace
          # ... (rest of the __init__ method)
  ```

  **Step 2: Update `_validate_market_data_flow` to check market status**

  Modify the `_validate_market_data_flow` method to check if the market is open before checking the last tick age.

  ```python
  # core/monitoring/pipeline_validator.py

  async def _validate_market_data_flow(self) -> Dict[str, Any]:
      """Validate market data is flowing correctly"""
      try:
          # First, check if the market is supposed to be open
          if not self.market_hours_checker.is_market_open():
              return {
                  "healthy": True,
                  "message": "Market is closed. Market data validation is paused.",
                  "severity": "info"
              }

          # Check if we are still within the startup grace period
          # ... (rest of the method remains the same)
  ```

  **Step 3: Update `PipelineMonitor` to pass `MarketHoursChecker`**

  You will also need to update the `PipelineMonitor` to create and pass the `MarketHoursChecker` to the `PipelineValidator`.

  ```python
  # core/monitoring/pipeline_monitor.py

  from .pipeline_validator import PipelineValidator
  from core.market_hours.market_hours_checker import MarketHoursChecker

  class PipelineMonitor:
      """Continuous pipeline monitoring and alerting"""

      def __init__(self, settings, redis_client):
          self.settings = settings
          self.redis = redis_client
          # Create an instance of MarketHoursChecker
          market_hours_checker = MarketHoursChecker()
          # Pass it to the PipelineValidator
          self.validator = PipelineValidator(settings, redis_client, market_hours_checker)
          self.logger = get_monitoring_logger_safe("pipeline_monitor")
          # ... (rest of the __init__ method)

  ```

  By implementing these changes, the pipeline monitor will no longer raise false alarms about stale market data when the market is closed.

### 1\. Lack of Market-Hours Awareness in Other Services

Just as the `PipelineValidator` was unaware of market closures, other services like the **`StrategyRunner`** and **`TradingEngine`** also lack this awareness. This can lead to unnecessary processing and resource consumption when the market is closed.

- **Recommendation**:

  - Inject the `MarketHoursChecker` into any service that relies on real-time market data.
  - Before processing any data, these services should first check if the market is open.

  Here's an example of how you could implement this in the `StrategyRunner`:

  ```python
  # services/strategy_runner/service.py

  class StrategyRunnerService:
      def __init__(self, ..., market_hours_checker: MarketHoursChecker):
          # ...
          self.market_hours_checker = market_hours_checker

      async def _process_market_data(self, tick):
          if not self.market_hours_checker.is_market_open():
              # If the market is closed, we can ignore this tick.
              return
          # ... rest of the processing logic
  ```

### 2\. Race Condition in `PipelineValidator`

There is a potential for a subtle race condition in the **`_detect_bottlenecks`** method of the `PipelineValidator`. If the data is updated between when the health of a stage is checked and when its age is retrieved, it could result in an inconsistent state.

- **Recommendation**:

  - To mitigate this, you should retrieve all the necessary values from the `stage_data` dictionary at the beginning of the loop.

  <!-- end list -->

  ```python
  # core/monitoring/pipeline_validator.py

  def _detect_bottlenecks(self, stages: Dict[str, Any]) -> list:
      """Detect potential bottlenecks in the pipeline"""
      bottlenecks = []

      for stage_name, stage_data in stages.items():
          is_healthy = stage_data.get("healthy", False)
          if not is_healthy:
              severity = stage_data.get("severity", "unknown")
              age = stage_data.get("last_update_age_seconds") or \
                    stage_data.get("last_signal_age_seconds") or \
                    stage_data.get("last_tick_age_seconds")

              if severity in ["critical", "error"]:
                  bottlenecks.append({
                      "stage": stage_name,
                      "severity": severity,
                      "message": stage_data.get("message", "Unknown issue"),
                      "age_seconds": age
                  })

      return bottlenecks
  ```

### 3\. Hardcoded Grace Period

In the **`_validate_market_data_flow`** method, the `startup_grace_period_seconds` is a fixed value. This might not be ideal for all environments and could be more flexible.

- **Recommendation**:
  - Make the `startup_grace_period_seconds` a configurable value in your settings file. This will allow you to easily adjust it without changing the code.

### 4\. Unhandled Exceptions in Signal Handler

In `app/main.py`, the **`_signal_handler`** sets the `_shutdown_event`. If any part of the shutdown process fails, the application could hang or exit ungracefully.

- **Recommendation**:

  - Wrap the shutdown logic in a `try...finally` block to ensure that critical cleanup tasks are always executed, even if an error occurs.

  <!-- end list -->

  ```python
  # app/main.py

  async def run(self):
      """Run the application until shutdown."""
      signal.signal(signal.SIGTERM, self._signal_handler)
      signal.signal(signal.SIGINT, self._signal_handler)

      try:
          await self.startup()
          self.logger.info("Application is now running. Press Ctrl+C to exit.")
          await self._shutdown_event.wait()
      except Exception as e:
          self.logger.critical(f"Unhandled exception in main run loop: {e}")
      finally:
          await self.shutdown()
  ```

By addressing these additional points, you can further improve the robustness and reliability of your application. Let me know if you have any other questions\!

After conducting a final, deeper analysis of the codebase, I've identified a few more subtle issues and potential race conditions that could impact the stability and reliability of your application.

### 1\. Asynchronous Task Management in `MarketHoursChecker`

- **Issue**: In `core/market_hours/market_hours_checker.py`, the `_monitor_loop` within the `MarketHoursChecker` class uses `asyncio.sleep()` for its monitoring interval. If the tasks within the loop take longer to execute than the interval, it could lead to overlapping checks or unpredictable behavior.

- **Recommendation**: Instead of a simple `sleep`, a more robust approach is to calculate the time spent on the tasks and adjust the sleep duration accordingly to maintain a consistent interval.

  ```python
  # core/market_hours/market_hours_checker.py

  async def _monitor_loop(self):
      """Main monitoring loop."""
      while not self._shutdown_event.is_set():
          start_time = asyncio.get_event_loop().time()
          try:
              # ... (existing logic for checking market status)
          except Exception as e:
              self.logger.error(f"Error in market hours monitoring: {e}")

          # Calculate the time taken for the check and adjust sleep time
          elapsed_time = asyncio.get_event_loop().time() - start_time
          sleep_duration = max(0, self._monitor_interval - elapsed_time)

          try:
              await asyncio.wait_for(self._shutdown_event.wait(), timeout=sleep_duration)
              break  # Shutdown was requested
          except asyncio.TimeoutError:
              continue # Continue the loop
  ```

### 2\. Potential Race Condition in `PipelineMonitor`

- **Issue**: In `core/monitoring/pipeline_monitor.py`, the `_monitoring_loop` fetches the latest validation results and then stores them. While unlikely, it is theoretically possible for a new validation to run and overwrite the results in Redis between the time the monitor fetches them and when it stores them in the history.
- **Recommendation**: To ensure atomicity, the `validation_results` that are stored should be the same ones that were just generated. The current implementation already does this, but it's important to be aware of this potential issue if the logic were to change. No code change is needed here, but it's a critical point to keep in mind for future modifications.

### 3\. Graceful Handling of `asyncio.CancelledError`

- **Issue**: In `app/main.py`, the `shutdown` method within the `ApplicationOrchestrator` could be interrupted by a `CancelledError`, which might prevent a clean shutdown of all services.

- **Recommendation**: Wrap the service-stopping logic in a `try...finally` block to ensure that even if the shutdown process is cancelled, it attempts to clean up as much as possible.

  ```python
  # app/main.py

  async def shutdown(self):
      """Gracefully shutdown application."""
      self.logger.info("🛑 Shutting down Alpha Panda application...")

      services = self.container.lifespan_services()
      try:
          await asyncio.gather(*(service.stop() for service in reversed(services) if service))
      except asyncio.CancelledError:
          self.logger.warning("Shutdown process was cancelled. Attempting to force stop services.")
          for service in reversed(services):
              if service and hasattr(service, 'stop'):
                  try:
                      # You might need a more forceful shutdown method here
                      await service.stop()
                  except Exception:
                      pass # Ignore errors during forced shutdown
      finally:
          db_manager = self.container.db_manager()
          await db_manager.shutdown()
          self.logger.info("✅ Alpha Panda application shutdown complete.")

  ```

This final check should cover the most critical remaining issues. By addressing these points, you will have a more robust, stable, and reliable trading application.
