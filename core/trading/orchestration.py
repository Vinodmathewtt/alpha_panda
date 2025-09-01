from __future__ import annotations

from typing import Iterable, List

from core.schemas.topics import TopicMap


def get_validated_signal_topics(active_brokers: Iterable[str]) -> List[str]:
    """List topics for validated signals for all active brokers."""
    topics: list[str] = []
    for broker in active_brokers:
        topic_map = TopicMap(broker)
        topics.append(topic_map.signals_validated())
    return topics


def get_order_event_topics(active_brokers: Iterable[str]) -> List[str]:
    """List order lifecycle topics (submitted/filled/failed) for all brokers."""
    topics: list[str] = []
    for broker in active_brokers:
        topic_map = TopicMap(broker)
        topics.extend(
            [
                topic_map.orders_filled(),
                topic_map.orders_failed(),
                topic_map.orders_submitted(),
            ]
        )
    return topics

