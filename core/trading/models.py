from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ExecutionResult:
    """Lightweight execution result model for Phase 1 scaffolding.

    This complements existing event schemas without changing them.
    """

    broker: str
    strategy_id: str
    instrument_token: str
    status: str
    data: Dict[str, Any]
    error_message: Optional[str] = None

