"""
Low-frequency demo strategy for end-to-end validation.

Emits at most one signal per instrument per `min_interval_seconds`
(default 900s = 15 minutes). This is intentionally conservative so
that a deployment can observe a few signals per day to validate the
pipeline without generating excessive noise or orders.

Recommended usage: enable for a small subset of instruments only
(e.g., 1–3) to cap total signals.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from decimal import Decimal
from time import time

from core.schemas.events import MarketTick as MarketData
from strategies.core.protocols import StrategyProcessor, SignalResult
from core.logging import get_trading_logger_safe


logger = get_trading_logger_safe("low_frequency_demo_strategy")


class LowFrequencyDemoProcessor(StrategyProcessor):
    """
    Rule-based demo processor that emits infrequent signals.

    Parameters:
    - min_interval_seconds: Minimum seconds between signals per instrument (default: 900)
    - max_daily_signals_per_instrument: Optional cap to avoid too many daily signals (default: None)
    - side: "BUY" or "SELL" or "auto" (auto alternates by instrument hash)
    - quantity: size per order (default: 1)

    Emission logic:
    - Tracks the last emission timestamp per instrument.
    - Emits when current_time - last_emit >= min_interval_seconds.
    - Uses the current tick price as the order price.
    """

    def __init__(
        self,
        min_interval_seconds: int = 900,
        max_daily_signals_per_instrument: Optional[int] = None,
        side: str = "auto",
        quantity: int = 1,
    ) -> None:
        self.min_interval_seconds = int(min_interval_seconds)
        self.max_daily_signals_per_instrument = (
            int(max_daily_signals_per_instrument) if max_daily_signals_per_instrument is not None else None
        )
        self.side = str(side).upper()
        self.quantity = int(quantity)

        # Runtime state (in-memory; resets on restart)
        self._last_emit_ts: Dict[int, float] = {}
        self._daily_counts: Dict[int, int] = {}
        self._daily_epoch: Optional[int] = None

        logger.info(
            "Initialized low-frequency demo strategy",
            min_interval_seconds=self.min_interval_seconds,
            max_daily_signals_per_instrument=self.max_daily_signals_per_instrument,
            side=self.side,
            quantity=self.quantity,
        )

    def _maybe_reset_daily(self, now: float) -> None:
        # Reset daily counters at UTC midnight boundaries
        day_epoch = int(now // 86400)
        if self._daily_epoch is None or day_epoch != self._daily_epoch:
            self._daily_epoch = day_epoch
            self._daily_counts.clear()

    def get_required_history_length(self) -> int:
        return 1

    def supports_instrument(self, token: int) -> bool:
        return True

    def _select_side(self, instrument_token: int) -> str:
        if self.side in ("BUY", "SELL"):
            return self.side
        # Auto: alternate side by instrument hash for variety
        return "BUY" if (int(instrument_token) % 2 == 0) else "SELL"

    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        try:
            now = time()
            self._maybe_reset_daily(now)

            token = int(tick.instrument_token)
            last = self._last_emit_ts.get(token, 0.0)

            # Enforce per-instrument min interval
            if now - last < self.min_interval_seconds:
                return None

            # Enforce optional daily cap
            if self.max_daily_signals_per_instrument is not None:
                count = self._daily_counts.get(token, 0)
                if count >= self.max_daily_signals_per_instrument:
                    return None

            side = self._select_side(token)
            price = Decimal(str(tick.last_price))

            # Update counters before returning to avoid race in rapid ticks
            self._last_emit_ts[token] = now
            self._daily_counts[token] = self._daily_counts.get(token, 0) + 1

            return SignalResult(
                signal_type=side,
                confidence=0.5,
                quantity=self.quantity,
                price=price,
                reasoning=f"low_frequency_demo: interval {self.min_interval_seconds}s elapsed"
            )
        except Exception as e:
            logger.warning("Low-frequency demo processing error", error=str(e))
            return None


def create_low_frequency_demo_processor(config: Dict[str, Any]) -> LowFrequencyDemoProcessor:
    return LowFrequencyDemoProcessor(
        min_interval_seconds=int(config.get("min_interval_seconds", 900)),
        max_daily_signals_per_instrument=(
            int(config["max_daily_signals_per_instrument"]) if config.get("max_daily_signals_per_instrument") is not None else None
        ),
        side=str(config.get("side", "auto")),
        quantity=int(config.get("quantity", 1)),
    )

