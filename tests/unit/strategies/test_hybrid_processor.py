from decimal import Decimal
from datetime import datetime, timezone

from strategies.core.factory import StrategyFactory
from strategies.core.config import StrategyConfig, ExecutionContext
from core.schemas.events import MarketTick


def test_factory_creates_hybrid_executor_and_rules_fallback():
    factory = StrategyFactory()
    # Configure hybrid with rules that will trigger and ML that will likely be None (no model loaded)
    config = StrategyConfig(
        strategy_id="hybrid_momentum_test",
        strategy_type="hybrid_momentum",
        parameters={
            "rules_config": {"lookback_periods": 2, "threshold": 0.005, "position_size": 1},
            "ml_config": {"lookback_periods": 2, "model_path": "strategies/models/does_not_exist.joblib"},
            "policy_type": "majority_vote",
            "min_ml_confidence": 0.6,
        },
        active_brokers=["paper"],
        instrument_tokens=[999],
        max_position_size=Decimal("1000"),
        risk_multiplier=Decimal("1.0"),
    )
    context = ExecutionContext(broker="paper", portfolio_state={}, market_session="regular", risk_limits={})

    executor = factory.create_executor(config, context)
    assert executor is not None

    # Warm up history so rules momentum can compute
    t0 = datetime.now(timezone.utc)
    history_prices = [Decimal("100.0"), Decimal("101.0")]  # ~1% momentum
    for i, p in enumerate(history_prices):
        _ = executor.process_tick(
            MarketTick(instrument_token=999, last_price=p, timestamp=t0)
        )

    # Next tick should trigger a BUY from rules; ML likely returns None, so fallback to rules
    tick = MarketTick(instrument_token=999, last_price=Decimal("102.0"), timestamp=t0)
    signal = executor.process_tick(tick)
    assert signal is not None
    assert signal.signal_type in ("BUY", "SELL", "HOLD")
    # With upward momentum the rules signal should be BUY
    assert signal.signal_type == "BUY"

