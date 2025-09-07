from decimal import Decimal
from datetime import datetime, timezone

from strategies.core.factory import StrategyFactory as CompositionFactory
from strategies.core.config import StrategyConfig, ExecutionContext
from core.schemas.events import MarketTick


def _mk_exec(enabled: bool = True):
    config = StrategyConfig(
        strategy_id="gate_test",
        strategy_type="momentum",
        parameters={"lookback_periods": 1, "threshold": 0.0, "position_size": 1},
        active_brokers=["paper"],
        instrument_tokens=[123],
        max_position_size=Decimal("1000"),
        risk_multiplier=Decimal("1.0"),
        enabled=enabled,
    )
    context = ExecutionContext(
        broker="paper", portfolio_state={}, market_session="regular", risk_limits={}
    )
    return CompositionFactory().create_executor(config, context)


def test_executor_gates_on_instrument_membership():
    ex = _mk_exec(enabled=True)
    # Tick for an instrument not in config should be ignored
    tick = MarketTick(
        instrument_token=999,
        last_price=Decimal("100.0"),
        timestamp=datetime.now(timezone.utc),
    )
    assert ex.can_process_tick(tick) is False
    assert ex.process_tick(tick) is None


def test_executor_gates_on_enabled_flag():
    ex = _mk_exec(enabled=False)
    # Tick for a configured instrument should still be ignored when disabled
    tick = MarketTick(
        instrument_token=123,
        last_price=Decimal("100.0"),
        timestamp=datetime.now(timezone.utc),
    )
    assert ex.can_process_tick(tick) is False
    assert ex.process_tick(tick) is None

