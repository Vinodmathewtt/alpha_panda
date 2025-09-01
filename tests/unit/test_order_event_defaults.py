from datetime import datetime, timezone
from decimal import Decimal
from core.schemas.events import OrderFilled, SignalType, ExecutionMode


def test_order_filled_default_side_and_enum_coercion():
    of = OrderFilled(
        order_id="OID-123",
        instrument_token=1,
        quantity=1,
        fill_price=Decimal("1.00"),
        timestamp=datetime.now(timezone.utc),
        broker="paper",
        execution_mode=ExecutionMode.PAPER,
    )
    assert of.side is SignalType.BUY  # default

    of2 = OrderFilled(
        order_id="OID-124",
        instrument_token=1,
        quantity=1,
        fill_price=Decimal("1.00"),
        timestamp=datetime.now(timezone.utc),
        broker="paper",
        execution_mode=ExecutionMode.PAPER,
        side="SELL",
    )
    assert of2.side is SignalType.SELL

