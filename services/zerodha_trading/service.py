from __future__ import annotations

from typing import Any, Dict

from core.config.settings import RedpandaSettings, Settings
from core.logging import (
    get_trading_logger_safe,
    get_error_logger_safe,
)
from core.monitoring.pipeline_metrics import PipelineMetricsCollector
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector
from core.observability.tracing import get_tracer
from core.schemas.events import EventType
from core.schemas.topics import TopicMap
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.trading.utils import get_first_producer_or_raise
from core.schemas.events import TradingSignal, ValidatedSignal, OrderPlaced, ExecutionMode, OrderStatus, PnlSnapshot, EventType
from core.schemas.topics import PartitioningKeys
from core.utils.ids import generate_event_id


class ZerodhaTradingService:
    """Broker-scoped trading orchestrator for 'zerodha'.

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
        self.logger = get_trading_logger_safe("zerodha_trading")
        self.error_logger = get_error_logger_safe("zerodha_trading_errors")
        self.metrics_collector = PipelineMetricsCollector(redis_client, settings, None)
        self.prom_metrics = prometheus_metrics

        # Subscribe only to zerodha.* validated signals
        topics = [TopicMap("zerodha").signals_validated()]

        self.orchestrator = (
            StreamServiceBuilder("zerodha_trading", config, settings)
            .with_prometheus(prometheus_metrics)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=topics,
                group_id=f"{settings.redpanda.group_id_prefix}.zerodha_trading.signals",
                handler_func=self._handle_validated_signal,
            )
            .build()
        )

    async def _get_producer(self):
        return get_first_producer_or_raise(self.orchestrator)

    async def start(self) -> None:
        self.logger.info("ZerodhaTrading starting...")
        await self.orchestrator.start()
        if self.prom_metrics:
            try:
                self.prom_metrics.set_pipeline_health("zerodha_trading", "zerodha", True)
            except Exception:
                pass

    async def stop(self) -> None:
        await self.orchestrator.stop()
        self.logger.info("ZerodhaTrading stopped")

    async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
        """Process validated signals and emit placed events (zerodha)."""
        tracer = get_tracer("zerodha_trading")
        with tracer.start_as_current_span("zerodha_trading.handle_signal") as span:
            try:
                span.set_attribute("broker", "zerodha")
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
            self.error_logger.error("Invalid validated signal payload", error=str(e), broker="zerodha")
            return

        # Record Prom last-activity for signals
        if self.prom_metrics:
            self.prom_metrics.set_last_activity("zerodha_trading", "signals_validated", "zerodha")

        # Emit order placed (ack/submit)
        order_id = generate_event_id()
        placed = OrderPlaced(
            order_id=order_id,
            instrument_token=signal.instrument_token,
            signal_type=signal.signal_type,
            quantity=validated.validated_quantity,
            price=validated.validated_price or signal.price,
            timestamp=validated.timestamp,
            broker="zerodha",
            status=OrderStatus.PLACED,
            strategy_id=signal.strategy_id,
            execution_mode=ExecutionMode.ZERODHA,
        )

        key = PartitioningKeys.order_key(signal.strategy_id, signal.instrument_token, str(validated.timestamp))
        topic_out = TopicMap("zerodha").orders_submitted()

        try:
            producer = await self._get_producer()
            await producer.send(
                topic=topic_out,
                key=key,
                data=placed.model_dump(mode="json"),
                event_type=EventType.ORDER_PLACED,
                broker="zerodha",
            )
            self.logger.info("Emitted zerodha order placed",
                            broker="zerodha", topic=topic_out,
                            strategy_id=signal.strategy_id,
                            instrument_token=signal.instrument_token)

            # Emit a minimal PnL snapshot placeholder (portfolio update might be async downstream)
            pnl = PnlSnapshot(
                broker="zerodha",
                instrument_token=signal.instrument_token,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                total_pnl=0.0,
                timestamp=validated.timestamp,
            )
            await producer.send(
                topic=TopicMap("zerodha").pnl_snapshots(),
                key=f"portfolio_snapshot_zerodha:{signal.strategy_id}",
                data=pnl.model_dump(mode="json"),
                event_type=EventType.PNL_SNAPSHOT,
                broker="zerodha",
            )
            # Update Prom last-activity for orders and portfolio
            if self.prom_metrics:
                self.prom_metrics.set_last_activity("zerodha_trading", "orders", "zerodha")
                self.prom_metrics.set_last_activity("zerodha_trading", "portfolio", "zerodha")
        except Exception as e:
            self.error_logger.error("Failed to emit zerodha order placed", error=str(e), broker="zerodha")

        # Phase 4: record observability metrics for visibility during rollout
        try:
            if self.prom_metrics:
                self.prom_metrics.record_event_processed("zerodha_trading", "zerodha", EventType.ORDER_PLACED.value)
                self.prom_metrics.record_event_processed("zerodha_trading", "zerodha", EventType.PNL_SNAPSHOT.value)
            if self.metrics_collector:
                await self.metrics_collector.set_last_activity_timestamp("orders", "zerodha")
                await self.metrics_collector.set_last_activity_timestamp("portfolio", "zerodha")
        except Exception:
            pass
