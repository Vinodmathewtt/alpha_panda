from core.monitoring.metrics_registry import MetricsRegistry


def test_metrics_registry_keys_include_signals_rejected():
    broker = "paper"
    # Validated
    assert MetricsRegistry.signals_validated_count(broker).endswith(":count")
    assert ":signals_validated:" in MetricsRegistry.signals_validated_count(broker)
    assert ":signals_validated:" in MetricsRegistry.signals_validated_last(broker)

    # Rejected (new)
    assert MetricsRegistry.signals_rejected_count(broker).endswith(":count")
    assert ":signals_rejected:" in MetricsRegistry.signals_rejected_count(broker)
    assert ":signals_rejected:" in MetricsRegistry.signals_rejected_last(broker)

    # All broker keys contain both validated and rejected keys
    all_keys = MetricsRegistry.get_all_broker_specific_keys(broker)
    vals = list(all_keys.values())
    assert any(":signals_validated:" in k for k in vals)
    assert any(":signals_rejected:" in k for k in [
        MetricsRegistry.signals_rejected_count(broker),
        MetricsRegistry.signals_rejected_last(broker),
    ])

