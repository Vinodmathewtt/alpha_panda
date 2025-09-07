import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer
from core.logging import get_logger
from core.config.settings import RedpandaSettings
from core.schemas.events import EventEnvelope, EventType
from core.schemas.topics import TopicNames
from core.observability.tracing import get_tracer, inject_headers
from core.utils.ids import generate_event_id
try:
    import orjson  # type: ignore
    _HAS_ORJSON = True
except Exception:  # pragma: no cover
    orjson = None  # type: ignore
    _HAS_ORJSON = False

class MessageProducer:
    """Enhanced message producer with reliability features."""
    
    def __init__(self, config: RedpandaSettings, service_name: str, tuning: Optional[Dict[str, Any]] = None):
        self.config = config
        self.service_name = service_name
        self._producer: Optional[AIOKafkaProducer] = None
        self._running = False
        self._tuning = tuning or {}
        self._logger = get_logger("core.streaming.message_producer", component="streaming")
    
    async def start(self) -> None:
        """Start the producer."""
        if self._running:
            return
        
        # Resolve tuning with safe defaults (preserve current behavior)
        linger_ms = self._tuning.get("linger_ms", 5)
        compression_type = self._tuning.get("compression_type", "gzip")
        batch_size = self._tuning.get("batch_size", None)
        request_timeout_ms = self._tuning.get("request_timeout_ms", 30000)
        max_in_flight_requests = self._tuning.get("max_in_flight_requests", None)

        producer_kwargs = dict(
            bootstrap_servers=self.config.bootstrap_servers,
            client_id=f"{self.config.client_id}-producer-{self.service_name}",
            enable_idempotence=True,
            acks='all',
            request_timeout_ms=request_timeout_ms,
            linger_ms=linger_ms,
            compression_type=compression_type,
            retry_backoff_ms=100,
            value_serializer=self._serialize_value,
        )
        if batch_size is not None:
            producer_kwargs["batch_size"] = batch_size
        if max_in_flight_requests is not None:
            producer_kwargs["max_in_flight_requests"] = max_in_flight_requests

        self._producer = AIOKafkaProducer(**producer_kwargs)
        
        await self._producer.start()
        self._running = True
    
    async def stop(self) -> None:
        """Stop the producer with flush."""
        if not self._running or not self._producer:
            return
        
        try:
            # Ensure all messages are sent before closing
            await self._producer.flush()
            await self._producer.stop()
        except Exception as e:
            # Log but don't raise to prevent shutdown issues
            self._logger.warning(f"Error during producer shutdown: {e}")
        finally:
            self._producer = None
            self._running = False
    
    async def send(self, topic: str, key: str, data: Dict[str, Any], 
                   event_type: Optional[EventType] = None,
                   correlation_id: Optional[str] = None,
                   broker: str = "unknown") -> str:
        """Send message with automatic envelope wrapping."""
        if not self._running:
            await self.start()
        
        # Create event envelope if not already wrapped
        if not isinstance(data, dict) or 'id' not in data:
            event_id = generate_event_id()
            
            # Use provided event_type or attempt to determine from data
            if event_type:
                envelope_type = event_type
            elif 'type' in data:
                # Coerce to EventType when possible; fallback to raw value with validation
                try:
                    envelope_type = EventType(data['type'])
                except Exception:
                    envelope_type = data['type']  # Let schema validation surface issues
            else:
                # No provided type; only default for market tick topics. Otherwise, raise.
                def _is_market_ticks_topic(t: str) -> bool:
                    try:
                        if t in {
                            TopicNames.MARKET_TICKS,
                            TopicNames.MARKET_EQUITY_TICKS,
                            TopicNames.MARKET_CRYPTO_TICKS,
                            TopicNames.MARKET_OPTIONS_TICKS,
                            TopicNames.MARKET_FOREX_TICKS,
                        }:
                            return True
                    except Exception:
                        pass
                    return t.startswith("market.") and t.endswith(".ticks")

                if _is_market_ticks_topic(topic):
                    envelope_type = EventType.MARKET_TICK
                else:
                    self._logger.error(
                        "Missing event_type for non-market topic; refusing to default",
                        extra={
                            "service": self.service_name,
                            "topic": topic,
                            "key": key,
                            "broker": broker,
                        },
                    )
                    raise ValueError(
                        f"event_type is required for non-market topics (service={self.service_name}, topic={topic}, key={key})"
                    )
            
            # Propagate trace fields if provided in data (best-effort)
            trace_id = None
            parent_trace_id = None
            try:
                if isinstance(data, dict):
                    trace_id = data.get('trace_id')
                    parent_trace_id = data.get('parent_trace_id')
            except Exception:
                trace_id = None
                parent_trace_id = None

            envelope = EventEnvelope(
                id=event_id,
                type=envelope_type,
                ts=datetime.now(timezone.utc),
                source=self.service_name,
                key=key,
                correlation_id=correlation_id or generate_event_id(),
                broker=broker,
                data=data,
                trace_id=trace_id or generate_event_id(),
                parent_trace_id=parent_trace_id
            ).model_dump(mode='json')
        else:
            envelope = data
            event_id = data.get('id')
        
        # CRITICAL FIX: Ensure robust key and value handling
        try:
            # Ensure key is a string and can be encoded
            if not isinstance(key, str):
                key = str(key)
            
            # Safely encode key to bytes
            encoded_key = key.encode('utf-8')
            
            # Ensure envelope is JSON-serializable dict/object
            if not isinstance(envelope, (dict, list)):
                raise ValueError(f"Envelope must be dict or list, got {type(envelope)}")
            
            # Inject tracing/correlation headers
            hdrs: Dict[str, str] = {}
            hdrs["trace_id"] = envelope.get("trace_id") if isinstance(envelope, dict) else None  # type: ignore
            hdrs["correlation_id"] = envelope.get("correlation_id") if isinstance(envelope, dict) else None  # type: ignore
            hdrs = {k: v for k, v in hdrs.items() if v}
            hdrs = inject_headers(hdrs)
            kafka_headers = [(k, v.encode("utf-8")) for k, v in hdrs.items()]

            # Start a producer span
            tracer = get_tracer("producer")
            with tracer.start_as_current_span("kafka.produce") as span:
                try:
                    span.set_attribute("messaging.system", "kafka")
                    span.set_attribute("messaging.destination", topic)
                    span.set_attribute("messaging.kafka.partition_key", key)
                    span.set_attribute("messaging.operation", "send")
                    span.set_attribute("broker", broker)
                    span.set_attribute("event.type", envelope.get("type") if isinstance(envelope, dict) else str(event_type))
                except Exception:
                    pass

                await self._producer.send_and_wait(
                    topic=topic,
                    key=encoded_key,
                    value=envelope,  # The value_serializer will handle JSON serialization
                    headers=kafka_headers,
                )
            
        except Exception as send_error:
            # Add detailed error context for debugging
            error_context = {
                "topic": topic,
                "key": key,
                "key_type": type(key).__name__,
                "envelope_type": type(envelope).__name__,
                "service": self.service_name
            }
            
            # Re-raise with context
            raise RuntimeError(f"MessageProducer.send failed: {send_error}. Context: {error_context}") from send_error
        
        return event_id

    @staticmethod
    def _json_serializer(obj):
        """Custom JSON serializer."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle Decimal objects from price fields
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')

    def _serialize_value(self, x: Any) -> bytes:
        """Serialize message value using orjson when available, else stdlib."""
        if _HAS_ORJSON:
            try:
                return orjson.dumps(x, default=self._json_serializer)  # type: ignore[arg-type]
            except Exception:
                return orjson.dumps(x)  # type: ignore[arg-type]
        return json.dumps(x, default=self._json_serializer).encode('utf-8')
