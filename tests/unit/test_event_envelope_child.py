from datetime import datetime, timezone
from core.schemas.events import EventEnvelope, EventType


def test_event_envelope_child_event_inherits_trace_and_sets_causation():
    parent = EventEnvelope(
        type=EventType.TRADING_SIGNAL,
        source="strategy_runner",
        key="k",
        broker="paper",
        correlation_id="corr-123",
        data={"a": 1},
    )

    child = parent.create_child_event(
        event_type=EventType.VALIDATED_SIGNAL,
        data={"b": 2},
        source="risk_manager",
        key="k",
    )

    assert child.correlation_id == parent.correlation_id
    assert child.trace_id == parent.trace_id
    assert child.parent_trace_id == parent.id
    assert child.causation_id == parent.id
    assert child.broker == parent.broker
    assert child.type is EventType.VALIDATED_SIGNAL

