from core.monitoring.metrics_registry import MetricsRegistry


def test_broker_specific_keys_include_broker_namespace():
    brokers = ["paper", "zerodha"]
    mapping = MetricsRegistry.validate_key_consistency(brokers)
    keys = mapping["keys"]
    # Ensure broker names appear somewhere in generated keys for namespacing
    assert any(":paper:" in k or k.endswith(":paper:last") or k.endswith(":paper:count") for k in keys)
    assert any(":zerodha:" in k or k.endswith(":zerodha:last") or k.endswith(":zerodha:count") for k in keys)

