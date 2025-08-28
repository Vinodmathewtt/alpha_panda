# Python Development Policies

This document provides comprehensive Python development policies for the Alpha Panda trading system, emphasizing composition-first object-oriented programming principles.

## 0) North Star

- **Prefer composition + protocols over inheritance**
- **Small, explicit objects; clear boundaries; minimal magic**
- **Runtime duck typing; optional static checks (mypy/pyright)**

---

## 1) Class Creation Guidelines

### When to Create a Class

Use a class when you need **state + behavior** that evolves over time.

**Alternatives:**
- Use **functions or modules** for stateless utilities
- Use **dataclasses/attrs** for simple data carriers with light methods

**Example:**

```python
@dataclass(slots=True, frozen=False)
class Order:
    id: str
    qty: int
    price: float

    def value(self) -> float:
        return self.qty * self.price
```

---

## 2) Inheritance Policy

- **Default: No inheritance**
- Allowed only for:
  1. **Framework adapters** (e.g., ABCs required by a library)
  2. **Stable, proven hierarchies** (e.g., Exception subclasses)
  3. **Mixins** that are truly stateless and tiny

- If used, **one level max** (no deep trees), and mark overrides with `@override`

---

## 3) Interfaces & Polymorphism

Express contracts with **`typing.Protocol`** (structural interfaces). Prefer **duck typing** at runtime; rely on **type checks in CI**.

```python
from typing import Protocol

class Logger(Protocol):
    def log(self, msg: str) -> None: ...

class ConsoleLogger:
    def log(self, msg: str) -> None: 
        print(msg)

def run(job: str, logger: Logger) -> None:
    logger.log(f"start {job}")
```

---

## 4) Composition & Delegation

- Objects **have** collaborators; they don't inherit them
- Pass dependencies via **constructor injection**; default to **protocol-typed** params
- Provide **factories** for common wiring; avoid global singletons

```python
class Engine(Protocol):
    def start(self) -> None: ...

class Car:
    def __init__(self, engine: Engine): 
        self._engine = engine
        
    def drive(self) -> None:
        self._engine.start()
```

---

## 5) Data Modeling

- Use `@dataclass(slots=True)` (or `attrs`) for domain models
- Keep models **immutable where reasonable** (`frozen=True` for value objects)
- Add **pure methods** for domain logic; avoid "anemic" models that only store data

**Example:**

```python
@dataclass(slots=True, frozen=True)
class MarketTick:
    symbol: str
    price: float
    volume: int
    timestamp: datetime

    def is_significant_volume(self, threshold: int = 1000) -> bool:
        return self.volume >= threshold
```

---

## 6) Error Handling

- Use **exceptions** for truly exceptional conditions
- Make custom exceptions **flat**: `DomainError -> SpecificError`
- For predictable branches, return results (`Ok/Err` pattern or `(value, error)` tuple) in **core** logic and convert to exceptions at **API boundaries**

```python
class TradingError(Exception):
    """Base trading system error"""
    pass

class InsufficientFundsError(TradingError):
    """Raised when account has insufficient funds for order"""
    pass

# Result pattern for core logic
def calculate_position_size(account_balance: float, risk_percent: float) -> tuple[float, str | None]:
    if account_balance <= 0:
        return 0.0, "Account balance must be positive"
    return account_balance * (risk_percent / 100), None
```

---

## 7) Public API Surface

- Keep classes **small** (≤ ~7 public methods)
- Public methods should be **verbs** and **side-effect clear**
- Hide internals with `_private` methods/attrs; no "smart" metaclass magic

---

## 8) Mutability Rules

- Prefer **immutable value types**; mutate **aggregates** in well-defined methods
- Never expose internal mutable collections directly; provide **iterators/copies**

```python
@dataclass(slots=True)
class Portfolio:
    _positions: dict[str, Position] = field(default_factory=dict, init=False)

    def positions(self) -> Iterator[Position]:
        """Return iterator over positions (safe access)"""
        return iter(self._positions.values())

    def add_position(self, position: Position) -> None:
        """Well-defined mutation method"""
        self._positions[position.symbol] = position
```

---

## 9) Async Compatibility

- Keep I/O at the edges; core domain stays **sync and pure** where possible
- Provide both sync/async adapters when needed (e.g., `Repo` + `AsyncRepo` protocols)

```python
class OrderRepository(Protocol):
    def save(self, order: Order) -> None: ...
    def get_by_id(self, order_id: str) -> Order | None: ...

class AsyncOrderRepository(Protocol):
    async def save(self, order: Order) -> None: ...
    async def get_by_id(self, order_id: str) -> Order | None: ...
```

---

## 10) Extensibility (Open/Closed Principle)

Prefer **plug-points**:
- Strategy objects (via Protocols)
- Event hooks/callback registries  
- `functools.singledispatch` for open extension of functions

Avoid modifying core classes for each new case; **compose new behavior**.

```python
from functools import singledispatch

@singledispatch
def calculate_commission(order_type) -> float:
    raise NotImplementedError(f"Commission calculation not implemented for {type(order_type)}")

@calculate_commission.register
def _(order: MarketOrder) -> float:
    return order.value * 0.001

@calculate_commission.register  
def _(order: LimitOrder) -> float:
    return max(order.value * 0.001, 1.0)
```

---

## 11) Factories & Builders

- Use **module-level factory functions** for simple assembly
- Use **Builder** only when object construction needs staged validation or many optional parts
- Keep DI **explicit**; no global "service locators"

```python
# Simple factory
def create_trading_engine(config: TradingConfig) -> TradingEngine:
    broker = create_broker(config.broker_type)
    risk_manager = RiskManager(config.max_position_size)
    return TradingEngine(broker=broker, risk_manager=risk_manager)

# Builder for complex construction
class StrategyBuilder:
    def __init__(self) -> None:
        self._indicators: list[Indicator] = []
        self._rules: list[Rule] = []

    def add_indicator(self, indicator: Indicator) -> Self:
        self._indicators.append(indicator)
        return self

    def add_rule(self, rule: Rule) -> Self:
        self._rules.append(rule)
        return self

    def build(self) -> Strategy:
        if not self._indicators:
            raise ValueError("Strategy must have at least one indicator")
        return Strategy(indicators=self._indicators, rules=self._rules)
```

---

## 12) Boundaries & Anti-Coupling

Separate:
- **Domain** (pure logic)
- **Adapters** (DB, HTTP, MQ)
- **Application** (use-cases/orchestration)

Domain must not import adapters. Adapters depend on domain **only**.

```
# Good architecture
domain/
  models.py      # Order, Position, etc.
  protocols.py   # OrderRepository, PriceFeed protocols
  services.py    # Pure business logic

adapters/
  database.py    # PostgreSQL implementation of OrderRepository
  brokers.py     # Zerodha implementation of PriceFeed
  
application/
  use_cases.py   # Orchestration logic
```

---

## 13) Logging & Observability

- Inject a `Logger` protocol; **no direct `print`** or global loggers in domain
- Business methods should log **intent + key IDs**, not internal noise

```python
class Logger(Protocol):
    def info(self, msg: str, **kwargs) -> None: ...
    def error(self, msg: str, **kwargs) -> None: ...

class OrderService:
    def __init__(self, repository: OrderRepository, logger: Logger):
        self._repo = repository
        self._log = logger

    def place_order(self, order: Order) -> None:
        self._log.info("Placing order", order_id=order.id, symbol=order.symbol)
        self._repo.save(order)
        self._log.info("Order placed successfully", order_id=order.id)
```

---

## 14) Naming & Documentation

- Class names are **nouns**; methods are **imperative verbs**
- Docstrings: 1-line summary + args/returns for public APIs
- No abbreviations in public symbols unless industry-standard

```python
class TradingSignal:  # Noun
    """Represents a trading signal generated by a strategy."""
    
    def execute_trade(self) -> None:  # Imperative verb
        """Execute the trade based on this signal."""
        pass
```

---

## 15) Testing Contract-First

- Unit tests target **protocol contracts** and public methods
- Use **fakes** implementing protocols; avoid heavy mocks tied to concrete classes
- Each class should be testable with **in-memory collaborators**

```python
class FakeOrderRepository:
    """Fake implementation for testing"""
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def save(self, order: Order) -> None:
        self._orders[order.id] = order

    def get_by_id(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

def test_order_service_places_order():
    # Arrange
    repo = FakeOrderRepository()
    logger = FakeLogger()
    service = OrderService(repo, logger)
    order = Order(id="123", symbol="AAPL", qty=100, price=150.0)
    
    # Act
    service.place_order(order)
    
    # Assert
    saved_order = repo.get_by_id("123")
    assert saved_order == order
```

---

## 16) Pattern Usage (80/20)

- **Yes**: Strategy, Adapter, Facade, Repository, Builder (sparingly), Observer/Events
- **Careful**: Singleton (prefer factories), Template Method (prefer Strategy)
- **Avoid**: Deep inheritance trees, God objects, magic metaclasses, implicit globals

---

## 17) Type Hints & Safety

- All public APIs must be **fully typed** (incl. `Self`, generics where useful)
- Run **mypy/pyright in CI**; treat errors as failures
- Use `@final`, `@override` to stabilize APIs when inheritance is used

```python
from typing import Self, Protocol, TypeVar, Generic

T = TypeVar('T')

class Repository(Protocol, Generic[T]):
    def save(self, entity: T) -> None: ...
    def get_by_id(self, id: str) -> T | None: ...

@final
class Order:
    def __init__(self, id: str, symbol: str, qty: int) -> None:
        self.id = id
        self.symbol = symbol  
        self.qty = qty

    def with_price(self, price: float) -> Self:
        """Return new Order with price set"""
        return Order(self.id, self.symbol, self.qty, price)
```

---

## 18) Performance & Footguns

- Prefer **simple Python** over cleverness; measure before optimizing
- Keep hot paths **function-level** or **dataclass methods**; avoid dynamic attribute tricks
- Use `slots=True` for data-heavy classes; avoid per-instance `__dict__` bloat

---

## 19) Exceptions & Control Flow

- Never use exceptions for ordinary branching
- Convert external errors (DB, HTTP) into **domain errors** at boundaries

```python
# Good: External error converted to domain error
class BrokerAdapter:
    def place_order(self, order: Order) -> None:
        try:
            response = self._api_client.place_order(order.to_api_format())
        except APIConnectionError as e:
            raise TradingSystemError(f"Failed to place order {order.id}: {e}") from e
```

---

## 20) File & Class Size Limits

- ~300–500 lines per module, ~150–200 lines per class as soft guidance
- If a class grows, **split responsibilities** (SRP) and compose

---

## Complete Example: Trading System Components

### Domain Contracts

```python
# domain/contracts.py
from typing import Protocol
from datetime import datetime

class PriceFeed(Protocol):
    async def get_current_price(self, symbol: str) -> float: ...

class OrderRepository(Protocol):
    async def save(self, order: Order) -> None: ...
    async def get_by_id(self, order_id: str) -> Order | None: ...

class Logger(Protocol):
    def info(self, msg: str, **kwargs) -> None: ...
```

### Domain Models

```python
# domain/models.py  
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"

@dataclass(slots=True)
class Order:
    id: str
    symbol: str
    qty: int
    price: float | None = None
    status: OrderStatus = field(default=OrderStatus.PENDING)
    created_at: datetime = field(default_factory=datetime.now)

    def is_priced(self) -> bool:
        return self.price is not None

    def total_value(self) -> float:
        if not self.is_priced():
            raise ValueError("Cannot calculate value for unpriced order")
        return self.qty * self.price
```

### Application Service

```python
# application/order_service.py
from ..domain.contracts import PriceFeed, OrderRepository, Logger
from ..domain.models import Order, OrderStatus

class OrderService:
    def __init__(self, 
                 price_feed: PriceFeed, 
                 repository: OrderRepository, 
                 logger: Logger) -> None:
        self._feed = price_feed
        self._repo = repository
        self._log = logger

    async def place_market_order(self, order: Order) -> Order:
        """Place a market order with current price"""
        if not order.is_priced():
            current_price = await self._feed.get_current_price(order.symbol)
            order.price = current_price
        
        await self._repo.save(order)
        
        self._log.info(
            "Market order placed", 
            order_id=order.id, 
            symbol=order.symbol, 
            price=order.price,
            total_value=order.total_value()
        )
        
        return order
```

### Adapters

```python
# adapters/zerodha_feed.py
from ..domain.contracts import PriceFeed

class ZerodhaFeed:
    def __init__(self, api_client) -> None:
        self._client = api_client

    async def get_current_price(self, symbol: str) -> float:
        """Implement PriceFeed protocol using Zerodha API"""
        quotes = await self._client.quote(symbol)
        return quotes[symbol]['last_price']

# adapters/postgres_repository.py  
from ..domain.contracts import OrderRepository
from ..domain.models import Order

class PostgresOrderRepository:
    def __init__(self, db_session) -> None:
        self._session = db_session

    async def save(self, order: Order) -> None:
        """Implement OrderRepository protocol using PostgreSQL"""
        # Database persistence logic
        pass

    async def get_by_id(self, order_id: str) -> Order | None:
        """Retrieve order from PostgreSQL"""
        # Database retrieval logic
        pass
```

---

## Guardrails & Quick Checklist

### Development Guardrails
- **Do** propose **composition** with protocol-typed dependencies
- **Do** add/keep **type hints**, `slots=True`, and concise docstrings
- **Do** introduce **strategies/adapters** instead of subclassing
- **Don't** add inheritance unless policy's exceptions apply; if so, use `@override`
- **Don't** introduce globals/singletons; wire via factories/constructors
- **Don't** expand a class beyond a single responsibility

### Quick Checklist (for PR reviews)
- [ ] No inheritance (or justified per §2 with `@override`)
- [ ] Dependencies injected, typed by Protocols
- [ ] Dataclasses/attrs for models; immutability where reasonable
- [ ] Public API small, well-named, fully typed
- [ ] Domain free of framework/adapter imports
- [ ] Tests target contracts; fakes over mocks
- [ ] Logs intent, not internals
- [ ] No clever metaclass/magic; simple, readable Python
- [ ] No shared mutable state without a guard; prefer queues/events
- [ ] No floats in prices/P&L; `Decimal` only; quantize before persistence or logging
- [ ] All state changes come from events; no 'naked' mutations
- [ ] Persist with optimistic concurrency; publish via Outbox
- [ ] Events are idempotent and backward-compatible

---

## 21) Concurrency & Shared State (Trading Systems)

**Policy**: Domain objects remain **single-threaded & mutable only via methods**. Concurrency is handled at boundaries (queues, async tasks, worker processes).

- Prefer **message passing** (event bus, queues) over shared mutation
- If you must share, **wrap with locks** and expose **methods**, not raw dicts
- Provide both **threaded** and **async** coordination patterns

```python
# Threaded guard (only in adapters/application; keep domain pure)
import threading
from typing import Protocol

class Positions(Protocol):
    def get(self, symbol: str) -> Position | None: ...
    def upsert(self, pos: Position) -> None: ...

class ThreadSafePositions(Positions):
    def __init__(self, inner: Positions):
        self._inner = inner
        self._lock = threading.RLock()

    def get(self, symbol: str) -> Position | None:
        with self._lock:
            return self._inner.get(symbol)

    def upsert(self, pos: Position) -> None:
        with self._lock:
            self._inner.upsert(pos)

# Async guard
import asyncio

class AsyncPositions(Protocol):
    async def get(self, symbol: str) -> Position | None: ...
    async def upsert(self, pos: Position) -> None: ...

class LockedAsyncPositions(AsyncPositions):
    def __init__(self, inner: AsyncPositions):
        self._inner = inner
        self._lock = asyncio.Lock()

    async def get(self, symbol: str) -> Position | None:
        async with self._lock:
            return await self._inner.get(symbol)

    async def upsert(self, pos: Position) -> None:
        async with self._lock:
            await self._inner.upsert(pos)
```

---

## 22) Money/Precision (No Floats)

**Policy**: All monetary values use `Decimal`; **never** `float`. Enforce **currency-aware quantization** and rounding (`ROUND_HALF_EVEN`). Forbid cross-currency ops unless an **FX rate object** is provided.

```python
from dataclasses import dataclass
from decimal import Decimal, getcontext, ROUND_HALF_EVEN

getcontext().prec = 34  # high precision; policy-level default

_MIN_UNITS = {"USD": 2, "INR": 2, "JPY": 0}

@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def _q(self) -> Decimal:
        places = _MIN_UNITS.get(self.currency, 2)
        return Decimal((0, (1,), -places))  # 10^-places

    def quantized(self) -> Money:
        return Money(self.amount.quantize(self._q(), rounding=ROUND_HALF_EVEN), self.currency)

    def add(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("Cross-currency op without FX")
        return Money((self.amount + other.amount), self.currency).quantized()

    def mul(self, factor: Decimal) -> Money:
        return Money((self.amount * factor), self.currency).quantized()

# Usage in trading models
@dataclass(frozen=True, slots=True)
class Order:
    id: str
    symbol: str
    qty: int
    price: Money
    
    def total_value(self) -> Money:
        return self.price.mul(Decimal(self.qty))
```

---

## 23) Event Sourcing Patterns (Trading Systems)

**Policy**: Aggregates are **state machines** updated only by applying domain events. Each event carries `aggregate_id`, **monotonic version**, timestamp (UTC), and a **type**. Use **optimistic concurrency** (compare version on persist). Support **replay** and optional **snapshotting** for big streams.

```python
from typing import Protocol, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(slots=True, frozen=True)
class DomainEvent:
    aggregate_id: str
    version: int
    type: str
    ts: datetime
    payload: dict

class EventSourcedAggregate(Protocol):
    id: str
    version: int
    def apply(self, e: DomainEvent) -> None: ...
    def pending(self) -> Sequence[DomainEvent]: ...
    def clear_pending(self) -> None: ...

class BaseAggregate:
    def __init__(self, agg_id: str):
        self.id = agg_id
        self.version = 0
        self._pending: list[DomainEvent] = []

    def _record(self, type_: str, payload: dict) -> None:
        evt = DomainEvent(
            aggregate_id=self.id,
            version=self.version + 1,
            type=type_,
            ts=datetime.now(timezone.utc),
            payload=payload,
        )
        self.apply(evt)           # mutate state
        self._pending.append(evt) # stage for persist

    def pending(self) -> Sequence[DomainEvent]: 
        return tuple(self._pending)
        
    def clear_pending(self) -> None: 
        self._pending.clear()

# Example: Portfolio aggregate
class Portfolio(BaseAggregate):
    def __init__(self, portfolio_id: str):
        super().__init__(portfolio_id)
        self._positions: dict[str, Position] = {}

    def apply(self, event: DomainEvent) -> None:
        if event.type == "position_updated":
            symbol = event.payload["symbol"]
            qty = event.payload["qty"]
            self._positions[symbol] = Position(symbol=symbol, qty=qty)
            self.version = event.version

    def update_position(self, symbol: str, qty: int) -> None:
        self._record("position_updated", {"symbol": symbol, "qty": qty})

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)
```

---

## Integration with Alpha Panda Architecture

These policies align with Alpha Panda's event-driven architecture:

- **Event Handlers**: Use protocol-based contracts for message handlers
- **Service Dependencies**: Inject Redpanda producers/consumers via protocols
- **Domain Models**: Event schemas as immutable dataclasses with validation methods
- **Error Boundaries**: Convert Kafka/database errors to domain exceptions at adapter layer
- **Testing**: Use fake implementations of streaming and database protocols

This ensures clean separation between business logic and infrastructure concerns while maintaining the composability and testability principles outlined in this policy.