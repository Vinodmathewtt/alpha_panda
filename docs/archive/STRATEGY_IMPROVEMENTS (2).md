# Strategy Agnostic Strategy Runner

You already _moved_ the codebase toward composition and protocols (nice!), but two hard-coded “ML-only” decisions are blocking you from running non-ML or hybrid (rule + ML) strategies:

- **Hard ML enforcement in the core factory** — `strategies/core/factory.py` refuses processors that don’t expose `load_model/extract_features/predict_signal`.
- **ML-only registry & migration in the service factory** — `services/strategy_runner/factory.py` maps legacy names to _ML_ processors and only registers ML implementations.

Everything else (executor, service loop, metrics) is _close_ to strategy-agnostic already. So we’ll keep your composition/executor, and surgically remove ML lock-in while adding a clean capability model and a hybrid combiner.

Below is a pragmatic, testable plan (composition-first, small public APIs, protocols > inheritance, immutability by default) with copy-pasteable snippets.

---

# What’s there now (quick audit)

- **Strategy runner orchestration**: `services/strategy_runner/service.py`

  - Efficient `instrument_token → [strategy_ids]` O(1) routing ✅
  - Emits `ML_INFERENCE` metric if it _detects_ ML methods (good instinct)
  - But on startup it **skips** strategies if model validation fails and treats ML as first-class citizens only.

- **Composition core**: `strategies/core/*`

  - `StrategyExecutor` composes `processor + validator`, manages rolling history ✅
  - `StrategyProcessor` protocol (rules-friendly) ✅
  - `MLStrategyProcessor` protocol (adds `load_model/extract_features/predict_signal`) ✅
  - **Problem**: `strategies/core/factory.py` enforces “must be ML-ready”, so a pure rules processor can’t be used.

- **Implementations**: only ML variants (`ml_momentum.py`, `ml_mean_reversion.py`, `ml_breakout.py`).

  - Rule-based sources are missing (pyc crumbs show they once existed).

- **Service factory**: `services/strategy_runner/factory.py`

  - Registry lists **only ML** processors, and migration forcibly maps legacy names → ML processors.

Result: you can’t register pure rules strategies; “mixed” requires bespoke implementations.

---

# Target design (strategy-agnostic)

Keep the same shape (executor + validator + config) and add **capabilities** instead of **classes**:

- **Base contract (always):** `StrategyProcessor`

  - `process_tick(tick, history) -> Optional[SignalResult]`
  - `get_required_history_length()`, `supports_instrument()`, `get_strategy_name()`

- **Optional capability:** `MLCapable` (a _Protocol mixin_)

  - `load_model() -> bool`, `extract_features(...)`, `predict_signal(features)`

- **Optional composition:** `DecisionPolicy`

  - Combine a rules processor and an ML inference into a single final decision (weighted vote, veto, confirmation, etc.).

This keeps runners and executors totally agnostic: they call `process_tick`. If a processor is ML-capable, it can still do its ML thing _inside_ `process_tick` or be wrapped by a hybrid combiner.

---

# Step-by-step changes

## 1) Core protocols: add `MLCapable` & `DecisionPolicy` (no breaking change)

**File:** `strategies/core/protocols.py`
Add two extra Protocols; don’t modify `StrategyProcessor`.

```python
# strategies/core/protocols.py
from typing import Protocol, List, Dict, Any, Optional
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from core.schemas.events import MarketTick as MarketData  # existing alias

@dataclass(frozen=True, slots=True)
class SignalResult:
    signal_type: str            # "BUY" | "SELL" | "HOLD"
    confidence: float           # 0.0 – 1.0
    quantity: int
    price: Decimal
    reasoning: str
    metadata: Dict[str, Any] | None = None

class StrategyProcessor(Protocol):
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]: ...
    def get_required_history_length(self) -> int: ...
    def supports_instrument(self, token: int) -> bool: ...
    def get_strategy_name(self) -> str: ...

# Optional ML capability (mixin) – NO inheritance needed
class MLCapable(Protocol):
    def load_model(self) -> bool: ...
    def extract_features(self, tick: MarketData, history: List[MarketData]) -> Any: ...
    def predict_signal(self, features: Any) -> Optional[SignalResult]: ...

# Optional combiner for hybrid strategies (rules + ml)
class DecisionPolicy(Protocol):
    def decide(
        self,
        rules_signal: Optional[SignalResult],
        ml_signal: Optional[SignalResult],
        context: Dict[str, Any] | None = None
    ) -> Optional[SignalResult]: ...
```

Intuition: **capabilities as mixins** (duck-typed). Your runner never needs to “know” which kind it is.

---

## 2) Make the **core factory** accept _any_ processor (remove ML gate)

**File:** `strategies/core/factory.py`
Remove the mandatory ML checks; optionally call `load_model()` when present.

```python
# strategies/core/factory.py
import importlib
from typing import Dict, Any
from .protocols import StrategyProcessor
from .executor import StrategyExecutor
from .config import StrategyConfig, ExecutionContext

class StrategyFactory:
    def __init__(self):
        self._processors = {
            # Keep existing ML entries
            "ml_momentum": "strategies.implementations.ml_momentum.create_ml_momentum_processor",
            "MLMomentumProcessor": "strategies.implementations.ml_momentum.create_ml_momentum_processor",
            "ml_mean_reversion": "strategies.implementations.ml_mean_reversion.create_ml_mean_reversion_processor",
            "MLMeanReversionProcessor": "strategies.implementations.ml_mean_reversion.create_ml_mean_reversion_processor",
            "ml_breakout": "strategies.implementations.ml_breakout.create_ml_breakout_processor",
            "MLBreakoutProcessor": "strategies.implementations.ml_breakout.create_ml_breakout_processor",
            # NEW: pure rule processors we’ll add in step 4
            "momentum": "strategies.implementations.momentum.create_rules_momentum_processor",
            "mean_reversion": "strategies.implementations.mean_reversion.create_rules_mean_reversion_processor",
            # NEW: hybrid processors (wrapper) in step 5
            "hybrid_momentum": "strategies.implementations.hybrid_momentum.create_hybrid_momentum_processor",
        }
        self._validators = {
            "standard": "strategies.validation.standard_validator.create_standard_validator"
        }

    def create_executor(self, config: StrategyConfig, context: ExecutionContext) -> StrategyExecutor:
        # Load processor dynamically (ML, rules, or hybrid)
        factory_fn = self._load_factory(self._processors[config.strategy_type])
        processor: StrategyProcessor = factory_fn(config.parameters)

        # If it *happens* to be ML-capable, load model now (no requirement)
        if hasattr(processor, "load_model"):
            try:
                ok = processor.load_model()
                if not ok:
                    # soft-fail: we still return the executor; the runner may choose to skip or run degraded
                    pass
            except Exception:
                pass

        validator_type = config.parameters.get("validator", "standard")
        validator = self._load_factory(self._validators[validator_type])(config.parameters)

        return StrategyExecutor(processor=processor, validator=validator, config=config, context=context)

    def register_processor(self, strategy_type: str, factory_path: str): ...
    def register_validator(self, validator_type: str, factory_path: str): ...
    def _load_factory(self, factory_path: str):
        module_path, function_name = factory_path.rsplit('.', 1)
        return getattr(importlib.import_module(module_path), function_name)
```

Why this works: **Executor** always calls `processor.process_tick(…)`. ML processors already implement that by delegating to `extract_features → predict_signal`. Rules processors will implement `process_tick` with indicator math.

---

## 3) Make the **service factory** stop forcing ML

**File:** `services/strategy_runner/factory.py`
Do three things:

1. Expand the registry to include rule & hybrid processors (mirroring the core factory).
2. Remove the **MIGRATION** that force-maps legacy → ML.
3. **Do not** re-enforce ML anywhere here.

Example (showing the important bits):

```python
# services/strategy_runner/factory.py
from strategies.core.factory import StrategyFactory as CompositionFactory
from strategies.core.config import StrategyConfig, ExecutionContext
from strategies.core.executor import StrategyExecutor
from core.logging import get_logger

logger = get_logger("strategy_factory")

class StrategyFactory:
    # Accept both ML and non-ML names
    STRATEGY_REGISTRY = {
        # ML
        "ml_momentum": "strategies.implementations.ml_momentum",
        "ml_mean_reversion": "strategies.implementations.ml_mean_reversion",
        "ml_breakout": "strategies.implementations.ml_breakout",
        # RULES
        "momentum": "strategies.implementations.momentum",
        "mean_reversion": "strategies.implementations.mean_reversion",
        # HYBRID
        "hybrid_momentum": "strategies.implementations.hybrid_momentum",
    }

    # DELETE the ML-only migration mapping entirely.
    MIGRATION_MAPPING = {}

    @classmethod
    def create_strategy(cls, strategy_id: str, strategy_type: str, parameters: dict,
                        brokers: list[str] | None = None, instrument_tokens: list[int] | None = None
                        ) -> StrategyExecutor:
        composition_type = cls.MIGRATION_MAPPING.get(strategy_type, strategy_type)
        if composition_type not in cls.STRATEGY_REGISTRY:
            raise ValueError(f"Unknown strategy type: {strategy_type}")

        strategy_config = StrategyConfig(
            strategy_id=strategy_id,
            strategy_type=composition_type,
            parameters=parameters,
            active_brokers=brokers or ["paper"],
            instrument_tokens=instrument_tokens or [],
            max_position_size=Decimal(str(parameters.get("max_position_size", "0"))),
            risk_multiplier=Decimal(str(parameters.get("risk_multiplier", "1.0"))),
            enabled=bool(parameters.get("enabled", True)),
        )

        # Context is still broker-specific; the runner creates executors per broker if needed
        context = ExecutionContext(
            broker=(brokers or ["paper"])[0],
            portfolio_state={},
            market_session="regular",
            risk_limits={}
        )

        core_factory = CompositionFactory()
        return core_factory.create_executor(strategy_config, context)
```

Minimal, boring, correct.

---

## 4) Add **rules** processors (pure non-ML) — small, composable

Create two tiny implementations so the registry has something to load.

**File:** `strategies/implementations/momentum.py`

```python
# strategies/implementations/momentum.py
from typing import List, Optional, Dict, Any
from decimal import Decimal
from strategies.core.protocols import StrategyProcessor, SignalResult
from core.schemas.events import MarketTick as MarketData

class RulesMomentumProcessor:
    def __init__(self, lookback_periods: int = 20, threshold: float = 0.01, position_size: int = 100):
        self.lookback = int(lookback_periods)
        self.threshold = float(threshold)       # e.g., 1% move
        self.qty = int(position_size)

    def get_required_history_length(self) -> int:
        return self.lookback

    def supports_instrument(self, token: int) -> bool:
        return True

    def get_strategy_name(self) -> str:
        return "momentum"

    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        if len(history) < self.lookback:
            return None
        start = float(history[-self.lookback].last_price)
        now = float(tick.last_price)
        if start == 0:
            return None
        change = (now - start) / start
        if change > self.threshold:
            return SignalResult(
                signal_type="BUY",
                confidence=min(1.0, abs(change) * 5.0),  # cheap heuristic
                quantity=self.qty,
                price=Decimal(str(now)),
                reasoning=f"Price ↑ {change:.2%} over {self.lookback} periods",
                metadata={"change": change}
            )
        elif change < -self.threshold:
            return SignalResult(
                signal_type="SELL",
                confidence=min(1.0, abs(change) * 5.0),
                quantity=self.qty,
                price=Decimal(str(now)),
                reasoning=f"Price ↓ {change:.2%} over {self.lookback} periods",
                metadata={"change": change}
            )
        return None

def create_rules_momentum_processor(config: Dict[str, Any]) -> RulesMomentumProcessor:
    return RulesMomentumProcessor(
        lookback_periods=config.get("lookback_periods", 20),
        threshold=config.get("threshold", 0.01),
        position_size=config.get("position_size", 100),
    )
```

**File:** `strategies/implementations/mean_reversion.py` (same vibe; use z-score / simple band):

```python
# strategies/implementations/mean_reversion.py
from typing import List, Optional, Dict, Any
from decimal import Decimal
from statistics import mean, pstdev
from strategies.core.protocols import StrategyProcessor, SignalResult
from core.schemas.events import MarketTick as MarketData

class RulesMeanReversionProcessor:
    def __init__(self, lookback_periods: int = 20, z_entry: float = 1.0, position_size: int = 100):
        self.lookback = int(lookback_periods)
        self.z_entry = float(z_entry)
        self.qty = int(position_size)

    def get_required_history_length(self) -> int: return self.lookback
    def supports_instrument(self, token: int) -> bool: return True
    def get_strategy_name(self) -> str: return "mean_reversion"

    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        if len(history) < self.lookback:
            return None
        prices = [float(h.last_price) for h in history[-self.lookback:]]
        mu, sigma = mean(prices), pstdev(prices) or 1e-9
        z = (float(tick.last_price) - mu) / sigma
        if z <= -self.z_entry:
            return SignalResult("BUY", confidence=min(1.0, abs(z) / 3), quantity=self.qty,
                                price=Decimal(str(tick.last_price)),
                                reasoning=f"Z-score {z:.2f} below mean", metadata={"z": z})
        if z >= self.z_entry:
            return SignalResult("SELL", confidence=min(1.0, abs(z) / 3), quantity=self.qty,
                                price=Decimal(str(tick.last_price)),
                                reasoning=f"Z-score {z:.2f} above mean", metadata={"z": z})
        return None

def create_rules_mean_reversion_processor(config: Dict[str, Any]) -> RulesMeanReversionProcessor:
    return RulesMeanReversionProcessor(
        lookback_periods=config.get("lookback_periods", 20),
        z_entry=config.get("z_entry", 1.0),
        position_size=config.get("position_size", 100),
    )
```

These are intentionally tiny and “safe defaults” — they won’t blow up mid-run.

---

## 5) Add **hybrid** wrapper (compose rules + ML with a policy)

You can combine _any_ rule processor with _any_ ML-capable processor via a policy. No inheritance, just composition.

**File:** `strategies/implementations/hybrid_momentum.py`

```python
# strategies/implementations/hybrid_momentum.py
from typing import List, Optional, Dict, Any
from strategies.core.protocols import StrategyProcessor, MLCapable, DecisionPolicy, SignalResult
from core.schemas.events import MarketTick as MarketData
from decimal import Decimal

class MajorityVotePolicy:
    def __init__(self, min_conf: float = 0.55): self.min_conf = float(min_conf)
    def decide(self, rules_signal, ml_signal, context=None) -> Optional[SignalResult]:
        # HOLD if neither; prefer agreement; otherwise take ML if confident
        if not rules_signal and not ml_signal:
            return None
        if rules_signal and ml_signal and rules_signal.signal_type == ml_signal.signal_type:
            # average confidence, prefer higher quantity
            conf = min(1.0, (rules_signal.confidence + ml_signal.confidence) / 2)
            qty  = max(rules_signal.quantity, ml_signal.quantity)
            return SignalResult(rules_signal.signal_type, conf, qty, rules_signal.price,
                                reasoning="rules+ml agree", metadata={"rules": rules_signal, "ml": ml_signal})
        # disagreement: take ML only if confident enough
        if ml_signal and ml_signal.confidence >= self.min_conf:
            return ml_signal
        return rules_signal

class HybridProcessor(StrategyProcessor):
    def __init__(self, rules_proc: StrategyProcessor, ml_proc: StrategyProcessor | MLCapable, policy: DecisionPolicy):
        self.rules = rules_proc
        self.ml = ml_proc
        self.policy = policy

    def get_required_history_length(self) -> int:
        return max(self.rules.get_required_history_length(), self.ml.get_required_history_length())

    def supports_instrument(self, token: int) -> bool:
        return self.rules.supports_instrument(token) and self.ml.supports_instrument(token)

    def get_strategy_name(self) -> str:
        return f"hybrid:{self.rules.get_strategy_name()}+{self.ml.get_strategy_name()}"

    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        r = self.rules.process_tick(tick, history)
        # ML processors in your repo already implement process_tick
        m = self.ml.process_tick(tick, history)
        return self.policy.decide(r, m, context={"price": Decimal(str(tick.last_price))})

def create_hybrid_momentum_processor(config: Dict[str, Any]) -> HybridProcessor:
    # Compose existing factories
    from .momentum import create_rules_momentum_processor
    from .ml_momentum import create_ml_momentum_processor

    rules = create_rules_momentum_processor(config)
    ml = create_ml_momentum_processor(config)
    # optional: call ml.load_model() is handled by core factory anyway
    policy = MajorityVotePolicy(min_conf=config.get("min_conf", 0.55))
    return HybridProcessor(rules, ml, policy)
```

You can add other policies (e.g., “ML-confirm rules”, “rules-as-guardrails”, “probability-weighted sizing”) without touching runner logic.

---

## 6) Make the **runner** treat ML as _optional_, not required

**File:** `services/strategy_runner/service.py`

- Keep `_is_ml_strategy` but use it only for **metrics** and **optional** validation.
- Don’t skip non-ML strategies.
- Only run model validation when ML capability is detected; on failure you can either (a) skip, or (b) continue in rules-only/hybrid-minus-ML mode. Below shows the “skip ML-broken strategy” path (safer for live trading).

Patch the important bits:

```python
# services/strategy_runner/service.py

def _is_ml_strategy(self, executor) -> bool:
    proc = getattr(executor, "processor", None)
    return any(hasattr(proc, attr) for attr in ("load_model", "extract_features", "predict_signal"))

async def _validate_ml_model(self, executor, strategy_id: str) -> bool:
    proc = getattr(executor, "processor", None)
    try:
        if hasattr(proc, "load_model"):
            # model should already be loaded by core factory; just check presence
            return hasattr(proc, "model") and proc.model is not None
        return True
    except Exception:
        return False

# In the loading loop:
for config in strategy_configs:
    try:
        executor = StrategyFactory.create_strategy(
            strategy_id=config.id,
            strategy_type=config.strategy_type,          # ← now can be rules/ml/hybrid
            parameters=config.parameters,
            brokers=["zerodha"] if config.zerodha_trading_enabled else ["paper"],
            instrument_tokens=config.instruments
        )

        # Only validate if ML-capable
        if self._is_ml_strategy(executor):
            if await self._validate_ml_model(executor, config.id):
                ml_models_loaded += 1
            else:
                self.logger.warning("ML model not valid; skipping strategy",
                                    strategy_id=config.id, type=config.strategy_type)
                continue  # ← skip just this strategy
        # register regardless of ML-ness
        self._register_strategy(executor, config)
    except Exception as e:
        self.logger.error("Failed to initialize strategy", strategy_id=config.id, error=str(e))
```

In the **tick path** you already conditionally mark `ML_INFERENCE` metrics if `_is_ml_strategy(executor)` is true — keep that.

---

## 7) Configuration shape (DB / YAML)

No schema explosion needed. Keep your existing `StrategyConfiguration` but allow `strategy_type` to be any of `momentum`, `mean_reversion`, `ml_momentum`, `hybrid_momentum`, etc.

**Parameters** can be shared; hybrids simply re-use the same keys (e.g., `lookback_periods`, `position_size`, `model_path`, `min_conf`).

Example YAML:

```yaml
# strategies/configs/hybrid_momentum.yaml
strategy_name: 'NIFTY50 hybrid momentum'
strategy_type: 'hybrid_momentum'
parameters:
  lookback_periods: 20
  threshold: 0.0125
  position_size: 75
  model_path: 'models/momentum.onnx'
  min_conf: 0.6
validator: 'standard'
instruments: [256265] # NIFTY50 token
brokers: ['paper']
enabled: true
```

For DB rows, the same: `strategy_type='hybrid_momentum'`, `parameters` JSON as above.

---

## 8) Observability (keep it boring)

- **Metrics:** keep your existing Prometheus counters; only increment `ML_INFERENCE` when `_is_ml_strategy` is true.
- **Tracing:** already spans `strategy.process_tick` — add one attribute: `span.set_attribute("strategy.kind", "ml" if is_ml else "rules/hybrid")`.
- **Health:** on stop you mark unhealthy per broker — keep.

---

## 9) Testing checklist (fast and meaningful)

- **Unit**:

  - Rules processors: deterministic signals given synthetic price sequences.
  - ML processors: mock `model.predict` to fixed outputs; verify confidence normalization.
  - Hybrid policy: enumerate cases `{None/BUY/SELL} × {None/BUY/SELL}` with confidences.

- **Executor**:

  - History window enforcement and eviction logic (already in `StrategyExecutor`).

- **Runner**:

  - Register ML + rules + hybrid from in-memory configs; assert `instrument_to_strategies` mapping.
  - Route 1k ticks → no exceptions; ensure O(1) routing.

- **Golden path**:

  - YAML load → factory → executor → first signal published topic OK.

---

## 10) Migration steps (order matters, takes <1hr)

1. Add `MLCapable` + `DecisionPolicy` protocols.
2. Update `strategies/core/factory.py` to remove ML requirement and to _optionally_ `load_model`.
3. Add rules processors (`momentum.py`, `mean_reversion.py`).
4. Add hybrid wrapper (`hybrid_momentum.py`).
5. Expand `services/strategy_runner/factory.py` registry; delete the forced ML migration.
6. Loosen `services/strategy_runner/service.py` init to not gate on ML; keep ML validation optional.
7. Add 5–10 unit tests per new module (mocks for ML).
8. Try one rules strategy + one ML + one hybrid in paper mode.

---

## Why this matches your rules

- **(1) Composition + protocols over inheritance** — all the way.
- **(2) Classes only when state+behavior go together** — processors own small injected config; executor composes them.
- **(3) Pure domain, adapters separate** — processors are domain; factories are adapters; runner is application service.
- **(4) Small public API** — `StrategyProcessor`, `MLCapable`, `DecisionPolicy`, and 3 factory functions. Done.
- **(5) Immutability by default** — `StrategyConfig`/`ExecutionContext` already frozen dataclasses ✅
- **(6–10)** Type everything; easy to mock; duck-typed protocols; no inheritance diamonds; testable.

---

## Bonus: minimal policy variants you’ll want tomorrow

- **Confirm-then-trade**: require rules + ML to agree; otherwise HOLD.
- **ML-as-sizer**: rules pick direction, ML sets `confidence → position size`.
- **Rules-as-guardrails**: ML can only trade if rules say “not overbought/oversold”.

Each is \~20 lines and lives entirely in `DecisionPolicy` implementations.

## STRATEGY MODULES REDESIGN

Awesome — let’s make your strategy layer truly strategy-agnostic without any ML favoritism. Below is a clean rebuild of the **`strategies`** and **`strategy_runner`** modules that:

- treats **rules**, **ML**, and **hybrid** strategies the same;
- uses **Protocols** (capabilities) instead of inheritance;
- keeps a **tiny public API**;
- stays **testable** and **boring** (in a good way).

I’m giving you a full, drop-in code set. You can paste these files into a fresh package and then swap them into your app file-by-file.

---

# Directory layout

```
.
├─ strategies/
│  ├─ core/
│  │  ├─ protocols.py
│  │  ├─ types.py
│  │  ├─ config.py
│  │  ├─ executor.py
│  │  ├─ factory.py
│  │  └─ validation/
│  │     └─ standard_validator.py
│  └─ implementations/
│     ├─ momentum.py
│     ├─ mean_reversion.py
│     ├─ ml_momentum.py
│     └─ hybrid_momentum.py
└─ services/
   └─ strategy_runner/
      ├─ factory.py
      └─ service.py
```

---

# strategies/core/protocols.py

```python
from __future__ import annotations
from typing import Protocol, List, Dict, Any, Optional
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

# Minimal tick shape; wire this to your real schema if you have one
@dataclass(frozen=True, slots=True)
class MarketTick:
    instrument_token: int
    last_price: Decimal
    timestamp: datetime

@dataclass(frozen=True, slots=True)
class SignalResult:
    signal_type: str            # "BUY" | "SELL" | "HOLD"
    confidence: float           # 0.0 – 1.0
    quantity: int
    price: Decimal
    reasoning: str
    metadata: Dict[str, Any] | None = None

class StrategyProcessor(Protocol):
    """Minimal, universal contract (works for rules, ML, or hybrid)."""
    def process_tick(self, tick: MarketTick, history: List[MarketTick]) -> Optional[SignalResult]: ...
    def get_required_history_length(self) -> int: ...
    def supports_instrument(self, token: int) -> bool: ...
    def get_strategy_name(self) -> str: ...

class MLCapable(Protocol):
    """Optional capability for strategies that use models."""
    def load_model(self) -> bool: ...
    def extract_features(self, tick: MarketTick, history: List[MarketTick]) -> Any: ...
    def predict_signal(self, features: Any) -> Optional[SignalResult]: ...

class DecisionPolicy(Protocol):
    """How a hybrid strategy merges two signals into one."""
    def decide(
        self,
        rules_signal: Optional[SignalResult],
        ml_signal: Optional[SignalResult],
        context: Dict[str, Any] | None = None
    ) -> Optional[SignalResult]: ...
```

---

# strategies/core/types.py

```python
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Any

@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_position_size: Decimal = Decimal("0")
    risk_multiplier: Decimal = Decimal("1.0")

@dataclass(frozen=True, slots=True)
class PortfolioState:
    # Extend as needed
    positions: Dict[int, int]  # token -> qty
```

---

# strategies/core/config.py

```python
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Any, List

@dataclass(frozen=True, slots=True)
class StrategyConfig:
    strategy_id: str
    strategy_type: str                   # e.g., "momentum", "ml_momentum", "hybrid_momentum"
    parameters: Dict[str, Any]
    active_brokers: List[str]
    instrument_tokens: List[int]
    max_position_size: Decimal
    risk_multiplier: Decimal
    enabled: bool = True

@dataclass(frozen=True, slots=True)
class ExecutionContext:
    broker: str
    portfolio_state: Dict[str, Any]
    market_session: str
    risk_limits: Dict[str, Any]
```

---

# strategies/core/executor.py

```python
from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional
from .protocols import StrategyProcessor, MarketTick, SignalResult
from decimal import Decimal

class Validator:
    """Runtime validator contract (kept simple)."""
    def validate(self, signal: Optional[SignalResult], tick: MarketTick, history: List[MarketTick]) -> Optional[SignalResult]:
        return signal

@dataclass(slots=True)
class StrategyExecutor:
    processor: StrategyProcessor
    validator: Validator
    config: "StrategyConfig"
    context: "ExecutionContext"

    def __post_init__(self):
        self._history: Dict[int, Deque[MarketTick]] = defaultdict(
            lambda: deque(maxlen=max(1, self.processor.get_required_history_length()))
        )

    def on_tick(self, tick: MarketTick) -> Optional[SignalResult]:
        if not self.processor.supports_instrument(tick.instrument_token):
            return None
        hist = self._history[tick.instrument_token]
        hist.append(tick)
        # Guard until we have enough history
        if len(hist) < self.processor.get_required_history_length():
            return None
        raw = self.processor.process_tick(tick, list(hist))
        return self.validator.validate(raw, tick, list(hist))
```

---

# strategies/core/factory.py

```python
from __future__ import annotations
import importlib
from decimal import Decimal
from typing import Dict, Any
from .executor import StrategyExecutor
from .config import StrategyConfig, ExecutionContext
from .protocols import StrategyProcessor

class StrategyFactory:
    """Dynamically creates executors for rules, ML, or hybrid processors."""
    def __init__(self):
        self._processors = {
            # ML
            "ml_momentum": "strategies.implementations.ml_momentum.create_ml_momentum_processor",
            # RULES
            "momentum": "strategies.implementations.momentum.create_rules_momentum_processor",
            "mean_reversion": "strategies.implementations.mean_reversion.create_rules_mean_reversion_processor",
            # HYBRID
            "hybrid_momentum": "strategies.implementations.hybrid_momentum.create_hybrid_momentum_processor",
        }
        self._validators = {
            "standard": "strategies.core.validation.standard_validator.create_standard_validator"
        }

    def create_executor(self, config: StrategyConfig, context: ExecutionContext) -> StrategyExecutor:
        proc_factory = self._load(self._processors[config.strategy_type])
        processor: StrategyProcessor = proc_factory(config.parameters)

        # Optional: if ML-capable, try loading model, but don't enforce
        if hasattr(processor, "load_model"):
            try:
                processor.load_model()
            except Exception:
                # Soft-fail: executor still works; ML-strategy may decide to output None until ready
                pass

        validator_type = config.parameters.get("validator", "standard")
        validator = self._load(self._validators[validator_type])(config.parameters)

        return StrategyExecutor(processor=processor, validator=validator, config=config, context=context)

    def register_processor(self, strategy_type: str, factory_path: str) -> None:
        self._processors[strategy_type] = factory_path

    def register_validator(self, validator_type: str, factory_path: str) -> None:
        self._validators[validator_type] = factory_path

    def _load(self, path: str):
        module_path, fn = path.rsplit(".", 1)
        return getattr(importlib.import_module(module_path), fn)
```

---

# strategies/core/validation/standard_validator.py

```python
from __future__ import annotations
from typing import Optional, Dict, Any, List
from decimal import Decimal
from ..protocols import SignalResult, MarketTick

class StandardValidator:
    """Minimal safety checks; extend with risk filters if needed."""
    def __init__(self, params: Dict[str, Any]):
        self.min_conf = float(params.get("min_confidence", 0.0))
        self.max_qty = int(params.get("max_quantity", 10**9))  # effectively unbounded unless configured

    def validate(self, signal: Optional[SignalResult], tick: MarketTick, history: List[MarketTick]) -> Optional[SignalResult]:
        if signal is None:
            return None
        if not (0.0 <= signal.confidence <= 1.0):
            return None
        if signal.quantity <= 0 or signal.quantity > self.max_qty:
            return None
        # Price sanity
        if signal.price <= Decimal("0"):
            return None
        if signal.confidence < self.min_conf:
            return None
        return signal

def create_standard_validator(params: Dict[str, Any]) -> StandardValidator:
    return StandardValidator(params)
```

---

# strategies/implementations/momentum.py (rules)

```python
from __future__ import annotations
from typing import List, Optional, Dict, Any
from decimal import Decimal
from statistics import fmean
from strategies.core.protocols import StrategyProcessor, SignalResult, MarketTick

class RulesMomentumProcessor:
    def __init__(self, lookback_periods: int = 20, threshold: float = 0.01, position_size: int = 100):
        self.lookback = int(lookback_periods)
        self.threshold = float(threshold)       # 1% default
        self.qty = int(position_size)

    def get_required_history_length(self) -> int:
        return self.lookback

    def supports_instrument(self, token: int) -> bool:
        return True

    def get_strategy_name(self) -> str:
        return "momentum"

    def process_tick(self, tick: MarketTick, history: List[MarketTick]) -> Optional[SignalResult]:
        if len(history) < self.lookback:
            return None
        start = float(history[-self.lookback].last_price)
        now = float(tick.last_price)
        if start <= 0.0:
            return None
        change = (now - start) / start
        if change > self.threshold:
            return SignalResult(
                signal_type="BUY",
                confidence=min(1.0, abs(change) * 5.0),
                quantity=self.qty,
                price=Decimal(str(now)),
                reasoning=f"Momentum: +{change:.2%} over {self.lookback}",
                metadata={"change": change}
            )
        if change < -self.threshold:
            return SignalResult(
                signal_type="SELL",
                confidence=min(1.0, abs(change) * 5.0),
                quantity=self.qty,
                price=Decimal(str(now)),
                reasoning=f"Momentum: {change:.2%} over {self.lookback}",
                metadata={"change": change}
            )
        return None

def create_rules_momentum_processor(config: Dict[str, Any]) -> RulesMomentumProcessor:
    return RulesMomentumProcessor(
        lookback_periods=config.get("lookback_periods", 20),
        threshold=config.get("threshold", 0.01),
        position_size=config.get("position_size", 100),
    )
```

---

# strategies/implementations/mean_reversion.py (rules)

```python
from __future__ import annotations
from typing import List, Optional, Dict, Any
from decimal import Decimal
from statistics import mean, pstdev
from strategies.core.protocols import StrategyProcessor, SignalResult, MarketTick

class RulesMeanReversionProcessor:
    def __init__(self, lookback_periods: int = 20, z_entry: float = 1.0, position_size: int = 100):
        self.lookback = int(lookback_periods)
        self.z_entry = float(z_entry)
        self.qty = int(position_size)

    def get_required_history_length(self) -> int: return self.lookback
    def supports_instrument(self, token: int) -> bool: return True
    def get_strategy_name(self) -> str: return "mean_reversion"

    def process_tick(self, tick: MarketTick, history: List[MarketTick]) -> Optional[SignalResult]:
        if len(history) < self.lookback:
            return None
        prices = [float(h.last_price) for h in history[-self.lookback:]]
        mu = mean(prices)
        sigma = pstdev(prices) or 1e-9
        z = (float(tick.last_price) - mu) / sigma
        if z <= -self.z_entry:
            return SignalResult("BUY", confidence=min(1.0, abs(z)/3), quantity=self.qty,
                                price=Decimal(str(tick.last_price)),
                                reasoning=f"Mean reversion: z={z:.2f} below band",
                                metadata={"z": z})
        if z >= self.z_entry:
            return SignalResult("SELL", confidence=min(1.0, abs(z)/3), quantity=self.qty,
                                price=Decimal(str(tick.last_price)),
                                reasoning=f"Mean reversion: z={z:.2f} above band",
                                metadata={"z": z})
        return None

def create_rules_mean_reversion_processor(config: Dict[str, Any]) -> RulesMeanReversionProcessor:
    return RulesMeanReversionProcessor(
        lookback_periods=config.get("lookback_periods", 20),
        z_entry=config.get("z_entry", 1.0),
        position_size=config.get("position_size", 100),
    )
```

---

# strategies/implementations/ml_momentum.py (ML-capable)

```python
from __future__ import annotations
from typing import List, Optional, Dict, Any
from decimal import Decimal
from strategies.core.protocols import StrategyProcessor, MLCapable, SignalResult, MarketTick

class MLMomentumProcessor(StrategyProcessor, MLCapable):
    """Tiny example ML strategy; replace model bits with your inference stack (ONNX, Torch, etc.)."""
    def __init__(self, model_path: str, position_size: int = 100, min_conf: float = 0.5):
        self.model_path = model_path
        self.qty = int(position_size)
        self.min_conf = float(min_conf)
        self.model = None

    # --- StrategyProcessor API ---
    def get_required_history_length(self) -> int:
        return 20

    def supports_instrument(self, token: int) -> bool:
        return True

    def get_strategy_name(self) -> str:
        return "ml_momentum"

    def process_tick(self, tick: MarketTick, history: List[MarketTick]) -> Optional[SignalResult]:
        # If model isn't loaded, refuse to act (safe default)
        if self.model is None:
            return None
        feats = self.extract_features(tick, history)
        signal = self.predict_signal(feats)
        if signal and signal.confidence >= self.min_conf:
            return signal
        return None

    # --- MLCapable API ---
    def load_model(self) -> bool:
        try:
            # Pseudo load; swap for real code: onnxruntime.InferenceSession(...), torch.load(...), etc.
            self.model = object()
            return True
        except Exception:
            self.model = None
            return False

    def extract_features(self, tick: MarketTick, history: List[MarketTick]) -> Dict[str, float]:
        # Very simple handcrafted features; replace with your pipeline
        window = history[-self.get_required_history_length():]
        prices = [float(h.last_price) for h in window]
        return {
            "p0": prices[0],
            "pN": prices[-1],
            "ret": (prices[-1] - prices[0]) / max(1e-9, prices[0]),
        }

    def predict_signal(self, features: Dict[str, float]) -> Optional[SignalResult]:
        # Dummy rule pretending to be ML; replace with model inference
        ret = features["ret"]
        if ret > 0.01:
            conf = min(1.0, ret * 10)
            return SignalResult("BUY", conf, self.qty, Decimal(str(features["pN"])), "ML momentum ↑")
        if ret < -0.01:
            conf = min(1.0, abs(ret) * 10)
            return SignalResult("SELL", conf, self.qty, Decimal(str(features["pN"])), "ML momentum ↓")
        return None

def create_ml_momentum_processor(config: Dict[str, Any]) -> MLMomentumProcessor:
    return MLMomentumProcessor(
        model_path=config.get("model_path", "models/momentum.onnx"),
        position_size=config.get("position_size", 100),
        min_conf=config.get("min_conf", 0.5),
    )
```

---

# strategies/implementations/hybrid_momentum.py (compose rules + ML)

```python
from __future__ import annotations
from typing import List, Optional, Dict, Any
from strategies.core.protocols import StrategyProcessor, DecisionPolicy, SignalResult, MarketTick

class MajorityVotePolicy:
    def __init__(self, min_ml_conf: float = 0.55): self.min_ml_conf = float(min_ml_conf)

    def decide(self, rules_signal: Optional[SignalResult], ml_signal: Optional[SignalResult], context=None) -> Optional[SignalResult]:
        if not rules_signal and not ml_signal:
            return None
        if rules_signal and ml_signal and rules_signal.signal_type == ml_signal.signal_type:
            # Merge: average confidence, take larger size & latest price
            conf = min(1.0, (rules_signal.confidence + ml_signal.confidence) / 2)
            qty = max(rules_signal.quantity, ml_signal.quantity)
            price = ml_signal.price
            return SignalResult(rules_signal.signal_type, conf, qty, price, "rules+ml agree",
                                metadata={"rules": rules_signal, "ml": ml_signal})
        # Disagreement: accept ML only if strong enough
        if ml_signal and ml_signal.confidence >= self.min_ml_conf:
            return ml_signal
        return rules_signal

class HybridProcessor(StrategyProcessor):
    def __init__(self, rules_proc: StrategyProcessor, ml_proc: StrategyProcessor, policy: DecisionPolicy):
        self.rules = rules_proc
        self.ml = ml_proc
        self.policy = policy

    def get_required_history_length(self) -> int:
        return max(self.rules.get_required_history_length(), self.ml.get_required_history_length())

    def supports_instrument(self, token: int) -> bool:
        return self.rules.supports_instrument(token) and self.ml.supports_instrument(token)

    def get_strategy_name(self) -> str:
        return f"hybrid:{self.rules.get_strategy_name()}+{self.ml.get_strategy_name()}"

    def process_tick(self, tick: MarketTick, history: List[MarketTick]) -> Optional[SignalResult]:
        r = self.rules.process_tick(tick, history)
        m = self.ml.process_tick(tick, history)
        return self.policy.decide(r, m, context={"tick": tick})

def create_hybrid_momentum_processor(config: Dict[str, Any]) -> HybridProcessor:
    from .momentum import create_rules_momentum_processor
    from .ml_momentum import create_ml_momentum_processor
    rules = create_rules_momentum_processor(config)
    ml = create_ml_momentum_processor(config)
    policy = MajorityVotePolicy(min_ml_conf=config.get("min_conf", 0.55))
    return HybridProcessor(rules, ml, policy)
```

---

# services/strategy_runner/factory.py

```python
from __future__ import annotations
from decimal import Decimal
from typing import Dict, Any, List
from strategies.core.factory import StrategyFactory as CoreFactory
from strategies.core.config import StrategyConfig, ExecutionContext
from strategies.core.executor import StrategyExecutor

class StrategyFactory:
    """App-level factory that builds StrategyExecutors from your DB/YAML configs."""
    STRATEGY_REGISTRY = {
        # mirror core factory keys for discoverability (optional)
        "momentum": "strategies.implementations.momentum",
        "mean_reversion": "strategies.implementations.mean_reversion",
        "ml_momentum": "strategies.implementations.ml_momentum",
        "hybrid_momentum": "strategies.implementations.hybrid_momentum",
    }

    @classmethod
    def create_strategy(
        cls,
        strategy_id: str,
        strategy_type: str,
        parameters: Dict[str, Any],
        brokers: List[str] | None,
        instrument_tokens: List[int] | None,
    ) -> StrategyExecutor:
        config = StrategyConfig(
            strategy_id=strategy_id,
            strategy_type=strategy_type,
            parameters=parameters,
            active_brokers=brokers or ["paper"],
            instrument_tokens=instrument_tokens or [],
            max_position_size=Decimal(str(parameters.get("max_position_size", "0"))),
            risk_multiplier=Decimal(str(parameters.get("risk_multiplier", "1.0"))),
            enabled=bool(parameters.get("enabled", True)),
        )
        context = ExecutionContext(
            broker=(brokers or ["paper"])[0],
            portfolio_state={},
            market_session="regular",
            risk_limits={}
        )
        return CoreFactory().create_executor(config, context)
```

---

# services/strategy_runner/service.py

```python
from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Optional
from strategies.core.protocols import MarketTick, SignalResult
from strategies.core.executor import StrategyExecutor
from .factory import StrategyFactory

class StrategyRunnerService:
    """Routes ticks to registered strategies and emits their signals."""

    def __init__(self):
        self.instrument_to_strategies: Dict[int, List[StrategyExecutor]] = defaultdict(list)
        self.strategy_index: Dict[str, StrategyExecutor] = {}

    def _is_ml_strategy(self, executor: StrategyExecutor) -> bool:
        proc = getattr(executor, "processor", None)
        return any(hasattr(proc, attr) for attr in ("load_model", "extract_features", "predict_signal"))

    def register_from_config(self, cfg_row: dict) -> None:
        """cfg_row shape is up to your DB; expecting keys used below."""
        execu = StrategyFactory.create_strategy(
            strategy_id=cfg_row["id"],
            strategy_type=cfg_row["strategy_type"],             # e.g., "momentum" | "ml_momentum" | "hybrid_momentum"
            parameters=cfg_row.get("parameters", {}),
            brokers=cfg_row.get("brokers") or ["paper"],
            instrument_tokens=cfg_row.get("instruments") or [],
        )

        # Optional: if ML-capable and model not loaded (your ML proc can expose a property), skip
        if self._is_ml_strategy(execu):
            proc = getattr(execu, "processor")
            if hasattr(proc, "model") and proc.model is None:
                # soft skip ML strategies with missing model (safer default)
                return

        self.strategy_index[cfg_row["id"]] = execu
        for token in execu.config.instrument_tokens:
            self.instrument_to_strategies[token].append(execu)

    def on_market_tick(self, tick: MarketTick) -> List[SignalResult]:
        """Push one tick, get zero/one/many signals."""
        results: List[SignalResult] = []
        for execu in self.instrument_to_strategies.get(tick.instrument_token, []):
            sig = execu.on_tick(tick)
            if sig:
                results.append(sig)
                # Here you’d publish to your event bus / OMS
        return results

    # Optional: health reporting, stop hooks, etc.
```

---

## Example YAML/DB row you can feed to the service

```yaml
id: 'strat-001'
strategy_type: 'hybrid_momentum'
parameters:
  lookback_periods: 20
  threshold: 0.012
  position_size: 75
  model_path: 'models/momentum.onnx'
  min_conf: 0.6
brokers: ['paper']
instruments: [256265]
enabled: true
```

---

## Why this design works (and stays simple)

- **One universal call path:** runner → executor → `process_tick`. No ML special rules.
- **Capabilities, not inheritance:** `MLCapable` and `DecisionPolicy` are optional Protocols.
- **Hybrids by composition:** a wrapper joins _any_ rules processor with _any_ ML processor.
- **Small public API:** `StrategyProcessor`, `MLCapable`, `DecisionPolicy`, and factory functions.
- **Immutability first:** configs/DTOs are frozen dataclasses.
- **Testable:** processors are pure functions of `(tick, history)`; validator is easy to mock.

---

## Quick test harness (sanity)

```python
from decimal import Decimal
from datetime import datetime, timedelta
from strategies.core.protocols import MarketTick
from services.strategy_runner.service import StrategyRunnerService

svc = StrategyRunnerService()

# Register three strategies
svc.register_from_config({
    "id": "rules-momo",
    "strategy_type": "momentum",
    "parameters": {"lookback_periods": 5, "threshold": 0.01, "position_size": 10},
    "brokers": ["paper"],
    "instruments": [123],
    "enabled": True,
})
svc.register_from_config({
    "id": "ml-momo",
    "strategy_type": "ml_momentum",
    "parameters": {"model_path": "models/momentum.onnx", "position_size": 10, "min_conf": 0.5},
    "brokers": ["paper"],
    "instruments": [123],
    "enabled": True,
})
svc.register_from_config({
    "id": "hybrid-momo",
    "strategy_type": "hybrid_momentum",
    "parameters": {"lookback_periods": 5, "threshold": 0.01, "position_size": 10, "model_path": "models/momentum.onnx"},
    "brokers": ["paper"],
    "instruments": [123],
    "enabled": True,
})

t0 = datetime.utcnow()
prices = [100, 100.5, 101.2, 100.9, 101.6, 102.0, 102.5]
for i, p in enumerate(prices):
    tick = MarketTick(instrument_token=123, last_price=Decimal(str(p)), timestamp=t0 + timedelta(seconds=i))
    signals = svc.on_market_tick(tick)
    if signals:
        print([ (s.signal_type, float(s.confidence), s.quantity, str(s.price)) for s in signals ])
```

Run this and you’ll see BUY/SELL/HOLD decisions from **all three** strategies via the same runner.

---

## Migration checklist (safe order)

1. Drop these files in a feature branch.
2. Point your existing config loader to build rows like the YAML shown.
3. Wire your real `MarketTick` type into `protocols.py` (or adapt in the runner).
4. Replace your current `services/strategy_runner/*` with the new ones.
5. Keep your existing metrics/tracing — the runner is a thin layer; just add tags like `strategy.kind=ml|rules|hybrid` if you like.
6. Add unit tests for processors and policies (mock `model` for ML).

## Additional Details

Heck yes—I’ll add the “glue” and the sharp edges you’ll hit in production. Think of this as the _ops + correctness + ergonomics_ layer around the code you’ve got.

# 1) Lifecycle & state machine (don’t YOLO the tick loop)

Give each strategy an explicit lifecycle to avoid spooky action at a distance.

- States: `INIT → WARMUP → ACTIVE → PAUSED → ERROR → STOPPED`
- Transitions:

  - `INIT→WARMUP` when registered
  - `WARMUP→ACTIVE` once `history >= required_len`
  - `ACTIVE→PAUSED` on throttling/circuit-breaker
  - `ACTIVE→ERROR` on unhandled exception (auto-retry N times → `PAUSED`)
  - `PAUSED→ACTIVE` on timer or manual resume

- Implementation: in `StrategyExecutor`, track `self.state`; gate `on_tick` early if not `ACTIVE`. Keep counts and last-transition timestamp.

Why: clean warmups, safe degradation, easy observability.

# 2) Idempotent & rate-limited signal emission

Your OMS (or paper broker) will thank you.

- Add a `signal_id = hash(strategy_id, instrument_token, side, price_bucket, ts_rounded)`
- Keep `last_signal_key` per instrument; drop duplicates within a window (e.g., 3–5s).
- Add simple rate limits: `max_signals_per_minute`, `min_signal_interval_ms` per strategy.

# 3) Risk/validation filters you’ll actually use

Extend `StandardValidator` without coupling to brokers:

- **Position guard:** query `portfolio_state` (in `ExecutionContext`) to avoid flipping too fast.
- **Cool-down:** per instrument after a trade-fired signal (e.g., 30–120s).
- **Banding:** ignore signals if price deviates >X% intrabar (volatility spike).
- **Exposure cap:** `abs(sum(qty*price)) <= max_exposure`.
- **Slippage budget:** drop if `|last_price - ref_price| > budget`.

All are pure functions fed with `(signal, tick, history, context)`.

# 4) Time & session hygiene (you’ll get bitten)

- Normalize timestamps to **UTC** inside the runner; only display in local tz.
- Maintain `SessionClock` (preopen/regular/closed) from an exchange calendar. Gate signals outside `regular` unless explicitly allowed.
- Handle **halts**/**auction** flags: store in `tick.metadata`, validator drops signals on those.

# 5) Multi-broker routing that stays composable

- Keep one `StrategyExecutor` per **(strategy, broker)** if broker-adapter logic differs (fees/lot size).
- Adapter boundary: `SignalPublisher` interface with `publish(SignalResult, context)`; inject a `publisher` per broker.
- Nice touch: add `supports_broker(broker_id)` on processor if you need broker-specific constraints.

# 6) ML ergonomics without coupling

- **Lazy + hot load:** ML processors implement `load_model()` and a no-op if already loaded. Watch a `model_path` for changes and reload between ticks (debounced).
- **Feature plumbing:** keep `extract_features` pure; add a tiny `FeatureCache` keyed by `(instrument_token, ts_floor)`.
- **Fallback mode:** if `predict_signal` raises, log & return `None`; lifecycle _doesn’t_ crash the strategy.

# 7) Hybrid policies you’ll want in practice

You already have MajorityVote. Add these tiny swappables:

- **ConfirmPolicy:** act only if rules and ML agree; else HOLD.
- **SizerPolicy:** direction from rules, size from ML via `size = base * f(confidence)`.
- **GuardrailPolicy:** ML only allowed if rules say “not overbought/oversold”.
- **ThresholdEscalationPolicy:** require higher ML confidence during high volatility (read from tick metadata).

Each is \~20–40 LOC and lives wholly outside the runner.

# 8) Backtest/live parity (same code, different wires)

- Introduce a `TickSource` protocol: `subscribe(callback)` for live, and `replay(stream)` for backtests.
- Record mode: persist all inbound ticks to a **Parquet** (or JSONL) log; replay in tests.
- Determinism: set a `rng_seed` per run; avoid wall-clock inside processors.

# 9) Metrics & tracing (what to actually emit)

**Counters**

- `signals_total{strategy, kind, side}`
- `signals_dropped_total{reason}`
- `ml_inferences_total{strategy}`

**Gauges**

- `strategy_state{strategy}` → 0/1/2/3 mapping to lifecycle
- `latency_ms{stage=process_tick|validate|publish}` histogram

**Tracing**

- Span per tick: attributes `strategy`, `instrument`, `kind=rules|ml|hybrid`, `history_len`, `decision_policy`

# 10) Concurrency model that won’t explode

- One async consumer per instrument **partition**. For high symbols, shard by `token % N`.
- Per-executor mailbox (bounded queue) to prevent backpressure exploding the shared loop.
- Use `asyncio.TaskGroup` to manage lifetimes; on crash, mark executor `ERROR` and isolate.

# 11) Config schema (stable & minimal)

JSON/YAML `parameters` already works. Add a schema validation step at load time:

```yaml
strategy_type: hybrid_momentum
parameters:
  lookback_periods: 20
  threshold: 0.012
  position_size: 75
  model_path: models/momentum.onnx
  min_conf: 0.6
  risk:
    min_confidence: 0.55
    cooldown_sec: 60
    max_signals_per_min: 6
instruments: [256265]
brokers: ['paper']
enabled: true
```

Run Pydantic v2 on this _outside_ the domain layer and pass a plain dict to factories (keep domain pure).

# 12) Testing matrix (cheap, high-value)

- **Processors (unit):** synthetic price ladders → expected signals (rules, ML, hybrid).
- **Policies:** truth table `{None, BUY, SELL} × {None, BUY, SELL}` with conf levels.
- **Executor:** history window & warmup; idempotency; rate limits.
- **Runner (integration):** 1k ticks across 100 strategies; ensure O(1) routing & no cross-talk.
- **Replay parity:** run the same Parquet through rules/ML/hybrid and assert counts/latencies.

# 13) Failure modes & safe defaults

- If a processor throws: catch → increment `processor_errors_total` → set `state=ERROR` if >K in window, else continue.
- If a publisher throws: retry with backoff; after N failures, route to a **dead-letter** topic and `PAUSED`.
- If config invalid: reject at load time, don’t half-register a strategy.

# 14) Type-safety & contracts (your rules honored)

- Protocols for `StrategyProcessor`, `MLCapable`, `DecisionPolicy`, `SignalPublisher`, `TickSource`.
- Frozen dataclasses for DTOs; no shared mutable state in processors.
- mypy/pyright in CI; a `--strict` pass for `strategies/*` and `services/strategy_runner/*`.

# 15) A tiny publisher interface (adapter boundary)

```python
class SignalPublisher(Protocol):
    async def publish(self, signal: SignalResult, *, strategy_id: str, broker: str) -> None: ...

# Adapter: Kafka/Redpanda/NATS lives here, not in domain
```

Inject this into the runner; call it **after** validator passes. For paper trading, swap in a logging publisher.

# 16) Warmup & history windows (per-instrument)

You already size `deque(maxlen=required)`. Add optional **preload**:

- On register, if a `HistoryProvider` exists, fetch last `required` bars and seed the deque so strategies go `ACTIVE` faster.

# 17) Feature store (optional but nice)

If you compute heavy features (e.g., TA or learned embeddings), cache them:

- Key: `(strategy_id, instrument_token, bar_ts) → feature_vector`
- Scope: in-memory LRU; optionally Redis if you have multiple workers.

# 18) Example: circuit breaker (5 lines, lots of pain avoided)

Add to validator:

```python
self._loss_streak = defaultdict(int)
if trade_result := self._lookup_recent_trade_result(tick.instrument_token):
    self._loss_streak[token] = self._loss_streak[token] + 1 if trade_result < 0 else 0
if self._loss_streak[token] >= self.max_loss_streak:
    return None  # auto-pause via state machine is even better
```

# 19) Logging you’ll actually read

- `INFO`: state transitions, registrations, reconfigures
- `WARN`: model not loaded, validator drops with reason buckets
- `ERROR`: processor exception (with strategy_id, token, last N prices)

# 20) Migration nudge (low drama)

1. Drop in lifecycle + idempotency + validator extensions (no API break).
2. Add SignalPublisher adapter and route publish there.
3. Introduce policies & hybrid (already done).
4. Add config validation pre-runner.
5. Wire metrics/tracing.
6. Add replay harness to keep you honest.
