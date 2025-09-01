"""
Centralized event ID generation.

Prefers real UUID v7 when available, else falls back to a
time-seeded, uniqueness-preserving scheme suitable for ordering
within short windows. This centralization allows future swaps
to a stronger implementation (e.g., ULID or a vetted uuid7 lib)
without touching call sites.
"""

from __future__ import annotations

import os
import time
from uuid import uuid4


def _fallback_time_prefixed_uuid() -> str:
    """Fallback: timestamp (ms) hex prefix + uuid4 suffix.

    Not a true UUID v7, but provides coarse ordering and uniqueness.
    """
    ts_ms = int(time.time() * 1000)
    return f"{ts_ms:013x}-{str(uuid4())[13:]}"


def generate_event_id() -> str:
    """Generate a monotonic-ish, globally unique event ID.

    Attempts a real UUID v7 if an implementation is available in the
    environment; otherwise uses a time-prefixed UUID4 fallback.
    """
    # Attempt uuid6/uuid7 provider if present
    try:
        # Some environments expose uuid7 via the 'uuid6' package
        from uuid6 import uuid7  # type: ignore

        return str(uuid7())
    except Exception:
        pass

    try:
        # Some installations may have a 'uuid7' package exposing uuid7()
        from uuid7 import uuid7 as uuid7_func  # type: ignore

        return str(uuid7_func())
    except Exception:
        pass

    # Fallback
    return _fallback_time_prefixed_uuid()

