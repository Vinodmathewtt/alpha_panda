from __future__ import annotations

import asyncio
import random
from decimal import Decimal
from typing import Any, Dict

from core.config.settings import RedpandaSettings, Settings
from core.logging import (
    get_trading_logger_safe,
    get_error_logger_safe,
    bind_broker_context,
)
from core.monitoring.pipeline_metrics import PipelineMetricsCollector
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector
from core.observability.tracing import get_tracer
from core.schemas.events import EventType
from core.schemas.topics import TopicMap, TopicNames
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.trading.utils import get_first_producer_or_raise
from core.schemas.events import TradingSignal, ValidatedSignal, OrderFilled, ExecutionMode, SignalType, PnlSnapshot, EventType, OrderFailed
from core.utils.exceptions import ValidationError
from core.schemas.topics import PartitioningKeys
from core.utils.ids import generate_event_id


class PaperTradingService:
    """Broker-scoped trading orchestrator for 'paper'.

    Phase 2 scaffold: builds/imports but does not require full runtime logic.
    """

    def __init__(
        self,
        config: RedpandaSettings,
        settings: Settings,
        redis_client: Any,
        prometheus_metrics: PrometheusMetricsCollector | None = None,
    ) -> None:
        self.settings = settings
        self.logger = get_trading_logger_safe("paper_trading")
        self.error_logger = get_error_logger_safe("paper_trading_errors")
        try:
            self.broker_logger = bind_broker_context(self.logger, "paper")
        except Exception:
            self.broker_logger = self.logger
        self.metrics_collector = PipelineMetricsCollector(redis_client, settings)
        self.prom_metrics = prometheus_metrics
        # Simple in-memory idempotency (bounded)
        from collections import deque
        self._seen_keys: set[str] = set()
        self._seen_queue: deque[str] = deque(maxlen=2000)

        # In-memory portfolio state (Phase 3)
        self._positions: dict[tuple[str, int], dict[str, Decimal | int]] = {}
        self._realized: dict[tuple[str, int], Decimal] = {}
        self._cash: dict[str, Decimal] = {}
        self._last_price: dict[int, Decimal] = {}
        # Bracket/OCO state per (strategy, instrument)
        self._brackets: dict[tuple[str, int], dict[str, Decimal | None]] = {}
        # Pending stop/stop-limit orders
        self._pending_stops: list[dict[str, Any]] = []

        # Subscribe to paper validated signals and shared market ticks
        topics_signals = [TopicMap("paper").signals_validated()]

        self.orchestrator = (
            StreamServiceBuilder("paper_trading", config, settings)
            .with_prometheus(prometheus_metrics)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=topics_signals,
                group_id=f"{settings.redpanda.group_id_prefix}.paper_trading.signals",
                handler_func=self._handle_validated_signal,
            )
            .add_consumer_handler(
                topics=[TopicNames.MARKET_TICKS],
                group_id=f"{settings.redpanda.group_id_prefix}.paper_trading.ticks",
                handler_func=self._handle_market_tick,
            )
            .build()
        )

    async def _get_producer(self):
        return get_first_producer_or_raise(self.orchestrator)

    async def start(self) -> None:
        self.logger.info("PaperTrading starting...")
        try:
            self.broker_logger.info("PaperTrading started", broker="paper")
        except Exception:
            pass
        await self.orchestrator.start()
        if self.prom_metrics:
            try:
                self.prom_metrics.set_pipeline_health("paper_trading", "paper", True)
            except Exception:
                pass

    async def stop(self) -> None:
        await self.orchestrator.stop()
        self.logger.info("PaperTrading stopped")
        try:
            self.broker_logger.info("PaperTrading stopped", broker="paper")
        except Exception:
            pass

    async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
        """Process validated signals and emit simulated fills (paper).

        Enhancements:
        - Slippage and commission models (config-driven)
        - Optional latency simulation (mean/std ms) with deterministic RNG per event
        """
        tracer = get_tracer("paper_trading")
        with tracer.start_as_current_span("paper_trading.handle_signal") as span:
            try:
                span.set_attribute("broker", "paper")
                span.set_attribute("topic", topic)
            except Exception:
                pass
        # Robustly check message type
        msg_type = message.get("type")
        if isinstance(msg_type, str):
            is_validated = msg_type == EventType.VALIDATED_SIGNAL or msg_type == EventType.VALIDATED_SIGNAL.value
        else:
            is_validated = msg_type == EventType.VALIDATED_SIGNAL
        if not is_validated:
            return

        data = message.get("data", {})
        try:
            # Build models from payload
            validated = ValidatedSignal(**data)
            signal: TradingSignal = validated.original_signal
        except Exception as e:
            # Route malformed payloads to DLQ via reliability layer
            raise ValidationError("Invalid validated signal payload", field="data", value=str(e))

        # For latency metrics
        _handle_started = None
        try:
            import time as _t
            _handle_started = _t.perf_counter()
        except Exception:
            pass

        # Record Prom last-activity for signals
        if self.prom_metrics:
            self.prom_metrics.set_last_activity("paper_trading", "signals_validated", "paper")

        # Idempotence key: strategy_id + instrument_token + ts
        idem_key = f"{signal.strategy_id}:{signal.instrument_token}:{validated.timestamp.isoformat()}"
        if idem_key in self._seen_keys:
            self.logger.info("Duplicate validated signal ignored (idempotent)", key=idem_key)
            return
        self._seen_keys.add(idem_key)
        self._seen_queue.append(idem_key)
        if len(self._seen_queue) == self._seen_queue.maxlen:
            # Drop oldest from set to bound memory
            old = self._seen_queue.popleft()
            if old in self._seen_keys:
                self._seen_keys.discard(old)

        # Deterministic RNG per event to make behavior reproducible
        seed = f"{signal.strategy_id}:{signal.instrument_token}:{validated.timestamp.isoformat()}"
        rng = random.Random(seed)

        # Optional latency simulation (ms)
        try:
            mean_ms = float(getattr(self.settings.paper_trading, "latency_ms_mean", 0.0) or 0.0)
            std_ms = float(getattr(self.settings.paper_trading, "latency_ms_std", 0.0) or 0.0)
        except Exception:
            mean_ms, std_ms = 0.0, 0.0
        if mean_ms > 0 or std_ms > 0:
            delay = max(0.0, rng.gauss(mean_ms, std_ms)) / 1000.0
            try:
                await asyncio.sleep(delay)
            except Exception:
                pass

        # Determine order type and TIF (from metadata)
        md = signal.metadata or {}
        order_type = str(md.get("order_type", "market")).lower()
        tif = str(md.get("tif", "DAY")).upper()  # IOC|FOK|DAY|GTD (not supported yet)
        limit_price_md = md.get("limit_price")
        stop_price_md = md.get("stop_price")

        # Normalize side as string for robust comparisons
        try:
            side_str = signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type)
        except Exception:
            side_str = str(signal.signal_type)

        # Slippage and commission (% of price/notional)
        try:
            slip_pct = float(getattr(self.settings.paper_trading, "slippage_percent", 0.0) or 0.0)
            comm_pct = float(getattr(self.settings.paper_trading, "commission_percent", 0.0) or 0.0)
        except Exception:
            slip_pct, comm_pct = 0.0, 0.0

        base_price = validated.validated_price or (signal.price or Decimal("0"))
        if not isinstance(base_price, Decimal):
            try:
                base_price = Decimal(str(base_price))
            except Exception:
                base_price = Decimal("0")

        # Price sanity guardrails
        try:
            min_p = getattr(self.settings.paper_trading, "min_price", None)
            max_p = getattr(self.settings.paper_trading, "max_price", None)
            if min_p is not None and float(min_p) is not None and base_price < Decimal(str(min_p)):
                await self._emit_order_failed(signal, validated, reason="Price below minimum")
                return
            if max_p is not None and str(max_p) != "None" and float(max_p) > 0 and base_price > Decimal(str(max_p)):
                await self._emit_order_failed(signal, validated, reason="Price above maximum")
                return
        except Exception:
            pass

        # Guardrails: instrument allowlist, quantity and price sanity
        allow = self.settings.paper_trading.allowed_instruments or []
        if allow and int(signal.instrument_token) not in allow:
            await self._emit_order_failed(signal, validated, reason="Instrument not allowed")
            return
        if signal.quantity < max(1, int(getattr(self.settings.paper_trading, "min_quantity", 1))):
            await self._emit_order_failed(signal, validated, reason="Quantity below minimum")
            return
        mq = getattr(self.settings.paper_trading, "max_quantity", None)
        if mq is not None and signal.quantity > int(mq):
            await self._emit_order_failed(signal, validated, reason="Quantity exceeds maximum")
            return

        # Order routing and fillability
        # For market orders: fully fillable baseline
        # For limit: require market crossing according to side
        market_price = base_price  # Using validated/signaled price as proxy
        limit_price = None
        if limit_price_md is not None:
            try:
                limit_price = Decimal(str(limit_price_md))
            except Exception:
                limit_price = None
        if order_type == "limit" and limit_price is None:
            limit_price = base_price
        # Stop/Stop-limit capture
        stop_price = None
        if order_type in ("stop", "stop_limit"):
            try:
                stop_price = Decimal(str(stop_price_md)) if stop_price_md is not None else None
            except Exception:
                stop_price = None
            if stop_price is None:
                await self._emit_order_failed(signal, validated, reason="Missing stop_price for stop order")
                return

        def _is_crossing(side: SignalType, mkt: Decimal, lim: Decimal) -> bool:
            if lim is None:
                return True
            if side == SignalType.BUY:
                return mkt <= lim
            return mkt >= lim

        requested_qty = int(validated.validated_quantity or 0)
        fillable_qty = requested_qty
        if order_type == "limit" and (not _is_crossing(signal.signal_type, market_price, limit_price)):
            fillable_qty = 0

        # TIF rules
        if tif == "FOK" and fillable_qty < requested_qty and order_type not in ("stop", "stop_limit"):
            # All-or-none failed
            await self._emit_order_failed(signal, validated, reason="FOK not fully fillable")
            return

        # IOC: allow partial; DAY: treat as normal
        if tif == "IOC" and fillable_qty <= 0 and order_type not in ("stop", "stop_limit"):
            await self._emit_order_failed(signal, validated, reason="IOC no immediate fill available")
            return

        # Decide actual fill quantity (IOC may fill partial fraction)
        actual_qty = requested_qty
        if tif == "IOC" and fillable_qty > 0 and fillable_qty < requested_qty:
            # Simulate partial based on liquidity fraction
            frac = max(0.1, min(1.0, rng.random()))
            actual_qty = max(1, int(requested_qty * frac))
        elif order_type == "limit" and fillable_qty == 0:
            actual_qty = 0

        # Stop and stop-limit orders: if not triggered now, enqueue pending order and return
        def _stop_triggered(side: SignalType, mkt: Decimal, stp: Decimal) -> bool:
            return (mkt >= stp) if side == SignalType.BUY else (mkt <= stp)

        if order_type in ("stop", "stop_limit"):
            if not _stop_triggered(signal.signal_type, market_price, stop_price):
                if tif in ("IOC", "FOK"):
                    await self._emit_order_failed(signal, validated, reason="Stop not triggered for IOC/FOK")
                    return
                # Enqueue DAY stop to trigger on ticks
                self._pending_stops.append({
                    "strategy_id": signal.strategy_id,
                    "instrument_token": int(signal.instrument_token),
                    "side": signal.signal_type,
                    "quantity": requested_qty,
                    "stop_price": stop_price,
                    "limit_price": limit_price if order_type == "stop_limit" else None,
                    "order_type": order_type,
                    "created_at": validated.timestamp,
                })
                self.logger.info("Enqueued stop order", strategy_id=signal.strategy_id, instrument_token=int(signal.instrument_token), order_type=order_type, stop_price=str(stop_price))
                # Record order counter as accepted (pending). We use status="pending".
                if self.prom_metrics:
                    self.prom_metrics.record_order_executed("paper", order_type, "pending")
                return
            else:
                # Triggered immediately; treat as market/limit according to type
                order_type = "market" if order_type == "stop" else "limit"
                # Recompute fillable for limit if needed
                if order_type == "limit" and not _is_crossing(signal.signal_type, market_price, limit_price):
                    await self._emit_order_failed(signal, validated, reason="Stop-limit not crossing")
                    return

        # Apply slippage: BUY pays up, SELL receives less
        slip_mult = (1 + slip_pct / 100.0) if signal.signal_type == SignalType.BUY else (1 - slip_pct / 100.0)
        fill_price_base = (base_price * Decimal(str(slip_mult))) if base_price else Decimal("0")

        # Commission on notional will be set per fill below
        order_id = generate_event_id()

        # Cash/position constraints (basic risk)
        # Initialize cash balance lazily from settings
        if signal.strategy_id not in self._cash:
            from decimal import Decimal as _D
            try:
                self._cash[signal.strategy_id] = _D(str(self.settings.paper_trading.starting_cash))
            except Exception:
                self._cash[signal.strategy_id] = _D("1000000")

        if signal.signal_type == SignalType.BUY:
            # Determine max affordable quantity including commission
            unit_cost = fill_price_base * Decimal("1.0") * Decimal(str(1 + comm_pct / 100.0))
            if unit_cost > 0:
                max_affordable = int(self._cash[signal.strategy_id] // unit_cost)
                if tif == "FOK" and actual_qty > max_affordable:
                    await self._emit_order_failed(signal, validated, reason="FOK insufficient cash")
                    return
                if actual_qty > max_affordable:
                    if tif == "IOC" and max_affordable > 0:
                        actual_qty = max_affordable
                    else:
                        await self._emit_order_failed(signal, validated, reason="Insufficient cash")
                        return
        # Max position notional guardrail
        try:
            max_notional = getattr(self.settings.paper_trading, "max_position_notional", None)
            if max_notional is not None and float(max_notional) > 0:
                unit_cost2 = float(fill_price_base) * (1 + comm_pct / 100.0)
                if unit_cost2 > 0:
                    cap_qty = int(float(max_notional) // unit_cost2)
                    if cap_qty <= 0:
                        await self._emit_order_failed(signal, validated, reason="Exceeds max position notional")
                        return
                    if tif == "FOK" and actual_qty > cap_qty:
                        await self._emit_order_failed(signal, validated, reason="FOK exceeds max position notional")
                        return
                    if actual_qty > cap_qty:
                        if tif == "IOC":
                            actual_qty = cap_qty
                        else:
                            await self._emit_order_failed(signal, validated, reason="Exceeds max position notional")
                            return
        except Exception:
            pass

        # SELL: enforce position availability (no shorting in Phase 3)
        if side_str != "BUY":
            pre_key2 = (signal.strategy_id, int(signal.instrument_token))
            pos2 = self._positions.get(pre_key2, {"qty": 0})
            held = int(pos2.get("qty", 0))
            if tif == "FOK" and actual_qty > held:
                await self._emit_order_failed(signal, validated, reason="FOK exceeds position size")
                return
            if actual_qty > held:
                if tif == "IOC" and held > 0:
                    actual_qty = held
                else:
                    await self._emit_order_failed(signal, validated, reason="No position to sell")
                    return

        # Partial fill simulation (Phase 2)
        try:
            p_prob = float(getattr(self.settings.paper_trading, "partial_fill_prob", 0.0) or 0.0)
            max_parts = int(getattr(self.settings.paper_trading, "max_partials", 1) or 1)
        except Exception:
            p_prob, max_parts = 0.0, 1
        parts: list[int] = [actual_qty]
        if actual_qty > 1 and max_parts > 1 and rng.random() < p_prob:
            # split into up to max_parts parts randomly
            remaining = actual_qty
            parts = []
            n_parts = rng.randint(2, min(max_parts, actual_qty))
            for i in range(n_parts - 1):
                # choose at least 1, leave at least 1 for remaining slots
                take = rng.randint(1, max(1, remaining - (n_parts - i - 1)))
                parts.append(take)
                remaining -= take
            parts.append(remaining)

        topic_out = TopicMap("paper").orders_filled()
        # Track pre-fill position to decide if this is a new long entry
        pre_key = (signal.strategy_id, int(signal.instrument_token))
        pre_pos = self._positions.get(pre_key, {"qty": 0})
        pre_qty = int(pre_pos.get("qty", 0))

        producer = await self._get_producer()
        for qty in parts:
            notional = fill_price_base * Decimal(qty)
            fees = (notional * Decimal(str(comm_pct / 100.0))) if notional else None
            filled = OrderFilled(
                order_id=order_id,
                instrument_token=signal.instrument_token,
                quantity=qty,
                fill_price=fill_price_base,
                timestamp=validated.timestamp,
                broker="paper",
                side=signal.signal_type,
                strategy_id=signal.strategy_id,
                signal_type=signal.signal_type,
                execution_mode=ExecutionMode.PAPER,
                fees=fees,
            )
            key = PartitioningKeys.order_key(signal.strategy_id, signal.instrument_token, str(validated.timestamp))
            await producer.send(
                topic=topic_out,
                key=key,
                data=filled.model_dump(mode="json"),
                event_type=EventType.ORDER_FILLED,
                broker="paper",
            )
            if self.prom_metrics:
                self.prom_metrics.record_order_executed("paper", order_type, "filled")
            self.logger.info(
                "Emitted paper order filled",
                broker="paper",
                topic=topic_out,
                strategy_id=signal.strategy_id,
                instrument_token=signal.instrument_token,
                part_quantity=qty,
                total_parts=len(parts),
                slippage_percent=slip_pct,
                commission_percent=comm_pct,
                order_type=order_type,
                tif=tif,
            )

            # Update portfolio positions and realized PnL
            self._apply_fill_to_portfolio(signal.strategy_id, signal.instrument_token, signal.signal_type, qty, filled.fill_price, fees)

            # Metrics: slippage bps per fill
            if self.prom_metrics and base_price and filled.fill_price:
                try:
                    if signal.signal_type == SignalType.BUY:
                        bps = (float(filled.fill_price / base_price) - 1.0) * 10000.0
                    else:
                        bps = (1.0 - float(filled.fill_price / base_price)) * 10000.0
                    self.prom_metrics.record_paper_slippage_bps(side=str(signal.signal_type), broker="paper", bps=abs(bps))
                except Exception:
                    pass

        # If this was a fresh long entry and bracket config present, set bracket on entry
        try:
            if signal.signal_type == SignalType.BUY and pre_qty == 0:
                self._set_bracket_if_configured(
                    signal.strategy_id,
                    signal.instrument_token,
                    fill_price_base,
                    signal.metadata or {},
                )
        except Exception:
            pass

        try:
            # Emit a minimal PnL snapshot to broker-specific topic (placeholder)
            pnl = PnlSnapshot(
                broker="paper",
                instrument_token=signal.instrument_token,
                realized_pnl=self._compute_realized_pnl_instrument(signal.strategy_id, signal.instrument_token),
                unrealized_pnl=self._compute_unrealized_pnl_instrument(signal.strategy_id, signal.instrument_token),
                total_pnl=self._compute_total_pnl_instrument(signal.strategy_id, signal.instrument_token),
                timestamp=validated.timestamp,
            )
            await producer.send(
                topic=TopicMap("paper").pnl_snapshots(),
                key=f"portfolio_snapshot_paper:{signal.strategy_id}",
                data=pnl.model_dump(mode="json"),
                event_type=EventType.PNL_SNAPSHOT,
                broker="paper",
            )
            # Record pipeline metrics (Redis) and Prom last-activity
            if self.metrics_collector:
                try:
                    await self.metrics_collector.record_order_processed(
                        filled.model_dump(mode="json"), broker_context="paper"
                    )
                except Exception:
                    pass
                try:
                    await self.metrics_collector.record_portfolio_update(
                        portfolio_id=f"paper:{signal.strategy_id}",
                        update_data=pnl.model_dump(mode="json"),
                        broker_context="paper",
                    )
                except Exception:
                    pass
            if self.prom_metrics:
                self.prom_metrics.set_last_activity("paper_trading", "orders", "paper")
                self.prom_metrics.set_last_activity("paper_trading", "portfolio", "paper")
                # Paper cash and PnL gauges
                try:
                    cash_val = float(self._cash.get(signal.strategy_id, Decimal("0")))
                    self.prom_metrics.set_paper_cash_balance(signal.strategy_id, "paper", cash_val)
                except Exception:
                    pass
        except Exception as e:
            self.error_logger.error("Failed to emit paper order filled", error=str(e), broker="paper")

        # Phase 4: record observability metrics for visibility during rollout
        try:
            if self.prom_metrics:
                self.prom_metrics.record_event_processed("paper_trading", "paper", EventType.ORDER_FILLED.value)
                self.prom_metrics.record_event_processed("paper_trading", "paper", EventType.PNL_SNAPSHOT.value)
            # Redis last activity recorded via record_* above
        except Exception:
            pass

        # Record fill latency once per message
        if self.prom_metrics and _handle_started is not None:
            try:
                import time as _t
                self.prom_metrics.record_paper_fill_latency(signal.strategy_id, "paper", _t.perf_counter() - _handle_started)
            except Exception:
                pass

    async def _emit_order_failed(self, signal: TradingSignal, validated: ValidatedSignal, reason: str) -> None:
        """Emit an order failed event for unfillable or TIF-rejected orders."""
        try:
            producer = await self._get_producer()
            topic = TopicMap("paper").orders_failed()
            order_id = generate_event_id()
            from datetime import datetime, timezone
            failed = OrderFailed(
                strategy_id=signal.strategy_id,
                instrument_token=signal.instrument_token,
                signal_type=signal.signal_type,
                quantity=validated.validated_quantity,
                price=validated.validated_price or signal.price,
                order_id=order_id,
                execution_mode=ExecutionMode.PAPER,
                error_message=reason,
                timestamp=validated.timestamp,
                broker="paper",
            )
            key = PartitioningKeys.order_key(signal.strategy_id, signal.instrument_token, str(validated.timestamp))
            await producer.send(
                topic=topic,
                key=key,
                data=failed.model_dump(mode="json"),
                event_type=EventType.ORDER_FAILED,
                broker="paper",
            )
            self.logger.info("Emitted paper order failed", reason=reason, topic=topic)
            if self.prom_metrics:
                self.prom_metrics.set_last_activity("paper_trading", "orders_failed", "paper")
                try:
                    order_type = (signal.metadata or {}).get("order_type", "market")
                    self.prom_metrics.record_order_executed("paper", str(order_type), "failed")
                except Exception:
                    pass
        except Exception as e:
            self.error_logger.error("Failed to emit paper order failed", error=str(e), broker="paper")

    # -------------------- Portfolio & Bracket Helpers (Phase 3) --------------------
    def _apply_fill_to_portfolio(self, strategy_id: str, instrument_token: int, side: SignalType, qty: int, price: Decimal, fees: Decimal | None) -> None:
        key = (strategy_id, int(instrument_token))
        pos = self._positions.get(key, {"qty": 0, "avg_price": Decimal("0")})
        q = int(pos["qty"])  # type: ignore[index]
        avg = Decimal(pos["avg_price"])  # type: ignore[index]
        if side == SignalType.BUY:
            new_qty = q + qty
            new_avg = ((avg * q) + (price * qty)) / Decimal(str(new_qty)) if new_qty > 0 else Decimal("0")
            self._positions[key] = {"qty": new_qty, "avg_price": new_avg}
            # Cash reduction including fees
            total_cost = price * Decimal(qty)
            fee_val = fees or Decimal("0")
            self._cash[strategy_id] = (self._cash.get(strategy_id, Decimal("0")) - total_cost - fee_val)
        else:  # SELL reduces
            new_qty = max(0, q - qty)
            # Realized PnL on SELL
            realized = self._realized.get(key, Decimal("0"))
            realized += (price - avg) * Decimal(qty)
            self._realized[key] = realized
            # Cash increase net of fees
            total_proceeds = price * Decimal(qty)
            fee_val = fees or Decimal("0")
            self._cash[strategy_id] = (self._cash.get(strategy_id, Decimal("0")) + total_proceeds - fee_val)
            if new_qty == 0:
                self._positions[key] = {"qty": 0, "avg_price": Decimal("0")}
            else:
                self._positions[key] = {"qty": new_qty, "avg_price": avg}

        # Setup bracket if configured and opening position from zero
        md = {}
        try:
            # Best-effort: original metadata is not passed here; brackets configured on BUY open only
            md = {}  # placeholder; brackets are set in _handle_validated_signal below
        except Exception:
            pass

    def _set_bracket_if_configured(self, strategy_id: str, instrument_token: int, entry_price: Decimal, md: dict) -> None:
        try:
            if not md.get("bracket") and not (md.get("take_profit_pct") or md.get("stop_loss_pct")):
                return
            tp_pct = float(md.get("take_profit_pct", 0.0) or 0.0)
            sl_pct = float(md.get("stop_loss_pct", 0.0) or 0.0)
            tp = entry_price * Decimal(str(1 + tp_pct / 100.0)) if tp_pct > 0 else None
            sl = entry_price * Decimal(str(1 - sl_pct / 100.0)) if sl_pct > 0 else None
            self._brackets[(strategy_id, int(instrument_token))] = {"tp": tp, "sl": sl}
            self.logger.info("Bracket/OCO set", strategy_id=strategy_id, instrument_token=instrument_token, tp=str(tp), sl=str(sl))
        except Exception:
            pass

    def _compute_realized_pnl_instrument(self, strategy_id: str, instrument_token: int) -> Decimal:
        key = (strategy_id, int(instrument_token))
        return self._realized.get(key, Decimal("0"))

    def _compute_unrealized_pnl_instrument(self, strategy_id: str, instrument_token: int) -> Decimal:
        key = (strategy_id, int(instrument_token))
        pos = self._positions.get(key)
        if not pos:
            return Decimal("0")
        qty = int(pos["qty"])  # type: ignore[index]
        if qty == 0:
            return Decimal("0")
        avg = Decimal(pos["avg_price"])  # type: ignore[index]
        lp = self._last_price.get(int(instrument_token)) or avg
        return (lp - avg) * Decimal(str(qty))

    def _compute_total_pnl_instrument(self, strategy_id: str, instrument_token: int) -> Decimal:
        return self._compute_realized_pnl_instrument(strategy_id, instrument_token) + self._compute_unrealized_pnl_instrument(strategy_id, instrument_token)

    async def _handle_market_tick(self, message: Dict[str, Any], topic: str) -> None:
        # Accept only market_tick
        t = message.get("type")
        if t not in (EventType.MARKET_TICK, EventType.MARKET_TICK.value, "market_tick"):
            return
        data = message.get("data", {})
        inst = int(data.get("instrument_token") or 0)
        if not inst:
            return
        try:
            lp = Decimal(str(data.get("last_price")))
        except Exception:
            return
        self._last_price[inst] = lp

        # Evaluate bracket triggers for this instrument
        # For each strategy that has bracket on this instrument
        to_remove = []
        for (sid, token), br in list(self._brackets.items()):
            if token != inst:
                continue
            tp = br.get("tp")  # type: ignore[assignment]
            sl = br.get("sl")  # type: ignore[assignment]
            key = (sid, token)
            pos = self._positions.get(key)
            if not pos or int(pos["qty"]) <= 0:  # type: ignore[index]
                to_remove.append((sid, token))
                continue
            qty = int(pos["qty"])  # type: ignore[index]
            # Trigger conditions
            trigger = None
            if tp is not None and lp >= tp:
                trigger = ("TP", tp)
            if sl is not None and lp <= sl:
                # If both meet (unlikely), stop-loss priority
                trigger = ("SL", sl)
            if trigger:
                _, price = trigger
                await self._emit_bracket_exit_fill(sid, token, qty, Decimal(price))
                to_remove.append((sid, token))
        for k in to_remove:
            self._brackets.pop(k, None)

        # Evaluate stop/stop-limit triggers for this instrument
        pending_after: list[dict[str, Any]] = []
        for od in self._pending_stops:
            if od.get("instrument_token") != inst:
                pending_after.append(od)
                continue
            stp = od.get("stop_price")
            lim = od.get("limit_price")
            side = od.get("side")
            qty = int(od.get("quantity") or 0)
            if stp is None or qty <= 0:
                continue
            triggered = (lp >= stp) if side == SignalType.BUY else (lp <= stp)
            if not triggered:
                pending_after.append(od)
                continue
            # Execute triggered stop as market/limit
            try:
                # Build a minimal synthetic signal/validated for reuse of emit path
                ts = datetime.now(timezone.utc)
                sig = TradingSignal(
                    strategy_id=od["strategy_id"],
                    instrument_token=inst,
                    signal_type=side,
                    quantity=qty,
                    price=lp,
                    timestamp=ts,
                    confidence=None,
                    metadata={"order_type": ("limit" if lim is not None else "market"), "limit_price": str(lim) if lim is not None else None}
                )
                val = ValidatedSignal(
                    original_signal=sig,
                    validated_quantity=qty,
                    validated_price=lp,
                    risk_checks={"stop_trigger": True},
                    timestamp=ts,
                )
                # Reuse main handler by building message envelope
                await self._handle_validated_signal({"type": EventType.VALIDATED_SIGNAL, "data": val.model_dump(mode="json")}, topic)
            except Exception as e:
                self.error_logger.error("Failed to execute stop order", error=str(e))
        self._pending_stops = pending_after

    async def _emit_bracket_exit_fill(self, strategy_id: str, instrument_token: int, qty: int, price: Decimal) -> None:
        try:
            producer = await self._get_producer()
            topic_out = TopicMap("paper").orders_filled()
            order_id = generate_event_id()
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc)
            filled = OrderFilled(
                order_id=order_id,
                instrument_token=instrument_token,
                quantity=qty,
                fill_price=price,
                timestamp=ts,
                broker="paper",
                side=SignalType.SELL,
                strategy_id=strategy_id,
                signal_type=SignalType.SELL,
                execution_mode=ExecutionMode.PAPER,
                fees=None,
            )
            key = PartitioningKeys.order_key(strategy_id, instrument_token, ts.isoformat())
            await producer.send(
                topic=topic_out,
                key=key,
                data=filled.model_dump(mode="json"),
                event_type=EventType.ORDER_FILLED,
                broker="paper",
            )
            # Update portfolio
            self._apply_fill_to_portfolio(strategy_id, instrument_token, SignalType.SELL, qty, price)
            self.logger.info("Bracket exit filled", strategy_id=strategy_id, instrument_token=instrument_token, quantity=qty, price=str(price))
        except Exception as e:
            self.error_logger.error("Failed to emit bracket exit fill", error=str(e))
