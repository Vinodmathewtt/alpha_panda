import sys


def test_streaming_init_is_lightweight():
    """Importing core.streaming must not pull heavy Kafka deps or clients."""
    before = set(sys.modules.keys())

    # Import target package
    import core.streaming as streaming  # noqa: F401

    after = set(sys.modules.keys())
    newly_imported = after - before

    # Ensure these heavy modules are not auto-imported as a side effect
    assert "aiokafka" not in newly_imported
    assert "aiokafka.admin" not in newly_imported
    assert "aiokafka.errors" not in newly_imported
    assert "core.streaming.clients" not in newly_imported


def test_streaming_init_does_not_reexport_heavy_symbols():
    import core.streaming as streaming

    # These should not be exposed from __init__ to avoid eager imports
    assert not hasattr(streaming, "StreamProcessor")
    assert not hasattr(streaming, "MessageProducer")
    assert not hasattr(streaming, "MessageConsumer")
    assert not hasattr(streaming, "StreamServiceBuilder")

