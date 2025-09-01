from __future__ import annotations

from typing import Any


def extract_broker_from_topic(topic: str) -> str:
    """Return the broker prefix from a topic like 'paper.orders.filled'."""
    if not topic:
        return ""
    # Topics follow naming: {broker}.{domain}.{event_type}[.dlq]
    return topic.split(".", 1)[0]


def get_first_producer_or_raise(orchestrator: Any):
    """Return the first producer from orchestrator or raise a clear error."""
    producers = getattr(orchestrator, "producers", None)
    if producers is None:
        raise RuntimeError("Orchestrator has no 'producers' attribute")
    if not producers:
        raise RuntimeError("No producers available for orchestrator")
    return producers[0]

