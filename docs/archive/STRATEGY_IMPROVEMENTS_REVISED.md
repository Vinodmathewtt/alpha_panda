# Strategy Scaling Improvements - REVISED (50–100 ML Strategies)

**REVISION DATE**: 2025-01-13  
**STATUS**: Architecture-Aligned Implementation Plan  
**TARGET**: Support 50–100 concurrent ML strategies with <50ms P99 latency

This document provides a **revised and aligned** implementation plan for scaling Alpha Panda's strategy framework to support 50–100 machine learning strategies concurrently. This revision addresses critical architectural misalignments identified in the original plan and aligns with the **composition-only architecture** currently implemented.

---

## 🎯 Goals & Success Metrics

- **Throughput**: Sustain shared `market.ticks` processing for 50–100 concurrent strategies
- **Latency**: P99 signal emission latency <50ms (configurable: 50-150ms) from tick arrival to signal publish
- **Stability**: Strategy failures isolated with graceful degradation, no cascading failures
- **Memory Efficiency**: Eliminate redundant computation/memory duplication across strategies
- **Observability**: Rich per-strategy metrics, model lifecycle controls, safe hot reloads

---

## ✅ Current Architecture Assessment

### Strengths Already Implemented
- **✅ Composition-Only Architecture**: Modern `StrategyExecutor` + `StrategyProcessor` protocol pattern
- **✅ O(1) Tick Routing**: `instrument_to_strategies` mapping already implemented  
- **✅ Multi-Broker Emission**: Single strategy generates signals for all configured brokers
- **✅ StreamServiceBuilder Pattern**: Modern service composition with error handling/metrics
- **✅ Protocol-Based Contracts**: `StrategyProcessor`, `StrategyValidator` protocols implemented

### Current Performance Characteristics
```python
# CURRENT IMPLEMENTATION (efficient foundation)
class StrategyRunnerService:
    def __init__(self):
        # O(1) instrument-to-strategy mapping (ALREADY IMPLEMENTED)
        self.instrument_to_strategies: Dict[int, List[str]] = defaultdict(list)
    
    async def _handle_market_tick(self, message: Dict[str, Any], topic: str):
        # Efficient tick routing (ALREADY OPTIMIZED)  
        interested_strategy_ids = self.instrument_to_strategies.get(instrument_token, [])
        
        for strategy_id in interested_strategy_ids:
            # Process using composition architecture
            signal_result = executor.process_tick(market_tick)
            
            # Multi-broker signal emission per strategy
            for broker in executor.config.active_brokers:
                await self._emit_signal(trading_signal, broker)
```

---

## 🚀 Implementation Plan - Revised

### Phase 1: Shared Resource Infrastructure (1-2 weeks)

#### 1.1 Instrument History Store
**Rationale**: 50-100 strategies × N instruments creates memory explosion; most strategies need same historical windows.

```python
# NEW: services/strategy_runner/components/instrument_history_store.py
from collections import deque
from typing import Dict, List, Optional
from core.schemas.events import MarketTick

class InstrumentHistoryStore:
    """Shared per-instrument ring buffers to eliminate memory duplication"""
    
    def __init__(self, max_history_per_instrument: int = 1000):
        self._histories: Dict[int, deque[MarketTick]] = {}
        self._max_history = max_history_per_instrument
        self._lock = asyncio.Lock()
    
    async def update_tick(self, tick: MarketTick) -> None:
        """Update shared history for instrument"""
        async with self._lock:
            if tick.instrument_token not in self._histories:
                self._histories[tick.instrument_token] = deque(maxlen=self._max_history)
            self._histories[tick.instrument_token].append(tick)
    
    def get_history_slice(self, instrument_token: int, length: int) -> List[MarketTick]:
        """Get lightweight view of recent history - O(1) access"""
        history = self._histories.get(instrument_token, deque())
        return list(history)[-length:] if len(history) >= length else list(history)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Return utilization metrics"""
        return {
            "instruments_tracked": len(self._histories),
            "total_ticks_stored": sum(len(h) for h in self._histories.values()),
            "memory_utilization": sum(len(h) / self._max_history for h in self._histories.values())
        }
```

#### 1.2 Feature Store with Caching
**Rationale**: Many ML strategies reuse common features (SMA, RSI, returns).

```python
# NEW: services/strategy_runner/components/feature_store.py
import hashlib
from typing import Dict, Any, Optional, Callable
from decimal import Decimal
import numpy as np

class FeatureStore:
    """Time-bucketed feature cache for common ML features"""
    
    def __init__(self, redis_client, cache_ttl_seconds: int = 300):
        self.redis = redis_client
        self.cache_ttl = cache_ttl_seconds
        self._feature_calculators = {
            "sma": self._calculate_sma,
            "ema": self._calculate_ema, 
            "rsi": self._calculate_rsi,
            "returns": self._calculate_returns,
            "volatility": self._calculate_volatility
        }
    
    async def get_feature(self, instrument_token: int, feature_name: str, 
                         window: int, history: List[MarketTick], 
                         params: Dict[str, Any] = None) -> Optional[float]:
        """Get cached feature or compute and cache"""
        cache_key = self._generate_cache_key(instrument_token, feature_name, window, params)
        
        # Try cache first
        cached = await self.redis.get(cache_key)
        if cached:
            return float(cached.decode())
        
        # Compute feature
        if feature_name in self._feature_calculators:
            value = self._feature_calculators[feature_name](history, window, params or {})
            if value is not None:
                await self.redis.setex(cache_key, self.cache_ttl, str(value))
            return value
        
        return None
    
    def _generate_cache_key(self, instrument_token: int, feature_name: str, 
                           window: int, params: Dict[str, Any]) -> str:
        """Generate deterministic cache key"""
        params_str = str(sorted(params.items())) if params else ""
        key_data = f"feature:{instrument_token}:{feature_name}:{window}:{params_str}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _calculate_sma(self, history: List[MarketTick], window: int, params: Dict) -> Optional[float]:
        """Simple Moving Average - vectorized"""
        if len(history) < window:
            return None
        prices = np.array([float(tick.last_price) for tick in history[-window:]])
        return float(np.mean(prices))
        
    def _calculate_rsi(self, history: List[MarketTick], window: int, params: Dict) -> Optional[float]:
        """RSI calculation - vectorized"""
        if len(history) < window + 1:
            return None
        prices = np.array([float(tick.last_price) for tick in history[-(window+1):]])
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - (100 / (1 + rs)))
```

#### 1.3 Updated Strategy Protocols for ML
**Alignment**: Extend current `StrategyProcessor` protocol for ML workflows.

```python  
# UPDATED: strategies/core/protocols.py (extend existing)
from typing import Protocol, Dict, List, Any, Optional
import numpy as np
from core.schemas.events import MarketTick

# EXTEND EXISTING StrategyProcessor protocol
class MLStrategyProcessor(StrategyProcessor):
    """Extended protocol for ML-based strategies"""
    
    def extract_features(self, tick: MarketTick, history: List[MarketTick], 
                        shared_features: Dict[str, Any]) -> Dict[str, Any]:
        """Extract features for ML inference"""
        ...
    
    def predict(self, features: Dict[str, Any]) -> Optional[SignalResult]:
        """Run ML inference on extracted features"""
        ...
        
    def supports_batch_prediction(self) -> bool:
        """Whether strategy supports batch prediction"""
        ...
        
    def get_model_info(self) -> Dict[str, Any]:
        """Return model metadata for monitoring"""
        ...

class BatchPredictor(Protocol):
    """Protocol for batch ML inference"""
    
    def predict_batch(self, feature_batch: List[Dict[str, Any]]) -> List[Optional[SignalResult]]:
        """Batch prediction interface"""
        ...
```

### Phase 2: ML Infrastructure & Micro-Batching (2-3 weeks)

#### 2.1 Micro-Batching Scheduler
**Rationale**: Amortize Python overhead, leverage vectorized ML libraries.

```python
# NEW: services/strategy_runner/components/batch_scheduler.py
import asyncio
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class InferenceBatch:
    strategy_ids: List[str]
    features: List[Dict[str, Any]]  
    callbacks: List[Callable[[Optional[SignalResult]], None]]
    created_at: float

class MicroBatchScheduler:
    """Collect predictions into micro-batches for ML efficiency"""
    
    def __init__(self, batch_window_ms: int = 20, max_batch_size: int = 32):
        self.batch_window = batch_window_ms / 1000.0
        self.max_batch_size = max_batch_size
        self._pending_batches: Dict[str, InferenceBatch] = {}
        self._batch_timers: Dict[str, asyncio.Handle] = {}
        
    async def schedule_prediction(self, model_signature: str, strategy_id: str,
                                features: Dict[str, Any], predictor: BatchPredictor,
                                callback: Callable[[Optional[SignalResult]], None]):
        """Schedule prediction with micro-batching"""
        
        # Add to batch
        if model_signature not in self._pending_batches:
            self._pending_batches[model_signature] = InferenceBatch([], [], [], time.time())
            
        batch = self._pending_batches[model_signature]
        batch.strategy_ids.append(strategy_id)
        batch.features.append(features)
        batch.callbacks.append(callback)
        
        # Execute immediately if batch full
        if len(batch.features) >= self.max_batch_size:
            await self._execute_batch(model_signature, predictor)
            return
        
        # Schedule timer if first item in batch
        if len(batch.features) == 1:
            self._batch_timers[model_signature] = asyncio.get_event_loop().call_later(
                self.batch_window,
                lambda: asyncio.create_task(self._execute_batch(model_signature, predictor))
            )
    
    async def _execute_batch(self, model_signature: str, predictor: BatchPredictor):
        """Execute batch prediction"""
        if model_signature not in self._pending_batches:
            return
            
        batch = self._pending_batches.pop(model_signature)
        if model_signature in self._batch_timers:
            self._batch_timers[model_signature].cancel()
            del self._batch_timers[model_signature]
        
        try:
            # Batch inference
            results = predictor.predict_batch(batch.features)
            
            # Dispatch results to callbacks
            for callback, result in zip(batch.callbacks, results):
                try:
                    callback(result)
                except Exception as e:
                    # Log callback error but don't fail batch
                    pass
                    
        except Exception as e:
            # Fallback: call all callbacks with None
            for callback in batch.callbacks:
                callback(None)
```

#### 2.2 Process Pool ML Inference
**Rationale**: Sidestep Python GIL for CPU-intensive ML inference.

```python
# NEW: services/strategy_runner/components/ml_inference_pool.py
import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Any, List, Optional
import pickle
import numpy as np

class MLInferencePool:
    """Process pool for CPU-intensive ML inference"""
    
    def __init__(self, max_workers: int = None, queue_size: int = 1000):
        self.executor = ProcessPoolExecutor(max_workers=max_workers)
        self.queue_size = queue_size
        self._active_tasks = 0
        
    async def predict_async(self, model_path: str, features: Dict[str, Any], 
                           timeout_seconds: float = 1.0) -> Optional[Dict[str, Any]]:
        """Async wrapper for CPU-bound ML inference"""
        if self._active_tasks >= self.queue_size:
            raise RuntimeError("ML inference pool saturated")
            
        self._active_tasks += 1
        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(self.executor, _predict_worker, model_path, features),
                timeout=timeout_seconds
            )
            return result
        except asyncio.TimeoutError:
            return None
        finally:
            self._active_tasks -= 1
    
    async def predict_batch_async(self, model_path: str, feature_batch: List[Dict[str, Any]],
                                 timeout_seconds: float = 2.0) -> List[Optional[Dict[str, Any]]]:
        """Batch prediction in process pool"""
        if self._active_tasks >= self.queue_size:
            return [None] * len(feature_batch)
            
        self._active_tasks += 1
        try:
            loop = asyncio.get_event_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(self.executor, _predict_batch_worker, model_path, feature_batch),
                timeout=timeout_seconds
            )
            return results
        except asyncio.TimeoutError:
            return [None] * len(feature_batch)
        finally:
            self._active_tasks -= 1
    
    def shutdown(self):
        """Clean shutdown"""
        self.executor.shutdown(wait=True)

def _predict_worker(model_path: str, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Worker function - runs in separate process"""
    try:
        # Load model (cache in process)
        if not hasattr(_predict_worker, '_model_cache'):
            _predict_worker._model_cache = {}
        
        if model_path not in _predict_worker._model_cache:
            # Load ONNX/sklearn/xgboost model
            import joblib
            _predict_worker._model_cache[model_path] = joblib.load(model_path)
        
        model = _predict_worker._model_cache[model_path]
        
        # Convert features to numpy array
        feature_array = np.array(list(features.values())).reshape(1, -1)
        
        # Predict
        prediction = model.predict(feature_array)[0]
        probabilities = getattr(model, 'predict_proba', lambda x: None)(feature_array)
        
        return {
            "prediction": float(prediction),
            "probabilities": probabilities[0].tolist() if probabilities is not None else None,
            "features_used": list(features.keys())
        }
    except Exception as e:
        return None

def _predict_batch_worker(model_path: str, feature_batch: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
    """Batch worker function"""
    try:
        # Similar to single prediction but vectorized
        # Implementation details...
        return [_predict_worker(model_path, features) for features in feature_batch]
    except Exception:
        return [None] * len(feature_batch)
```

### Phase 3: Enhanced Strategy Framework (2-3 weeks)

#### 3.1 Updated Strategy Executor for ML
**Alignment**: Enhance current `StrategyExecutor` class with ML capabilities.

```python
# UPDATED: strategies/core/executor.py (enhance existing)
class MLStrategyExecutor(StrategyExecutor):
    """Enhanced executor for ML strategies - extends current StrategyExecutor"""
    
    def __init__(self, processor: MLStrategyProcessor, validator: StrategyValidator,
                 config: StrategyConfig, context: ExecutionContext,
                 history_store: InstrumentHistoryStore = None,
                 feature_store: FeatureStore = None,
                 inference_pool: MLInferencePool = None):
        super().__init__(processor, validator, config, context)
        
        # ML-specific components
        self._history_store = history_store
        self._feature_store = feature_store  
        self._inference_pool = inference_pool
        
        # Remove per-executor history - use shared store
        self._history = None  # Shared history eliminates this
        
        # ML-specific metrics
        self._inference_count = 0
        self._cache_hits = 0
        self._inference_latency = []
        
    async def process_tick_async(self, tick: MarketData) -> Optional[SignalResult]:
        """Async processing for ML strategies with shared resources"""
        if not self.can_process_tick(tick):
            return None
        
        start_time = time.time()
        
        try:
            # Use shared history store
            history = []
            if self._history_store:
                history = self._history_store.get_history_slice(
                    tick.instrument_token, 
                    self._processor.get_required_history_length()
                )
            
            # Get shared features if available
            shared_features = {}
            if self._feature_store and hasattr(self._processor, 'get_required_features'):
                required_features = self._processor.get_required_features()
                for feature_name, params in required_features.items():
                    shared_features[feature_name] = await self._feature_store.get_feature(
                        tick.instrument_token, feature_name, params.get('window', 20), history, params
                    )
            
            # Extract strategy-specific features
            features = self._processor.extract_features(tick, history, shared_features)
            
            # ML inference (potentially batched/async)
            signal = None
            if self._inference_pool and hasattr(self._processor, 'get_model_path'):
                model_path = self._processor.get_model_path()
                inference_result = await self._inference_pool.predict_async(model_path, features)
                
                if inference_result:
                    signal = self._processor.convert_prediction_to_signal(inference_result, tick)
                    
            else:
                # Fallback to sync prediction
                signal = self._processor.predict(features)
            
            # Validate signal
            if signal and self._validator.validate_signal(signal, tick):
                self._inference_count += 1
                latency = (time.time() - start_time) * 1000
                self._inference_latency.append(latency)
                return signal
                
        except Exception as e:
            # Log error but don't fail
            pass
        
        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Enhanced metrics for ML strategies"""
        base_metrics = super().get_metrics()
        
        ml_metrics = {
            "inference_count": self._inference_count,
            "cache_hits": self._cache_hits,
            "avg_inference_latency_ms": np.mean(self._inference_latency) if self._inference_latency else 0,
            "p95_inference_latency_ms": np.percentile(self._inference_latency, 95) if self._inference_latency else 0,
        }
        
        return {**base_metrics, **ml_metrics}
```

#### 3.2 ML Strategy Template
```python
# NEW: strategies/implementations/ml_template/ml_momentum_strategy.py
import numpy as np
from typing import List, Dict, Any, Optional
from decimal import Decimal
from strategies.core.protocols import MLStrategyProcessor, SignalResult
from core.schemas.events import MarketTick

class MLMomentumProcessor(MLStrategyProcessor):
    """ML-enhanced momentum strategy using shared resources"""
    
    def __init__(self, model_path: str, lookback_periods: int = 20, 
                 confidence_threshold: float = 0.6):
        self.model_path = model_path
        self.lookback_periods = lookback_periods
        self.confidence_threshold = confidence_threshold
        
    def get_required_features(self) -> Dict[str, Dict[str, Any]]:
        """Define features needed from shared feature store"""
        return {
            "sma_5": {"window": 5},
            "sma_20": {"window": 20}, 
            "rsi_14": {"window": 14},
            "volatility_10": {"window": 10}
        }
    
    def extract_features(self, tick: MarketTick, history: List[MarketTick], 
                        shared_features: Dict[str, Any]) -> Dict[str, Any]:
        """Extract features using shared cache + custom logic"""
        features = {}
        
        # Use shared features
        features.update(shared_features)
        
        # Add custom features  
        if len(history) >= self.lookback_periods:
            prices = np.array([float(t.last_price) for t in history[-self.lookback_periods:]])
            returns = np.diff(prices) / prices[:-1]
            
            features.update({
                "momentum_5_1": float((prices[-1] - prices[-5]) / prices[-5]) if len(prices) >= 5 else 0,
                "momentum_20_1": float((prices[-1] - prices[-20]) / prices[-20]) if len(prices) >= 20 else 0,
                "returns_std": float(np.std(returns)),
                "returns_skew": float(scipy.stats.skew(returns)) if len(returns) > 3 else 0,
                "current_price": float(tick.last_price)
            })
        
        return features
    
    def predict(self, features: Dict[str, Any]) -> Optional[SignalResult]:
        """Convert ML prediction to trading signal"""
        # This would be called by inference pool or sync fallback
        # Model loading/prediction handled by pool
        pass
        
    def convert_prediction_to_signal(self, inference_result: Dict[str, Any], 
                                   tick: MarketTick) -> Optional[SignalResult]:
        """Convert ML model output to SignalResult"""
        prediction = inference_result.get("prediction", 0)
        probabilities = inference_result.get("probabilities", [0.5, 0.5])
        
        # Convert to signal based on prediction
        if prediction == 1 and max(probabilities) > self.confidence_threshold:
            return SignalResult(
                signal_type="BUY",
                confidence=float(max(probabilities) * 100),
                quantity=100,
                price=tick.last_price,
                reasoning=f"ML prediction: BUY (confidence: {max(probabilities):.2f})",
                metadata={
                    "model_prediction": prediction,
                    "model_confidence": max(probabilities),
                    "features_used": list(inference_result.get("features_used", []))
                }
            )
        elif prediction == -1 and max(probabilities) > self.confidence_threshold:
            return SignalResult(
                signal_type="SELL", 
                confidence=float(max(probabilities) * 100),
                quantity=100,
                price=tick.last_price,
                reasoning=f"ML prediction: SELL (confidence: {max(probabilities):.2f})"
            )
        
        return None
    
    def supports_batch_prediction(self) -> bool:
        return True
        
    def get_model_info(self) -> Dict[str, Any]:
        return {
            "model_path": self.model_path,
            "model_type": "sklearn_ensemble", 
            "version": "1.0",
            "feature_count": len(self.get_required_features()) + 5  # shared + custom
        }
    
    # Implement required StrategyProcessor methods
    def process_tick(self, tick: MarketTick, history: List[MarketTick]) -> Optional[SignalResult]:
        """Fallback sync processing"""
        return None  # Handled by MLStrategyExecutor.process_tick_async
        
    def get_required_history_length(self) -> int:
        return self.lookback_periods
        
    def supports_instrument(self, token: int) -> bool:
        return True
        
    def get_strategy_name(self) -> str:
        return "ml_momentum"
```

### Phase 4: Integration & Observability (1-2 weeks)

#### 4.1 Enhanced Strategy Runner Service
**Alignment**: Update current `StrategyRunnerService` with ML capabilities.

```python
# UPDATED: services/strategy_runner/service.py (enhance existing)
class StrategyRunnerService:
    """Enhanced with ML infrastructure - extends current implementation"""
    
    def __init__(self, config: RedpandaSettings, settings: Settings, 
                 db_manager: DatabaseManager, redis_client=None, 
                 market_hours_checker: MarketHoursChecker = None, 
                 prometheus_metrics: PrometheusMetricsCollector = None):
        
        # Keep existing initialization...
        super().__init__(config, settings, db_manager, redis_client, market_hours_checker, prometheus_metrics)
        
        # NEW: ML Infrastructure Components
        self.history_store = InstrumentHistoryStore(max_history_per_instrument=2000)
        self.feature_store = FeatureStore(redis_client) if redis_client else None
        self.ml_inference_pool = MLInferencePool(max_workers=settings.strategy_ml_pool_size)
        self.batch_scheduler = MicroBatchScheduler(
            batch_window_ms=settings.strategy_batch_window_ms,
            max_batch_size=settings.strategy_max_batch_size
        )
        
        # Enhanced metrics
        self.ml_strategy_count = 0
        self.total_inference_time = 0
        self.batch_efficiency_ratio = 0
    
    async def start(self):
        """Enhanced startup with ML components"""
        await super().start()  # Keep existing startup logic
        
        # Additional ML-specific startup
        self.logger.info("🧠 ML infrastructure initialized", 
                        history_store=True,
                        feature_store=self.feature_store is not None,
                        ml_pool_workers=self.ml_inference_pool.executor._max_workers)
    
    async def _handle_market_tick(self, message: Dict[str, Any], topic: str) -> None:
        """Enhanced tick handling with shared resources"""
        if not self._is_event_type(message, EventType.MARKET_TICK):
            return
            
        if not self.market_hours_checker.is_market_open():
            self.logger.debug("Ignoring market tick - market is closed")
            return
        
        tick_data = message.get("data", {})
        instrument_token = tick_data.get("instrument_token")
        
        if not instrument_token:
            return
        
        # Convert to MarketTick
        market_tick = MarketTick(
            instrument_token=tick_data["instrument_token"],
            last_price=tick_data["last_price"], 
            timestamp=tick_data["timestamp"],
            symbol=tick_data.get("symbol", "")
        )
        
        # Update shared history store ONCE per tick
        await self.history_store.update_tick(market_tick)
        
        # Get interested strategies (O(1) lookup - already implemented)
        interested_strategy_ids = self.instrument_to_strategies.get(instrument_token, [])
        if not interested_strategy_ids:
            return
        
        # Process through each strategy - enhanced for ML
        for strategy_id in interested_strategy_ids:
            executor = self.strategy_executors.get(strategy_id)
            if executor and isinstance(executor, MLStrategyExecutor):
                try:
                    # Async ML processing
                    signal_result = await executor.process_tick_async(market_tick)
                    if signal_result:
                        await self._emit_signals_multi_broker(signal_result, strategy_id, tick_data)
                        
                except Exception as e:
                    self.error_logger.error("ML strategy processing error",
                                          strategy_id=strategy_id,
                                          error=str(e))
            
            elif executor:
                # Standard composition processing (keep existing)
                signal_result = executor.process_tick(market_tick)  
                if signal_result:
                    await self._emit_signals_multi_broker(signal_result, strategy_id, tick_data)
    
    async def _emit_signals_multi_broker(self, signal_result: SignalResult, 
                                       strategy_id: str, tick_data: Dict[str, Any]):
        """Multi-broker signal emission (keep existing logic)"""
        # Keep existing implementation from current service.py
        # This ensures alignment with current multi-broker architecture
        pass
```

#### 4.2 Enhanced Monitoring & Metrics

```python
# Updated Prometheus metrics
STRATEGY_ML_METRICS = {
    "strategy_inference_latency_ms": "histogram",
    "strategy_batch_size": "gauge", 
    "feature_cache_hit_ratio": "gauge",
    "history_store_utilization": "gauge",
    "ml_pool_queue_depth": "gauge",
    "strategy_quarantined_total": "counter",
    "model_load_time_seconds": "histogram",
    "batch_efficiency_ratio": "gauge"
}
```

---

## 🎯 Performance Targets & Validation

### Benchmarking Plan
1. **Baseline**: Measure current system with 10-20 composition strategies
2. **Phase 1**: Test shared resources with 25-50 strategies  
3. **Phase 2**: Validate ML infrastructure with 50+ strategies
4. **Phase 3**: Full load test with 100 concurrent ML strategies

### Success Criteria
- **P99 latency <50ms**: From tick receipt to signal emission
- **Memory efficiency**: <50MB per additional strategy (vs current ~200MB+)
- **Throughput**: Handle 1000+ ticks/second across all strategies  
- **Fault tolerance**: Individual strategy failures don't impact others
- **Hot reload**: Add/remove/modify strategies without service restart

---

## 🔧 Configuration Extensions

```bash
# New settings for ML scaling
STRATEGY__MAX_ML_WORKERS=4
STRATEGY__BATCH_WINDOW_MS=20
STRATEGY__MAX_BATCH_SIZE=32
STRATEGY__HISTORY_STORE_SIZE=2000
STRATEGY__FEATURE_CACHE_TTL_SECONDS=300
STRATEGY__INFERENCE_TIMEOUT_SECONDS=1.0
STRATEGY__ML_POOL_QUEUE_SIZE=1000
```

---

## 🚀 Migration Path from Current System

### Week 1-2: Foundation
1. **Implement shared InstrumentHistoryStore** - integrate with existing StrategyRunnerService
2. **Add FeatureStore** - optional path alongside existing processing
3. **Create MLStrategyExecutor** - extends current StrategyExecutor

### Week 3-4: ML Infrastructure  
1. **Add micro-batching** - fallback to sync processing if batch fails
2. **Implement process pools** - optional for ML strategies only
3. **Create ML strategy template** - demonstrate complete ML workflow

### Week 5-6: Production Integration
1. **Enhance monitoring** - add ML-specific metrics to existing Prometheus setup
2. **Load testing** - validate 50-100 strategy target
3. **Documentation** - update strategy development guide

---

## 🛡️ Risk Mitigation & Safety

### Circuit Breakers
- **Per-strategy failure thresholds**: Quarantine after 5 consecutive failures
- **ML pool saturation**: Graceful degradation to sync processing
- **Feature cache failures**: Fallback to direct computation

### Resource Limits
- **Bounded queues**: Prevent memory exhaustion
- **Inference timeouts**: Prevent hanging strategies
- **Memory monitoring**: Alert on excessive memory growth

### Rollback Strategy
- **Feature flags**: Enable/disable ML infrastructure components
- **Gradual migration**: Start with 10-20 ML strategies, scale gradually
- **Fallback paths**: Every ML feature has non-ML fallback

---

## 📚 References & Dependencies

### New Dependencies
```python
# ML & Scientific Computing
numpy>=1.21.0
scipy>=1.7.0
scikit-learn>=1.0.0
onnxruntime>=1.12.0  # Optional for ONNX models
joblib>=1.1.0

# Performance
numba>=0.56.0  # Optional for JIT compilation
```

### Architecture Alignment
- ✅ **Composition-Only**: All ML strategies use StrategyProcessor protocol
- ✅ **Multi-Broker**: ML strategies emit to all configured brokers
- ✅ **StreamServiceBuilder**: ML infrastructure integrates with existing service patterns  
- ✅ **Protocol-Based**: New ML protocols extend existing StrategyProcessor
- ✅ **Database-Driven**: ML strategies loaded from PostgreSQL configuration

---

**IMPLEMENTATION STATUS**: Ready for Phase 1 development with full architectural alignment.