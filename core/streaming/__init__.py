"""Streaming module namespace.

This package exposes multiple submodules (clients, infrastructure, patterns,
reliability, etc.). To avoid heavy optional dependencies at import time in
lightweight environments (e.g., unit tests without Kafka), this __init__ does
not eagerly import submodules.

Import required components directly from subpackages, e.g.:
  - core.streaming.patterns.stream_service_builder import StreamServiceBuilder
  - core.streaming.error_handling import DLQPublisher
"""

# Intentionally avoid importing heavy modules (e.g., clients that depend on aiokafka)
# to keep unit tests import-safe without Kafka dependencies installed.

# Light-weight utility submodules can still be imported explicitly by callers:
# from core.streaming import error_handling  # OK

__all__ = []
