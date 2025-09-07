# Strategy Scaling Improvements (50–100 ML Strategies)

This document proposes targeted enhancements to support running 50–100 machine‑learning (ML) strategies concurrently with predictable latency, high reliability, and observability. It covers both the `services/strategy_runner` and the `strategies` module.

## Goals
- Throughput: Sustain shared `market.ticks` at realistic tick rates while dispatching to 50–100 strategies.
- Latency: 99p signal emission latency under 50–150 ms (configurable budget) from tick arrival to publish.
- Stability: Strategy faults isolated; backpressure and sheds load without cascading failures.
- Efficiency: Avoid redundant computation and memory duplication across strategies.
- Operability: Rich per‑strategy metrics, model lifecycle controls, and safe hot reloads.

---

## Fixes to Previously Identified Issues (Folded Into Plan)

- Tracing and correlation continuity:
  - Tighten span scope so strategy processing occurs within the `strategy.process_tick` span.
  - Propagate `correlation_id` from incoming envelopes to emitted signal events.
- Broker‑agnostic execution path:
  - Make `StrategyExecutor` processing independent of a single broker context; runner handles multi‑broker emissions.
- Documentation alignment and fallback semantics:
  - Align READMEs to composition‑only architecture; document that runtime loads from DB. If YAML fallback is desired, specify it and implement; otherwise, remove the claim.
- Input metrics completeness:
  - Record `market_tick processed` metrics in the runner (throughput and latency), even though broker is `unknown` for shared topics.
- Code hygiene and consistency:
  - Remove unused imports and unused loggers; standardize logger usage; ensure TopicMap/validator usage remains consistent.

---

## Strategy Runner: Improvements

- **Shared Instrument History**: Replace per‑executor deques with a per‑instrument ring buffer service.
  - Rationale: 50–100 strategies × N instruments multiplies memory; most strategies read the same windows.
  - Design: `InstrumentHistoryStore` keyed by `instrument_token` → fixed‑size ring of `MarketTick` plus cached rolling stats.
  - API: `get_slice(token, length)` returns a lightweight view; avoid copying on hot path.

- **Shared Feature Cache**: Compute common features once per instrument per tick and share.
  - Rationale: Many ML strategies reuse moving averages, RSI, returns, z‑scores.
  - Design: `FeatureStore` with pluggable `FeaturePipelines` (NumPy‑vectorized), keyed by `(instrument_token, feature, window, params, ts_bucket)`.
  - Invalidation: time‑bucketed (e.g., 1s) caches to avoid thrash on high‑freq ticks.

- **Inference Micro‑Batching**: Batch predictions across strategies within a short window (e.g., 5–20 ms).
  - Rationale: Amortize Python overhead and leverage vectorized libs / ONNX Runtime batching.
  - Design: Per‑process bounded queue; scheduler forms micro‑batches by model signature and feature shape, then executes in pools.
  - SLA: Guardrail with timeout; if batch does not fill in time, run partial.

- **Parallel Execution Pools**: Offload ML to CPU/GPU worker pools to avoid GIL contention.
  - CPU: `concurrent.futures.ProcessPoolExecutor` for scikit‑learn/XGBoost/LightGBM.
  - GPU: Optional ONNX Runtime / Torch inference workers via `multiprocessing` or Triton/HTTP (see below).
  - Backpressure: Bounded task queues; shed load or degrade gracefully once saturated.

- **Model Server Option**: Support remote inference for heavy models.
  - Options: ONNX Runtime Server, NVIDIA Triton, or a lightweight FastAPI predictor with batching.
  - Routing: Strategy declares `inference_backend: inprocess|onnxrt|remote`; runner picks adapter.
  - Circuit‑breaker: Per‑backend health + retries + failover to HOLD/skip.

- **Strategy Scheduler & Budgets**: Introduce a fairness/budgeted scheduler.
  - Per‑strategy compute budgets (ms/sec) and priority classes (critical/normal/background).
  - Drop or sample low‑priority strategies under pressure; record drops with metrics.

- **Tick Dispatch Optimizations**: Keep O(1) routing and reduce Python overhead.
  - Pre‑compute interested strategy IDs once; store compiled callables (no repeated attribute lookups).
  - Avoid per‑tick object allocations by reusing small structs and leveraging dataclass slots.

- **Warmup & Cooldown**: Gate strategy execution until feature/history warmup is complete.
  - Runner maintains per‑strategy instrument warmup status; suppress predictions early.

- **Hot Reload & Live Tuning**: Safe reconfiguration without restarts.
  - Watch DB rows; reconcile deltas: add/remove strategies, swap models, change params.
  - Quiesce and replace executors atomically; drain and resume to preserve ordering.

- **Fault Isolation & Circuit Breakers**: Contain bad actors.
  - Per‑strategy failure counters, exponential backoff, quarantine on repeated exceptions.
  - DLQ tagging `dlq=true` and reason in metadata for analytics.

- **Observability Upgrades**:
  - Metrics: `strategy_inference_latency_ms{strategy,broker}`, `strategy_batch_size{model}`, `feature_cache_hit_ratio{feature}`, `history_ring_utilization{instrument}`, `drops_total{reason}`.
  - Tracing: Parent span per tick dispatch; child spans per strategy inference; include `model_version`.
  - Logging: Sampled info logs; structured errors with model/feature context.
  - Input counters/timers: `market_tick_processed_total{service}` and `market_tick_process_latency_ms{service}` for shared input load.

- **Configuration Surfaces**:
  - New settings: `STRATEGY__MAX_CONCURRENCY`, `STRATEGY__BATCH_WINDOW_MS`, `STRATEGY__POOL_SIZE`, `STRATEGY__REMOTE_INFERENCE_URL`, `STRATEGY__WARMUP_TICKS`.
  - Per‑strategy overrides via DB `parameters`.

---

## Strategies Module: Improvements

- **Expanded Protocols**: Split responsibilities for ML pipelines.
  - `FeatureExtractor`: `extract(tick, history, shared_features) -> Dict[str, Any]`.
  - `ModelPredictor`: `predict(batch_features) -> np.ndarray | List[Pred]` with batch support.
  - `DecisionPostProcessor`: thresholding, calibration, position sizing, and sanity guards.
  - Update `StrategyExecutor` to orchestrate these components and accept shared history/features.

- **Model Abstraction & Registry**:
  - `ModelSpec` (path, framework, version, signature, device).
  - `ModelRegistry` (filesystem, S3, or DB‑tracked) with checksum verification and lazy loading.
  - ONNX first‑class: convert/sklearn/xgboost/lightgbm → ONNX; use `onnxruntime` for speed and uniformity.

- **Vectorization & Batching**:
  - Feature extractors produce NumPy arrays with consistent dtypes/shapes.
  - Predictors accept `N×F` matrices; avoid Python loops.
  - Optional Numba for bespoke numeric features; guard for fallback.

- **Shared Feature Pipelines**:
  - Define canonical feature definitions (e.g., SMA, EMA, RSI, returns) and register in `FeatureStore`.
  - Hash feature config to key the cache; expose reusability across strategies.

- **Determinism & Reproducibility**:
  - Standardize RNG seeding (`numpy`, `random`, framework‑specific) via `ExecutionContext.seed`.
  - Record `model_version`, `feature_hash`, `seed` in signal metadata.

- **Safety & Validation**:
  - Extend `StrategyValidator` to include schema checks for feature values (NaN/inf), model output ranges, and confidence calibration.
  - Add drift detectors: population/feature drift alerts (e.g., PSI, KS test) out‑of‑band.

- **Testing Harness**:
  - Contract tests: model I/O schema validation, batch invariants, and reproducibility checks.
  - Golden tests for feature pipelines using fixture data.

- **Templates & Examples**:
  - Provide a `strategies/implementations/ml_template/` showing the 3‑stage pipeline and ONNX usage.

- **Broker‑Agnostic Execution**:
  - Remove broker gating from `StrategyExecutor.can_process_tick()` or set a neutral broker context; strategy logic should not depend on a single broker, as emission is broker‑scoped in the runner.

---

## Deployment & Scaling Patterns

- **Horizontal Scale**: Multiple strategy_runner replicas in one consumer group; partitions pin subsets of instruments.
- **Capacity Planning**: Start with 1–2 process pools sized to CPU cores; measure inference latency and adjust.
- **Remote Inference**: For large models, run a dedicated inference service with batching; authenticate and isolate resources.
- **GPU Utilization**: If applicable, segregate GPU‑backed inference workers from CPU feature workers.

---

## Implementation Plan (Phased)

### Phase 1: Quick Wins (1–2 weeks)
- Strategy Runner
  - Add shared `InstrumentHistoryStore` and wire into executor.
  - Add `FeatureStore` with a few common rolling features.
  - Introduce micro‑batching scaffold and bounded worker pools (CPU).
  - Propagate `correlation_id` and tighten spans around inference.
- Strategies
  - Extend protocols; refactor momentum/mean‑reversion to use extractor→predictor→post‑processor.
  - Add ONNX Runtime dependency (optional path) and a dummy ONNX example.
  - Make executor broker‑agnostic (remove broker checks); update tests accordingly.
- Observability
  - Add latency histograms, batch size gauges, cache hit ratios, and drops.
  - Add `market_tick processed` counters/timers in the runner.

Acceptance: Same outputs as today with comparable latency for classic strategies; new metrics visible under `/metrics`.

### Phase 2: ML First‑Class (2–4 weeks)
- Strategy Runner
  - Enable model registry loading and lazy warmup; add health/circuit breaker.
  - Implement proper micro‑batching by model signature; add scheduler with budgets.
- Strategies
  - Provide ML template and convert first 10 ML strategies to the new pipeline.
  - Vectorize feature extraction; add calibration/post‑processing components.

Acceptance: 50 ML strategies running with 99p latency within budget on dev hardware; no uncontrolled memory growth.

### Phase 3: Scale & Hardening (4–8 weeks)
- Remote inference adapter (optional); add canary/shadow modes per strategy.
- Advanced drift monitoring and auto‑quarantine under anomalies.
- Hot reload of strategy params/models without restart; rolling swaps.

Acceptance: 100 ML strategies steady‑state, graceful degradation under load, full observability, and safe hot reloads.

---

## Touchpoints (Code Outline)

- `services/strategy_runner/`
  - `service.py`: integrate `InstrumentHistoryStore`, `FeatureStore`, micro‑batch scheduler, worker pools, budgets.
  - `components/history_store.py`: shared per‑instrument ring buffers.
  - `components/feature_store.py`: registry + cache + rolling features.
  - `components/predict_worker.py`: process pool/gpu adapters; batch API.
  - README alignment: update to composition‑only; clarify DB load and optional YAML fallback.

- `strategies/core/`
  - `protocols.py`: add `FeatureExtractor`, `ModelPredictor`, `DecisionPostProcessor`.
  - `executor.py`: orchestrate new pipeline; accept shared history/features and batch contexts.
  - `config.py`: extend with `model_spec`, `inference_backend`, `warmup_ticks`, `seed`.
  - `factory.py`: construct components from `StrategyConfig` + registry.
  - Broker‑agnostic execution: remove broker gating or set neutral broker in context.

- `strategies/implementations/`
  - `ml_template/`: feature extractor, ONNX predictor, post‑processor example.

---

## Metrics (Prometheus Names)
- `strategy_inference_latency_ms{strategy,broker,model}` (histogram)
- `strategy_batch_size{model}` (gauge)
- `feature_cache_hit_ratio{feature}` (gauge)
- `history_ring_utilization{instrument}` (gauge)
- `strategy_drops_total{strategy,reason}` (counter)
- `strategy_quarantined{strategy}` (gauge)
- `model_load_seconds{model,version}` (histogram)
 - `market_tick_processed_total{service}` (counter)
 - `market_tick_process_latency_ms{service}` (histogram)

---

## Risk & Safety
- Timeouts per inference and per batch; bounded queues to avoid unbounded latency.
- Circuit breakers per strategy and backend; quarantine on repeated failures.
- Validation gates (NaN/inf, out‑of‑range) before emitting; route to DLQ with `dlq=true` tag on violation.

---

## Next Steps
- Confirm Phase 1 scope and hardware targets (CPU cores, memory).
- Choose ONNX Runtime vs in‑process framework for initial ML cohort.
- Prioritize first 10 ML strategies for migration using the template.
 - Update READMEs and docs to reflect composition‑only architecture and clarify YAML fallback policy.
