import pytest

from core.schemas.topics import TopicMap, TopicNames
from core.schemas.topic_validator import TopicValidator


def test_broker_extraction_from_topics():
    assert TopicMap.get_broker_from_topic("paper.signals.raw") == "paper"
    assert TopicMap.get_broker_from_topic("zerodha.orders.filled") == "zerodha"
    assert TopicMap.get_broker_from_topic("market.ticks") == "unknown"
    assert TopicMap.get_broker_from_topic("global.dead_letter_queue") == "unknown"
    assert TopicMap.get_broker_from_topic("") == "unknown"


@pytest.mark.parametrize(
    "broker,expected",
    [
        ("paper", "paper.signals.raw"),
        ("zerodha", "zerodha.signals.raw"),
    ],
)
def test_signals_raw_topic_mapping(broker, expected):
    tm = TopicMap(broker)
    assert tm.signals_raw() == expected
    assert TopicValidator.validate_broker_topic_pair(expected, broker)


@pytest.mark.parametrize(
    "broker,expected",
    [
        ("paper", "paper.orders.filled"),
        ("zerodha", "zerodha.orders.filled"),
    ],
)
def test_orders_filled_topic_mapping(broker, expected):
    tm = TopicMap(broker)
    assert tm.orders_filled() == expected
    assert TopicValidator.validate_broker_topic_pair(expected, broker)


def test_dlq_suffix_helper():
    base = TopicNames.MARKET_TICKS
    assert TopicNames.get_dlq_topic(base) == f"{base}.dlq"

