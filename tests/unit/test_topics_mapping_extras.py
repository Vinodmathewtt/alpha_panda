import pytest
from core.schemas.topics import TopicNames, TopicMap


def test_market_topic_by_asset_class_mapping():
    assert TopicNames.get_market_topic_by_asset_class("equity") == TopicNames.MARKET_EQUITY_TICKS
    assert TopicNames.get_market_topic_by_asset_class("crypto") == TopicNames.MARKET_CRYPTO_TICKS
    assert TopicNames.get_market_topic_by_asset_class("options") == TopicNames.MARKET_OPTIONS_TICKS
    assert TopicNames.get_market_topic_by_asset_class("forex") == TopicNames.MARKET_FOREX_TICKS
    # Unknown asset class falls back to shared ticks
    assert TopicNames.get_market_topic_by_asset_class("commodities") == TopicNames.MARKET_TICKS


@pytest.mark.parametrize(
    "topic,expected",
    [
        ("global.dead_letter_queue", "unknown"),
        ("unknown.prefix.route", "unknown"),
        ("market.crypto.ticks", "unknown"),  # shared prefix 'market' => unknown broker
    ],
)
def test_broker_extraction_edge_cases(topic, expected):
    assert TopicMap.get_broker_from_topic(topic) == expected

