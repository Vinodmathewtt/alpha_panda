## Strategy Module Recommendations

I dug through your repo (the `/services/strategy_runner` and `/strategies/**` bits in your zip) and here’s the short truth:

- You already **moved to composition + protocols** (nice!) but the **runner still behaves ML-first**: it tries to detect ML processors, performs **ML model validation**, and logs ML metrics specially.
- The **core protocols are flexible**, but comments and the factory lean “ML-only”. Your existing `StrategyProcessor` can already host a non-ML strategy that just implements `process_tick()`. The friction is in **factory registration**, **startup validation**, and **service orchestration**.

Below is a concrete, minimal-risk rebuild to make the whole thing **truly strategy-agnostic** while keeping your composition vibe and your OOP rules (protocols > inheritance, pure domain, typed, tiny public API). I’m giving you (1) the target shape, (2) precise file-by-file changes, (3) new example strategies (ML, rules, hybrid), and (4) migration steps and safety rails.

---

# What we’ll aim for

1. **Protocol-first contracts (unchanged in spirit, clarified in code):**

   - Minimal required: a **processor** that exposes `process_tick(tick, history) -> Optional[SignalResult]`.
   - Optional capabilities: `load_model()`, `warmup()`, `on_bar()`, etc. The runner only calls what exists.
   - Validators stay pluggable.

2. **Factory becomes engine-agnostic:**
   Registry maps `strategy_type -> factory path`. No ML assumptions. If a processor _happens_ to have `load_model()`, the runner will call it. If not, fine.

3. **Runner policy is capability-driven, not ML-driven:**

   - At startup, **if** a processor has `load_model`, call it and fail _that strategy only_ if it returns False or throws (no global ML gates).
   - If it has `warmup`, call it.
   - Everything else identical: `process_tick` → `SignalResult` → risk/route.

4. **Signals unified:**
   One `SignalResult` everywhere, normalize confidence to `[0.0, 1.0]` (you already do that). Map `str` → `SignalType` enum (you already do that too).

---

# File-by-file implementation

I’ll show **surgical diffs** (copy/pasteable) and a couple of **new files** for examples.
Paths are relative to `algo_panda_24/`.

---

## 1) `strategies/core/protocols.py` — keep it minimal & capability-based

Your file already hints at this, but the comments still suggest ML-first. Replace it with the following clarified version (keeps your public shape identical so nothing else breaks):

```python
# strategies/core/protocols.py
"""
Strategy protocols for composition-based architecture.
A processor may be ML-based, rule-based, or hybrid.
The runner calls the minimal contract, and optionally calls capabilities if present.
"""

from typing import Protocol, List, Dict, Any, Optional
from dataclasses import dataclass
from decimal import Decimal
from core.schemas.events import MarketTick as MarketData

@dataclass(frozen=True, slots=True)
class SignalResult:
    """Immutable signal result value object"""
    signal_type: str  # "BUY", "SELL", "HOLD"
    confidence: float  # 0.0..1.0 preferred; 0..100 accepted and normalized by runner
    quantity: int
    price: Decimal
    reasoning: Optional[str] = None

class StrategyProcessor(Protocol):
    """Minimal required contract for any strategy (ML, rules, hybrid)."""
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        ...

    # Optional capabilities. Runner will call them if available.
    def warmup(self, history: List[MarketData]) -> None: ...
    def on_bar(self, bar: Dict[str, Any]) -> None: ...
    def shutdown(self) -> None: ...

    # ML-capabilities (OPTIONAL)
    def load_model(self) -> bool: ...
    def extract_features(self, tick: MarketData, history: List[MarketData]) -> Any: ...
    def predict_signal(self, features: Any) -> Optional[SignalResult]: ...

class StrategyValidator(Protocol):
    """Validator for signals and configs (composition)"""
    def validate_signal(self, signal: SignalResult, market_data: MarketData) -> bool: ...
    def validate_configuration(self, config: Dict[str, Any]) -> bool: ...
```

**Why:**

- Your existing executor only needs `process_tick`.
- Non-ML strategies implement **only** `process_tick`.
- ML strategies can expose `load_model` and friends.
- Hybrid strategies can do both.

---

## 2) `strategies/core/factory.py` — unify registry; drop “ML-only” assumptions

Replace the **commentary + registry** bits so it’s explicitly agnostic. Keep your API intact:

```python
# strategies/core/factory.py
"""
Strategy factory for creating strategy executors using composition.
Agnostic to ML vs rules; registry points strategy_type -> create_* factory.
"""

import importlib
from typing import Dict, Any
from .protocols import StrategyProcessor, StrategyValidator
from .executor import StrategyExecutor
from .config import StrategyConfig, ExecutionContext

class StrategyFactory:
    def __init__(self):
        # strategy_type -> "module_path.create_processor"
        self._processors: Dict[str, str] = {}
        # validator_type -> "module_path.create_validator"
        self._validators: Dict[str, str] = {}

    def create_strategy(
        self,
        strategy_id: str,
        strategy_type: str,
        parameters: Dict[str, Any],
        brokers: list[str],
        instrument_tokens: list[int],
        validator_type: str | None = None,
    ) -> StrategyExecutor:
        # Load processor factory
        if strategy_type not in self._processors:
            raise ValueError(f"Unknown strategy_type: {strategy_type}")
        processor_factory = self._load(self._processors[strategy_type])
        processor: StrategyProcessor = processor_factory(parameters)

        # Optional validator
        if validator_type:
            if validator_type not in self._validators:
                raise ValueError(f"Unknown validator_type: {validator_type}")
            validator_factory = self._load(self._validators[validator_type])
            validator: StrategyValidator = validator_factory(parameters)
        else:
            # Safe default validator if none registered
            from strategies.validation.standard_validator import create_standard_validator
            validator = create_standard_validator(parameters)

        config = StrategyConfig(
            strategy_id=strategy_id,
            strategy_type=strategy_type,
            parameters=parameters,
            active_brokers=brokers,
            instrument_tokens=instrument_tokens,
            max_position_size=parameters.get("max_position_size"),
            risk_multiplier=parameters.get("risk_multiplier"),
            enabled=True,
        )

        context = ExecutionContext(
            broker=(brokers[0] if brokers else "paper"),
            portfolio_state={},
            market_session="regular",
            risk_limits={"max_position": parameters.get("max_position_size")},
        )

        return StrategyExecutor(
            processor=processor,
            validator=validator,
            config=config,
            context=context,
        )

    def register_processor(self, strategy_type: str, factory_path: str) -> None:
        self._processors[strategy_type] = factory_path

    def register_validator(self, validator_type: str, factory_path: str) -> None:
        self._validators[validator_type] = factory_path

    def _load(self, dotted: str):
        module_path, func_name = dotted.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        return getattr(mod, func_name)
```

**Key change:** The old comments/code that implied “ML-only registry” are gone; now it’s neutral.

---

## 3) `services/strategy_runner/service.py` — remove ML gates; use capability detection

### A) Remove the ML-only gating on registration

Find the section where you do ML detection (`_is_ml_strategy`) and **skip strategies when `load_model()` fails**. Replace with **capability-aware startup**:

```python
# near where you iterate DB strategies and create executors

executor = StrategyFactory.create_strategy(
    strategy_id=config.id,
    strategy_type=config.strategy_type,
    parameters=config.parameters,
    brokers=(config.active_brokers or (["zerodha"] if config.zerodha_trading_enabled else ["paper"])),
    instrument_tokens=config.instruments,
    validator_type=config.validator_type,  # allow null
)

# Capability-aware startup
# 1) If a processor has load_model(), call it.
_loaded = True
try:
    if hasattr(executor.processor, "load_model"):
        _loaded = bool(executor.processor.load_model())
except Exception as e:
    _loaded = False
    self.logger.error("Model load failed", strategy_id=config.id, error=str(e))

# 2) If a processor has warmup(), call it (ignore errors, just log).
if _loaded and hasattr(executor.processor, "warmup"):
    try:
        # You may pass recent history if you cache it, otherwise an empty list is fine
        executor.processor.warmup([])
    except Exception as e:
        self.logger.warning("Warmup failed (continuing)", strategy_id=config.id, error=str(e))

if _loaded:
    self.strategy_executors[config.id] = executor
    for it in (config.instruments or []):
        self.instrument_to_strategies[it].append(config.id)
else:
    self.logger.error("Strategy disabled due to startup failure", strategy_id=config.id)
```

### B) Keep `_is_ml_strategy` only for **metrics labeling** (optional)

You can keep `_is_ml_strategy()` to mark Prometheus attributes, but it MUST NOT control whether a strategy is allowed to run. If you’d like, redefine it as:

```python
def _is_ml_strategy(self, executor) -> bool:
    # purely for labeling/observability
    p = executor.processor
    return any(hasattr(p, attr) for attr in ("load_model", "predict_signal", "extract_features"))
```

### C) Make broker routing generic

Right now you special-case Zerodha vs Paper. Prefer **`config.active_brokers`** with a sane default:

- In DB: add a JSONB `active_brokers` column (array of strings).
- Fall back to flag only when `active_brokers` is null.

You already track per-broker Prometheus gauges; this will just make it cleaner.

---

## 4) `strategies/core/executor.py` — no change required

Your executor already composes `processor + validator` and calls `validate_signal`. Perfect.
(If you want one tiny polish: expose a typed `supports(instrument_token: int) -> bool` that checks the immutable config set, but you’re already mapping instruments to strategies in the runner.)

---

## 5) Validators — keep the standard one as default

`strategies/validation/standard_validator.py` is great as the default. Consider adding one more (e.g., a strict risk validator) and register it (see below).

---

## 6) Registration bootstrap

Somewhere central (e.g. a startup module or the runner’s `start()`), **register processors and validators** with names that match your DB rows:

```python
# e.g., services/strategy_runner/factory.py or an app bootstrap
from strategies.core.factory import StrategyFactory

# Create and hold a singleton factory or attach it to the service
StrategyFactory.register_processor("ml_momentum", "strategies.implementations.ml_momentum.create_processor")
StrategyFactory.register_processor("rules_rsi", "strategies.implementations.rules_rsi.create_processor")
StrategyFactory.register_processor("hybrid_ml_rsi_filter", "strategies.implementations.hybrid_ml_rsi.create_processor")

StrategyFactory.register_validator("standard", "strategies.validation.standard_validator.create_standard_validator")
# Add more validators if needed
```

(Adjust to where you manage the factory singleton in your codebase.)

---

# New example strategies

Add these **two lightweight** implementations to prove “agnostic” works end-to-end.

### 1) Non-ML: RSI cross

```python
# strategies/implementations/rules_rsi.py
from typing import List, Optional, Dict, Any
from decimal import Decimal
from strategies.core.protocols import StrategyProcessor, SignalResult
from core.schemas.events import MarketTick as MarketData

class RSIRuleProcessor:
    def __init__(self, params: Dict[str, Any]):
        self.period = int(params.get("period", 14))
        self.lower = float(params.get("lower", 30.0))
        self.upper = float(params.get("upper", 70.0))
        self._gains: list[float] = []
        self._losses: list[float] = []
        self._last_price: float | None = None

    def _update_rsi(self, price: float) -> Optional[float]:
        if self._last_price is None:
            self._last_price = price
            return None
        change = price - self._last_price
        self._last_price = price
        self._gains.append(max(0.0, change))
        self._losses.append(max(0.0, -change))
        if len(self._gains) > self.period:
            self._gains.pop(0)
            self._losses.pop(0)
        if len(self._gains) < self.period:
            return None
        avg_gain = sum(self._gains) / self.period
        avg_loss = sum(self._losses) / self.period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        rsi = self._update_rsi(float(tick.last_price))
        if rsi is None:
            return None
        if rsi < self.lower:
            return SignalResult("BUY", confidence=0.7, quantity=1, price=Decimal(str(tick.last_price)), reasoning=f"RSI {rsi:.1f} < {self.lower}")
        if rsi > self.upper:
            return SignalResult("SELL", confidence=0.7, quantity=1, price=Decimal(str(tick.last_price)), reasoning=f"RSI {rsi:.1f} > {self.upper}")
        return None

def create_processor(params: Dict[str, Any]) -> StrategyProcessor:
    return RSIRuleProcessor(params)
```

### 2) Hybrid: Gate ML with a simple RSI filter

```python
# strategies/implementations/hybrid_ml_rsi.py
from typing import List, Optional, Dict, Any
from decimal import Decimal
from strategies.core.protocols import StrategyProcessor, SignalResult
from core.schemas.events import MarketTick as MarketData

class HybridMLWithRSI:
    def __init__(self, params: Dict[str, Any]):
        self.period = int(params.get("period", 14))
        self.lower = float(params.get("lower", 30.0))
        self.upper = float(params.get("upper", 70.0))
        self._last_price: float | None = None
        self._gains: list[float] = []
        self._losses: list[float] = []
        # pretend ML bits
        self.model_path = params.get("model_path", "models/ml_momentum.onnx")

    # --- ML capability (optional) ---
    def load_model(self) -> bool:
        # Load real model here; return False to disable strategy if load fails
        return True

    def extract_features(self, tick: MarketData, history: List[MarketData]) -> Dict[str, float]:
        return {"price": float(tick.last_price)}

    def predict_signal(self, features: Dict[str, float]) -> Optional[SignalResult]:
        # Dummy prediction: BUY when last digit < 5 else SELL
        last_digit = int(str(int(features["price"]))[-1])
        side = "BUY" if last_digit < 5 else "SELL"
        return SignalResult(side, confidence=0.55, quantity=1, price=Decimal(str(features["price"])), reasoning="Toy model")

    # --- RSI rule gate ---
    def _update_rsi(self, price: float) -> Optional[float]:
        if self._last_price is None:
            self._last_price = price
            return None
        change = price - self._last_price
        self._last_price = price
        self._gains.append(max(0.0, change))
        self._losses.append(max(0.0, -change))
        if len(self._gains) > self.period:
            self._gains.pop(0)
            self._losses.pop(0)
        if len(self._gains) < self.period:
            return None
        avg_gain = sum(self._gains) / self.period
        avg_loss = sum(self._losses) / self.period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    # --- unified entrypoint ---
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        rsi = self._update_rsi(float(tick.last_price))
        if rsi is None:
            return None
        if rsi < self.lower or rsi > self.upper:
            # out of neutral zone → allow ML decision
            feats = self.extract_features(tick, history)
            return self.predict_signal(feats)
        return None

def create_processor(params: Dict[str, Any]) -> StrategyProcessor:
    return HybridMLWithRSI(params)
```

Your **existing ML examples** (e.g. `strategies/implementations/ml_momentum.py`) already fit this contract and can stay.

---

# Database and config knobs

- **DB table `strategy_configurations`:**
  Ensure it has:

  - `id` (uuid)
  - `strategy_type` (text) → must match registry name (e.g. `rules_rsi`, `ml_momentum`, `hybrid_ml_rsi_filter`)
  - `parameters` (jsonb)
  - `instruments` (array\[int])
  - `active_brokers` (array\[text]) — **new** (fallback to your existing `zerodha_trading_enabled` only if null)
  - `validator_type` (text, nullable; default `standard`) — **new**

- **Seeding scripts:**
  Add templates for the new strategies; remove ML-only seeding bias.

---

# Observability & safety rails

- **Startup health:** mark “registered strategies” by type, not by ML-ness. Keep model-load stats, but as **capabilities** (e.g., `has_model=true/false`).
- **Per-broker counts:** You already compute these; keep it.
- **Confidence normalization:** You already normalize 0–100 to 0.0–1.0. Keep it.
- **Tracing:** You’re wrapping `executor.process_tick()` inside a span — perfect. Add `span.set_attribute("strategy.type", executor.config.strategy_type)`.

---

# Risk and routing (unchanged, but here’s the clean shape)

Public API of the runner remains tiny:

- `start()` loads strategies, subscribes to ticks.
- On each tick:

  - Look up interested strategies via `instrument_to_strategies` (you already do this).
  - Call `executor.process_tick()`.
  - If you get a `SignalResult`, validate with validator, map to `TradingSignal`, then hand off to risk/order router.

No ML branches anywhere.

---

# Migration plan (low-risk, reversible)

1. **Commit the protocol and factory changes** (backwards compatible).
2. **Add the non-ML `rules_rsi` and hybrid examples**.
3. **Update the runner** with capability-aware startup (safe feature flags: if `load_model` missing, nothing is called).
4. **DB migration**:

   - Add `active_brokers` (nullable array) and `validator_type` (nullable text).
   - Update your seeds to set these fields.

5. **Register processors** centrally with the `StrategyFactory`.
6. **Deploy** with a small canary (paper broker only).
7. **Flip any legacy “ML-only” flags/comments** in logs and dashboards.

---

# Sanity checklist (your OOP rules)

- ✅ **Composition + protocols over inheritance:** processors + validators are protocols; executor composes them.
- ✅ **Small public API:** `StrategyExecutor.process_tick`, `StrategyFactory.create_strategy`.
- ✅ **Pure domain, adapters separate:** no broker logic in strategies.
- ✅ **Immutability:** `StrategyConfig` / `ExecutionContext` are frozen dataclasses (you already have this).
- ✅ **Type everything:** all examples typed; keep mypy/pyright happy.
- ✅ **Inject via protocols:** factories wire protocols, no globals.
- ✅ **Testability:** processors are small units (drop-in fakes for tests).

---

# Quick “does it actually work?” scenario

- Seed three rows:

  - `strategy_type="rules_rsi"` with `{period:14, lower:30, upper:70}`
  - `strategy_type="ml_momentum"` with `{model_path:"..."}`
  - `strategy_type="hybrid_ml_rsi_filter"` with both RSI + `model_path`
    all mapped to the same instruments, `active_brokers=["paper"]`, `validator_type="standard"`.

- Start the runner:

  - It registers all three.
  - Only the two ML-capable processors run `load_model()`.
  - Ticks hit all three via `instrument_to_strategies` mapping.
  - You’ll see signals from rules when RSI crosses, from ML when hybrid gate opens, and from ML momentum as usual.

No special cases. No ML-only code paths. Just capabilities.

---

If you want, I can draft the tiny DB migration and a bootstrap registration module next. But this is the core: **one protocol, one factory, one runner policy — strategy-agnostic by design**.
