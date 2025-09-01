import pytest
from datetime import datetime, timezone
from decimal import Decimal
from core.schemas.events import (
    EventEnvelope,
    EventType,
    TradingSignal,
    OrderPlaced,
    OrderFilled,
    OrderFailed,
    SignalType,
    ExecutionMode,
    OrderStatus,
)


def test_event_envelope_minimal_valid():
    now = datetime.now(timezone.utc)
    env = EventEnvelope(
        type=EventType.MARKET_TICK,
        source="test",
        key="k",
        broker="paper",
        correlation_id="corr-1",
        data={"ok": True},
    )
    assert env.id
    assert env.trace_id
    assert env.type == EventType.MARKET_TICK
    assert env.broker == "paper"
    assert env.key == "k"
    assert env.data == {"ok": True}


def test_order_events_enums_and_fields():
    placed = OrderPlaced(
        order_id="OID-1",
        instrument_token=123,
        signal_type=SignalType.BUY,
        quantity=10,
        price=Decimal("100.5"),
        timestamp=datetime.now(timezone.utc),
        broker="zerodha",
        status=OrderStatus.PLACED,
    )
    assert placed.status is OrderStatus.PLACED
    assert placed.signal_type is SignalType.BUY

    filled = OrderFilled(
        order_id="OID-1",
        instrument_token=123,
        quantity=10,
        fill_price=Decimal("100.5"),
        timestamp=datetime.now(timezone.utc),
        broker="paper",
        signal_type=SignalType.BUY,
        execution_mode=ExecutionMode.PAPER,
    )
    assert isinstance(filled.fill_price, Decimal)
    assert filled.broker == "paper"

    failed = OrderFailed(
        strategy_id="s1",
        instrument_token=123,
        signal_type=SignalType.SELL,
        quantity=5,
        price=Decimal("99.5"),
        order_id="OID-2",
        execution_mode=ExecutionMode.ZERODHA,
        error_message="Insufficient funds",
        timestamp=datetime.now(timezone.utc),
        broker="zerodha",
    )
    assert failed.execution_mode is ExecutionMode.ZERODHA
    assert failed.broker == "zerodha"


def test_trading_signal_schema():
    ts = TradingSignal(
        strategy_id="strat-1",
        instrument_token=111,
        signal_type=SignalType.SELL,
        quantity=100,
        price=Decimal("125.25"),
        timestamp=datetime.now(timezone.utc),
        confidence=0.9,
        metadata={"note": "test"},
    )
    assert ts.signal_type is SignalType.SELL
    assert 0.0 <= ts.confidence <= 1.0

