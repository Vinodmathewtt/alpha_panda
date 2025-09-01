# Enhanced structured logging with multi-channel support
import sys
import logging
import logging.handlers
import re
import threading
import queue
import time
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any
import structlog

from core.config.settings import Settings
from .channels import (
    LogChannel, 
    get_channel_for_component, 
    get_channel_config,
    create_log_directory_structure,
    get_channel_statistics
)

# Global logger manager instance
_logger_manager: Optional['EnhancedLoggerManager'] = None

# Global flag to prevent duplicate configuration
_enhanced_logging_configured = False


class AnsiStrippingFormatter(logging.Formatter):
    """Formatter that removes ANSI escape codes and emoji from log messages.

    This keeps console pretty-printing intact while ensuring file logs are clean.
    """

    _ansi_re = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

    def format(self, record: logging.LogRecord) -> str:
        original_msg = record.getMessage()
        # Strip ANSI escape codes
        msg = self._ansi_re.sub("", original_msg)
        # Drop non-ASCII characters (e.g., emojis) to keep files plain
        try:
            msg_ascii = msg.encode("ascii", "ignore").decode("ascii")
        except Exception:
            msg_ascii = msg
        # Replace the message and clear args so base formatter handles exc_info, etc.
        record.msg = msg_ascii
        record.args = None
        return super().format(record)


class ChannelFilter(logging.Filter):
    """Filter that routes records to a handler only if they match a channel.

    If the record has a structured `channel` attribute, it must match `expected_channel`.
    If not present, allow selected third-party logger name prefixes (e.g., uvicorn/fastapi) when provided.
    """

    def __init__(self, expected_channel: str, allowed_logger_prefixes: Optional[list[str]] = None):
        super().__init__()
        self.expected_channel = expected_channel
        self.allowed_logger_prefixes = allowed_logger_prefixes or []

    def filter(self, record: logging.LogRecord) -> bool:
        ch = getattr(record, "channel", None)
        if ch is not None:
            return str(ch) == self.expected_channel
        name = getattr(record, "name", "")
        for prefix in self.allowed_logger_prefixes:
            if name.startswith(prefix):
                return True
        return False


class AccessLogEnricherFilter(logging.Filter):
    """Parse uvicorn access log messages and enrich records with structured fields.

    Expected message format (set by api.main access_log_format):
        h=<ip> r="<METHOD PATH PROTO>" s=<status> L=<latency_seconds> a="<user-agent>"
    """

    _re = re.compile(
        r"h=(?P<h>\S+)\s+r=\"(?P<r>[^\"]+)\"\s+s=(?P<s>\d{3})\s+L=(?P<L>[0-9.]+)\s+a=\"(?P<a>[^\"]*)\""
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if getattr(record, "name", "") != "uvicorn.access":
                return True
            # Idempotency: if already enriched, skip
            if hasattr(record, "http_method"):
                return True
            msg = record.getMessage()
            m = self._re.search(str(msg))
            if not m:
                return True
            groups = m.groupdict()
            req = groups.get("r", "")
            parts = req.split()
            method, path, proto = (parts + [None, None, None])[:3]
            setattr(record, "access_client_ip", groups.get("h"))
            setattr(record, "http_method", method)
            setattr(record, "http_path", path)
            setattr(record, "http_protocol", proto)
            setattr(record, "http_status", int(groups.get("s") or 0))
            # Convert latency seconds to ms
            try:
                latency_ms = float(groups.get("L") or 0.0) * 1000.0
            except Exception:
                latency_ms = None
            setattr(record, "http_duration_ms", latency_ms)
            setattr(record, "user_agent", groups.get("a"))
            # Provide a concise event label
            setattr(record, "event", "http_access")
            # Try to add correlation/request IDs from context
            try:
                from core.logging.correlation import CorrelationIdManager
                cid = CorrelationIdManager.get_correlation_id()
                if cid:
                    setattr(record, "correlation_id", cid)
                ctx = CorrelationIdManager.get_correlation_context()
                rid = ctx.get("request_id") if isinstance(ctx, dict) else None
                if rid:
                    setattr(record, "request_id", rid)
            except Exception:
                pass
        except Exception:
            # Do not block logging on parsing failures
            return True
        return True


class EnhancedLoggerManager:
    """Enhanced logging manager with multi-channel support and configurable formats."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.channel_handlers: Dict[LogChannel, logging.Handler] = {}
        self.configured_loggers: Dict[str, structlog.BoundLogger] = {}
        
        # Set up logging
        self._setup_logging()
        
    def _setup_logging(self) -> None:
        """Setup enhanced logging with configurable formats."""
        # Create logs directory
        if self.settings.logging.file_enabled:
            create_log_directory_structure(self.settings.logs_dir)
        
        # Configure console logging
        self._setup_console_logging()
        
        # Configure file logging
        if self.settings.logging.file_enabled:
            self._setup_file_logging()
            
        # Configure multi-channel logging if enabled
        if self.settings.logging.multi_channel_enabled:
            self._setup_multi_channel_logging()
            
        # Configure structlog
        self._configure_structlog()

        # Optionally enable async logging via queue for root handlers
        if getattr(self.settings.logging, "queue_enabled", True):
            self._enable_queue_logging()

        # Start background maintenance for log archival/compression if enabled
        if getattr(self.settings.logging, "auto_cleanup_enabled", True):
            self._start_log_maintenance_thread()
    
    def _setup_console_logging(self) -> None:
        """Setup console logging with configurable format."""
        if not self.settings.logging.console_enabled:
            # If console is disabled, remove any existing stdout console handlers (e.g., added by uvicorn)
            root_logger = logging.getLogger()
            to_remove = []
            for handler in root_logger.handlers:
                if isinstance(handler, logging.StreamHandler) and getattr(handler, "stream", None) == sys.stdout:
                    to_remove.append(handler)
            for h in to_remove:
                root_logger.removeHandler(h)
            return
            
        root_logger = logging.getLogger()
        
        # If a console handler already exists (e.g., set by uvicorn), reconfigure it
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and getattr(handler, "stream", None) == sys.stdout:
                handler.setLevel(getattr(logging, self.settings.logging.level.upper()))
                foreign_chain = [
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.add_logger_name,
                    structlog.processors.TimeStamper(fmt="iso"),
                ]
                console_processor = (
                    structlog.processors.JSONRenderer()
                    if self.settings.logging.console_json_format
                    else structlog.dev.ConsoleRenderer()
                )
                handler.setFormatter(
                    structlog.stdlib.ProcessorFormatter(
                        processor=console_processor,
                        foreign_pre_chain=foreign_chain,
                    )
                )
                # Ensure root level matches desired level
                root_logger.setLevel(getattr(logging, self.settings.logging.level.upper()))
                return  # Reconfigured existing console handler; no need to add another
            
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.settings.logging.level.upper()))
        
        # Use structlog ProcessorFormatter for console rendering
        foreign_chain = [
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
        ]
        console_processor = (
            structlog.processors.JSONRenderer()
            if self.settings.logging.console_json_format
            else structlog.dev.ConsoleRenderer()
        )
        console_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=console_processor,
                foreign_pre_chain=foreign_chain,
            )
        )
        
        # Add to root logger
        root_logger.addHandler(console_handler)
        root_logger.setLevel(getattr(logging, self.settings.logging.level.upper()))
    
    def _setup_file_logging(self) -> None:
        """Setup basic file logging."""
        if not self.settings.logging.file_enabled:
            return
            
        logs_dir = Path(self.settings.logs_dir)
        log_file = logs_dir / "alpha_panda.log"
        
        root_logger = logging.getLogger()
        
        # Check if file handler already exists for this file
        for handler in root_logger.handlers:
            if (isinstance(handler, logging.handlers.RotatingFileHandler) and 
                hasattr(handler, 'baseFilename') and 
                Path(handler.baseFilename) == log_file):
                return  # File handler already configured
        
        max_bytes = self._parse_size(self.settings.logging.file_max_size)
        
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=self.settings.logging.file_backup_count,
            encoding="utf-8"
        )
        
        file_handler.setLevel(getattr(logging, self.settings.logging.level.upper()))
        
        # Use structlog ProcessorFormatter for files (prefer JSON)
        foreign_chain = [
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
        ]
        file_processor = (
            structlog.processors.JSONRenderer()
            if getattr(self.settings.logging, "json_format", True)
            else structlog.processors.KeyValueRenderer(key_order=["event", "level", "timestamp"])
        )
        file_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=file_processor,
                foreign_pre_chain=foreign_chain,
            )
        )
        
        # Add to root logger (may be replaced by QueueHandler later)
        root_logger.addHandler(file_handler)
    
    def _setup_multi_channel_logging(self) -> None:
        """Setup multi-channel logging with dedicated files."""
        # Multi-channel handlers are file-backed; respect both multi_channel_enabled and file_enabled
        if not self.settings.logging.multi_channel_enabled or not self.settings.logging.file_enabled:
            return
            
        # Setup handlers for each channel
        for channel in LogChannel:
            config = get_channel_config(channel)
            handler = self._create_channel_handler(channel, config)
            self.channel_handlers[channel] = handler

        # Wire important channels to well-known third-party loggers
        # 1) API channel -> uvicorn/fastapi loggers
        api_handler = self.channel_handlers.get(LogChannel.API)
        if api_handler:
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
                logger = logging.getLogger(name)
                if api_handler not in logger.handlers:
                    logger.addHandler(api_handler)
                # Prevent duplicate propagation to root when API handler attached
                logger.propagate = False

        # 2) ERROR channel -> attach to root to capture all ERROR+ records
        error_handler = self.channel_handlers.get(LogChannel.ERROR)
        if error_handler:
            error_handler.setLevel(logging.ERROR)
            root_logger = logging.getLogger()
            if error_handler not in root_logger.handlers:
                root_logger.addHandler(error_handler)

        # 3) DATABASE channel -> attach to SQLAlchemy loggers
        db_handler = self.channel_handlers.get(LogChannel.DATABASE)
        if db_handler:
            for name in (
                "sqlalchemy",
                "sqlalchemy.engine",
                "sqlalchemy.pool",
                "sqlalchemy.orm",
            ):
                lg = logging.getLogger(name)
                if db_handler not in lg.handlers:
                    lg.addHandler(db_handler)
                # Keep level conservative unless raised via settings
                if lg.level == logging.NOTSET:
                    lg.setLevel(logging.WARNING)
                lg.propagate = False

        # 4) APPLICATION channel -> attach to aiokafka/kafka infrastructure
        app_handler = self.channel_handlers.get(LogChannel.APPLICATION)
        if app_handler:
            for name in ("aiokafka", "kafka"):
                lg = logging.getLogger(name)
                if app_handler not in lg.handlers:
                    lg.addHandler(app_handler)
                if lg.level == logging.NOTSET:
                    lg.setLevel(logging.WARNING)
                lg.propagate = False
    
    def _create_channel_handler(self, channel: LogChannel, config) -> logging.Handler:
        """Create a file handler for a specific channel."""
        log_file = config.get_file_path(self.settings.logs_dir)
        max_bytes = self._parse_size(config.max_bytes)
        
        handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8"
        )
        
        handler.setLevel(getattr(logging, config.level))
        
        # Channel files use structlog ProcessorFormatter (JSON by default)
        foreign_chain = [
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
        ]
        channel_processor = (
            structlog.processors.JSONRenderer()
            if getattr(self.settings.logging, "json_format", True)
            else structlog.processors.KeyValueRenderer(key_order=["event", "level", "timestamp"])
        )
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=channel_processor,
                foreign_pre_chain=foreign_chain,
            )
        )
        # Attach channel filter to avoid cross-channel duplication
        allowed_prefixes = []
        if channel == LogChannel.API:
            allowed_prefixes = ["uvicorn", "fastapi", "starlette"]
        # Don't filter error handler attached to root; keep all ERROR+ (added above in _setup_multi_channel_logging)
        if channel != LogChannel.ERROR:
            handler.addFilter(ChannelFilter(expected_channel=channel.value, allowed_logger_prefixes=allowed_prefixes))
            # Enrich uvicorn access logs with structured HTTP fields for API channel
            if channel == LogChannel.API:
                handler.addFilter(AccessLogEnricherFilter())
        
        return handler

    # --- Async logging via queue ---
    def _enable_queue_logging(self) -> None:
        """Route root logging through a QueueHandler and spin up a QueueListener."""
        root_logger = logging.getLogger()
        # Collect existing root handlers
        target_handlers = list(root_logger.handlers)
        if not target_handlers:
            return
        # Remove them from root; they will be driven by the listener
        for h in target_handlers:
            root_logger.removeHandler(h)

        qmax = max(1000, int(getattr(self.settings.logging, "queue_maxsize", 10000) or 10000))
        self._log_queue: queue.Queue = queue.Queue(maxsize=qmax)

        # Prometheus metrics (best-effort; uses default registry)
        try:
            from prometheus_client import Counter, Gauge
            self._metrics_enabled = True
            self._metric_queue_dropped = Counter(
                "logging_queue_dropped_total",
                "Total log records dropped due to queue overflow",
                namespace="alpha_panda",
                subsystem="logging",
            )
            self._metric_queue_size = Gauge(
                "logging_queue_size",
                "Current logging queue size",
                namespace="alpha_panda",
                subsystem="logging",
            )
            self._metric_queue_capacity = Gauge(
                "logging_queue_capacity",
                "Logging queue capacity",
                namespace="alpha_panda",
                subsystem="logging",
            )
            self._metric_queue_capacity.set(qmax)
        except Exception:
            self._metrics_enabled = False
            self._metric_queue_dropped = None
            self._metric_queue_size = None

        class _SafeQueueHandler(logging.handlers.QueueHandler):
            def __init__(self, q, mgr: 'EnhancedLoggerManager'):
                super().__init__(q)
                self._mgr = mgr

            def emit(self, record: logging.LogRecord) -> None:
                try:
                    self.enqueue(record)
                except Exception as e:
                    # Queue full or other error — track drops
                    if isinstance(e, queue.Full):
                        try:
                            self._mgr._queue_dropped += 1
                            if self._mgr._metrics_enabled and self._mgr._metric_queue_dropped:
                                self._mgr._metric_queue_dropped.inc()
                        except Exception:
                            pass

        self._queue_dropped = 0
        qh = _SafeQueueHandler(self._log_queue, self)
        qh.setLevel(root_logger.level)
        root_logger.addHandler(qh)

        # Listener thread forwards to original handlers
        self._queue_listener = logging.handlers.QueueListener(
            self._log_queue, *target_handlers, respect_handler_level=True
        )
        self._queue_listener.daemon = True
        self._queue_listener.start()

        # Start metrics updater thread if metrics available
        if self._metrics_enabled and self._metric_queue_size is not None:
            self._start_logging_metrics_thread()

    def _start_logging_metrics_thread(self) -> None:
        def _metrics_worker():
            while True:
                try:
                    size = self._log_queue.qsize()
                    if self._metric_queue_size:
                        self._metric_queue_size.set(size)
                except Exception:
                    pass
                time.sleep(5)

        t = threading.Thread(target=_metrics_worker, name="log-metrics", daemon=True)
        t.start()
        self._metrics_thread = t

    # --- Log archival and compression ---
    def _start_log_maintenance_thread(self) -> None:
        """Start a background daemon thread to compress and prune logs."""
        self._stop_maintenance = False

        def _worker():
            while not getattr(self, "_stop_maintenance", False):
                try:
                    self._perform_log_maintenance()
                except Exception:
                    pass
                time.sleep(6 * 60 * 60)  # every 6 hours

        t = threading.Thread(target=_worker, name="log-maintenance", daemon=True)
        t.start()
        self._maintenance_thread = t

    def _perform_log_maintenance(self) -> None:
        """Compress older logs and enforce retention policies."""
        logs_path = Path(self.settings.logs_dir)
        if not logs_path.exists():
            return

        compression_enabled = getattr(self.settings.logging, "compression_enabled", True)
        compress_age_days = int(getattr(self.settings.logging, "compression_age_days", 7) or 7)
        compress_before = datetime.utcnow() - timedelta(days=compress_age_days)

        # Build retention map from channel configs
        retention_by_prefix: Dict[str, int] = {}
        for ch in LogChannel:
            cfg = get_channel_config(ch)
            if cfg.retention_days:
                retention_by_prefix[cfg.filename] = int(cfg.retention_days)

        archived_dir = logs_path / "archived"
        archived_dir.mkdir(exist_ok=True)

        for p in logs_path.iterdir():
            if not p.is_file():
                continue
            if p.name.endswith(".gz"):
                # Already compressed; apply retention below
                pass
            # Skip active primary log files (*.log)
            if p.suffix == ".log" and p.name.count(".") == 1:
                continue

            try:
                mtime = datetime.utcfromtimestamp(p.stat().st_mtime)
            except Exception:
                continue

            # Compression step for rotated logs
            if compression_enabled and not str(p).endswith(".gz") and mtime < compress_before:
                dest = archived_dir / (p.name + ".gz")
                try:
                    with open(p, "rb") as f_in, gzip.open(dest, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    p.unlink(missing_ok=True)
                except Exception:
                    # Best-effort; continue
                    pass

        # Retention enforcement for archived files
        now = datetime.utcnow()
        for p in archived_dir.iterdir():
            if not p.is_file():
                continue
            # Determine retention days by matching channel filename prefix
            retention_days = 30  # default
            for fname, days in retention_by_prefix.items():
                if p.name.startswith(fname):
                    retention_days = days
                    break
            try:
                mtime = datetime.utcfromtimestamp(p.stat().st_mtime)
                if (now - mtime).days > retention_days:
                    p.unlink(missing_ok=True)
            except Exception:
                pass
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size string (e.g., '100MB') to bytes."""
        size_str = size_str.upper()
        
        if size_str.endswith("B"):
            size_str = size_str[:-1]
        
        multipliers = {
            "K": 1024,
            "M": 1024 * 1024,
            "G": 1024 * 1024 * 1024,
        }
        
        for suffix, multiplier in multipliers.items():
            if size_str.endswith(suffix):
                return int(float(size_str[:-1]) * multiplier)
        
        return int(size_str)
    
    def _configure_structlog(self) -> None:
        """Configure structlog with appropriate processors."""

        def add_correlation_id(logger, name, event_dict):
            """Add correlation ID to log events if available"""
            try:
                from core.logging.correlation import CorrelationIdManager
                correlation_id = CorrelationIdManager.get_correlation_id()
                if correlation_id:
                    event_dict['correlation_id'] = correlation_id
                    
                    # Also add correlation context if available
                    correlation_context = CorrelationIdManager.get_correlation_context()
                    if correlation_context:
                        event_dict['correlation_context'] = correlation_context
            except ImportError:
                # Correlation module not available, skip
                pass
            return event_dict

        def add_standard_context(logger, name, event_dict):
            """Bind standard context fields once from settings."""
            try:
                env = getattr(self.settings, 'environment', None)
                app_name = getattr(self.settings, 'app_name', None)
                version = getattr(self.settings, 'version', None)
                if env is not None:
                    event_dict.setdefault('env', str(env))
                if app_name:
                    event_dict.setdefault('service', app_name)
                if version:
                    event_dict.setdefault('version', version)
            except Exception:
                pass
            return event_dict

        def redact_sensitive(logger, name, event_dict):
            """Redact sensitive fields from event dict recursively."""
            # Prefer configured list if present; otherwise default list
            try:
                configured = getattr(self.settings.logging, 'redact_keys', None)
            except Exception:
                configured = None
            keys_to_redact = set(
                (configured or [
                    'authorization', 'access_token', 'refresh_token', 'api_key', 'api-secret', 'api_secret',
                    'password', 'secret', 'token', 'set-cookie'
                ])
            )

            def _redact(obj):
                if isinstance(obj, dict):
                    out = {}
                    for k, v in obj.items():
                        if isinstance(k, str) and k.lower() in keys_to_redact:
                            out[k] = '[REDACTED]'
                        else:
                            out[k] = _redact(v)
                    return out
                if isinstance(obj, list):
                    return [_redact(v) for v in obj]
                return obj

            return _redact(event_dict)

        def normalize_error(logger, name, event_dict):
            """Add normalized error fields if exception info is present."""
            try:
                # If structured exception already present as text
                exc_text = event_dict.get("exception")
                if exc_text and isinstance(exc_text, str):
                    event_dict.setdefault("stack", exc_text)
                    # Best-effort extract of error_type and message
                    first_line = exc_text.splitlines()[0] if exc_text else ""
                    if ":" in first_line:
                        etype, emsg = first_line.split(":", 1)
                        event_dict.setdefault("error_type", etype.strip())
                        event_dict.setdefault("error_message", emsg.strip())
                # Map common fields
                if "error" in event_dict and not event_dict.get("error_message"):
                    event_dict["error_message"] = str(event_dict["error"])
            except Exception:
                pass
            return event_dict

        processors = [
            add_correlation_id,  # Add correlation ID processor first
            add_standard_context,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            normalize_error,
            structlog.processors.UnicodeDecoder(),
            redact_sensitive,
        ]
        
        # Defer final rendering to handlers via ProcessorFormatter
        processors.append(structlog.stdlib.ProcessorFormatter.wrap_for_formatter)
        
        structlog.configure(
            processors=processors,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    def get_logger(self, name: str, component: Optional[str] = None) -> structlog.BoundLogger:
        """Get a structured logger for a component."""
        if name in self.configured_loggers:
            return self.configured_loggers[name]
            
        logger = structlog.get_logger(name)
        
        # Add component context if provided
        if component:
            logger = logger.bind(component=component)
            
            # If multi-channel logging is enabled, add channel-specific handler
            if self.settings.logging.multi_channel_enabled:
                channel = get_channel_for_component(component)
                if channel in self.channel_handlers:
                    # Add channel-specific logging
                    stdlib_logger = logging.getLogger(name)
                    if self.channel_handlers[channel] not in stdlib_logger.handlers:
                        stdlib_logger.addHandler(self.channel_handlers[channel])
        
        self.configured_loggers[name] = logger
        return logger
    
    def get_channel_logger(self, name: str, channel: LogChannel) -> structlog.BoundLogger:
        """Get a logger for a specific channel."""
        logger = self.get_logger(name)
        
        # Add channel context
        logger = logger.bind(channel=channel.value)
        
        # Add channel-specific handler if available
        if channel in self.channel_handlers:
            stdlib_logger = logging.getLogger(name)
            if self.channel_handlers[channel] not in stdlib_logger.handlers:
                stdlib_logger.addHandler(self.channel_handlers[channel])
        
        return logger
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get logging statistics."""
        stats = {
            "total_loggers": len(self.configured_loggers),
            "multi_channel_enabled": self.settings.logging.multi_channel_enabled,
            "file_logging_enabled": self.settings.logging.file_enabled,
            "console_logging_enabled": self.settings.logging.console_enabled,
            "json_format": self.settings.logging.json_format,
            "console_json_format": self.settings.logging.console_json_format,
            "logs_directory": self.settings.logs_dir,
            "queue_enabled": getattr(self.settings.logging, "queue_enabled", True),
        }

        if self.settings.logging.multi_channel_enabled:
            stats.update(get_channel_statistics())
            
        # Queue stats
        try:
            q = getattr(self, "_log_queue", None)
            stats.update({
                "queue_size": (q.qsize() if q is not None else None),
                "queue_capacity": getattr(self, "_metric_queue_capacity", None) and getattr(self, "_metric_queue_capacity")._value.get(),
                "queue_dropped": getattr(self, "_queue_dropped", 0),
            })
        except Exception:
            stats.update({"queue_size": None, "queue_capacity": None, "queue_dropped": None})

        # Channel handler status
        channel_status: Dict[str, Any] = {}
        for ch in LogChannel:
            cfg = get_channel_config(ch)
            channel_status[ch.value] = {
                "filename": str(cfg.filename),
                "level": cfg.level,
                "attached": ch in self.channel_handlers,
            }
        stats["channel_handlers"] = channel_status

        return stats


def configure_enhanced_logging(settings: Settings) -> None:
    """Configure enhanced logging system."""
    global _logger_manager, _enhanced_logging_configured
    
    # Prevent duplicate configuration
    if _enhanced_logging_configured:
        return
    
    _logger_manager = EnhancedLoggerManager(settings)
    _enhanced_logging_configured = True


def get_enhanced_logger(name: str, component: Optional[str] = None) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    global _logger_manager
    
    if _logger_manager is None:
        # Fallback to basic structlog configuration
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=logging.INFO,
        )
        
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        logger = structlog.get_logger(name)
        if component:
            logger = logger.bind(component=component)
        return logger
    
    return _logger_manager.get_logger(name, component)


def get_channel_logger(name: str, channel: LogChannel) -> structlog.BoundLogger:
    """Get a logger for a specific channel."""
    global _logger_manager
    
    if _logger_manager is None:
        return get_enhanced_logger(name)
        
    return _logger_manager.get_channel_logger(name, channel)


def get_logging_statistics() -> Dict[str, Any]:
    """Get logging system statistics."""
    global _logger_manager
    
    if _logger_manager is None:
        return {"error": "Logger manager not initialized"}
        
    return _logger_manager.get_statistics()


# Convenience functions for specific components
def get_trading_logger(name: str) -> structlog.BoundLogger:
    """Get a trading-specific logger."""
    return get_channel_logger(name, LogChannel.TRADING)


def get_market_data_logger(name: str) -> structlog.BoundLogger:
    """Get a market data logger."""
    return get_channel_logger(name, LogChannel.MARKET_DATA)


def get_api_logger(name: str) -> structlog.BoundLogger:
    """Get an API logger."""
    return get_channel_logger(name, LogChannel.API)


def get_audit_logger(name: str) -> structlog.BoundLogger:
    """Get an audit logger."""
    return get_channel_logger(name, LogChannel.AUDIT)


def get_performance_logger(name: str) -> structlog.BoundLogger:
    """Get a performance logger."""
    return get_channel_logger(name, LogChannel.PERFORMANCE)


def get_monitoring_logger(name: str) -> structlog.BoundLogger:
    """Get a monitoring logger."""
    return get_channel_logger(name, LogChannel.MONITORING)


def get_error_logger(name: str) -> structlog.BoundLogger:
    """Get an error logger."""
    return get_channel_logger(name, LogChannel.ERROR)


# Safe logger functions with fallback
def get_api_logger_safe(name: str) -> structlog.BoundLogger:
    """Get an API logger with safe fallback."""
    try:
        return get_api_logger(name)
    except Exception:
        return get_enhanced_logger(name, "api")


def get_audit_logger_safe(name: str) -> structlog.BoundLogger:
    """Get an audit logger with safe fallback."""
    try:
        return get_audit_logger(name)
    except Exception:
        return get_enhanced_logger(name, "audit")


def get_performance_logger_safe(name: str) -> structlog.BoundLogger:
    """Get a performance logger with safe fallback."""
    try:
        return get_performance_logger(name)
    except Exception:
        return get_enhanced_logger(name, "performance")


def get_error_logger_safe(name: str) -> structlog.BoundLogger:
    """Get an error logger with safe fallback."""
    try:
        return get_error_logger(name)
    except Exception:
        return get_enhanced_logger(name, "error")


def get_trading_logger_safe(name: str) -> structlog.BoundLogger:
    """Get a trading logger with safe fallback."""
    try:
        return get_trading_logger(name)
    except Exception:
        return get_enhanced_logger(name, "trading")


def get_monitoring_logger_safe(name: str) -> structlog.BoundLogger:
    """Get a monitoring logger with safe fallback."""
    try:
        return get_monitoring_logger(name)
    except Exception:
        return get_enhanced_logger(name, "monitoring")


def get_database_logger_safe(name: str) -> structlog.BoundLogger:
    """Get a database logger with safe fallback."""
    try:
        return get_channel_logger(name, LogChannel.DATABASE)
    except Exception:
        return get_enhanced_logger(name, "database")
