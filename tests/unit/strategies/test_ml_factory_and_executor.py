import types
from decimal import Decimal
from datetime import datetime, timezone

import pytest

from strategies.core.factory import StrategyFactory
from strategies.core.config import StrategyConfig, ExecutionContext
from core.schemas.events import MarketTick


class DummyModel:
    def predict(self, X):
        return [1]

    def predict_proba(self, X):
        return [[0.1, 0.9]]


def test_factory_creates_ml_executor_momentum(monkeypatch):
    # Patch model loader to avoid file dependency
    from strategies.implementations import ml_momentum as mlmod

    monkeypatch.setattr(mlmod.ModelLoader, "load_model", lambda path: DummyModel())

    factory = StrategyFactory()
    config = StrategyConfig(
        strategy_id="ml_momentum_test",
        strategy_type="MLMomentumProcessor",
        parameters={
            "model_path": "models/momentum_v1.joblib",
            "lookback_periods": 5,
            "position_size": 10,
            "confidence_threshold": 0.5,
        },
        active_brokers=["paper"],
        instrument_tokens=[123],
        max_position_size=Decimal("10000"),
        risk_multiplier=Decimal("1.0"),
    )
    context = ExecutionContext(
        broker="paper",
        portfolio_state={},
        market_session="regular",
        risk_limits={},
    )

    executor = factory.create_executor(config, context)

    # Warm-up history by feeding ticks to the executor
    base_price = Decimal("100.0")
    for i in range(5):
        warm_tick = MarketTick(
            instrument_token=123,
            last_price=base_price + Decimal(i),
            timestamp=datetime.now(timezone.utc),
        )
        _ = executor.process_tick(warm_tick)

    tick = MarketTick(instrument_token=123, last_price=Decimal("106.0"), timestamp=datetime.now(timezone.utc))

    signal = executor.process_tick(tick)
    assert signal is not None
    assert 0.0 <= signal.confidence <= 1.0
    assert signal.quantity == 10


def test_factory_accepts_rules_based_type(monkeypatch):
    factory = StrategyFactory()
    # Rules-based momentum should be supported now
    config = StrategyConfig(
        strategy_id="rules_momentum",
        strategy_type="momentum",
        parameters={"lookback_periods": 2, "threshold": 0.01, "position_size": 1},
        active_brokers=["paper"],
        instrument_tokens=[1],
        max_position_size=Decimal("1000"),
        risk_multiplier=Decimal("1.0"),
    )
    context = ExecutionContext(broker="paper", portfolio_state={}, market_session="regular", risk_limits={})
    executor = factory.create_executor(config, context)
    assert executor is not None


def test_factory_allows_non_ml_processors(monkeypatch):
    factory = StrategyFactory()

    def bad_factory(_params):
        # Valid StrategyProcessor without ML methods
        class BadProcessor:
            def get_required_history_length(self):
                return 1

            def supports_instrument(self, token: int) -> bool:
                return True

            def get_strategy_name(self) -> str:
                return "bad"

            def process_tick(self, tick, history):
                return None

        return BadProcessor()

    # Temporarily register a non-ML processor and ensure factory accepts it
    factory.register_processor("bad_proc", __name__ + ".bad_factory")
    # Monkeypatch loader to point to local factory only for this module
    import importlib
    _orig_import_module = importlib.import_module

    def _fake_import_module(m):
        if m == __name__:
            return types.SimpleNamespace(bad_factory=bad_factory)
        return _orig_import_module(m)

    monkeypatch.setattr(importlib, "import_module", _fake_import_module)

    config = StrategyConfig(
        strategy_id="bad",
        strategy_type="bad_proc",
        parameters={},
        active_brokers=["paper"],
        instrument_tokens=[1],
        max_position_size=Decimal("1000"),
        risk_multiplier=Decimal("1.0"),
    )
    context = ExecutionContext(broker="paper", portfolio_state={}, market_session="regular", risk_limits={})
    executor = factory.create_executor(config, context)
    assert executor is not None
