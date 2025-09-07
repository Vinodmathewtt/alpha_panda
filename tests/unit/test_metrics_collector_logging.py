import logging
import pytest
import importlib.util
from pathlib import Path

# Import the module directly from file to avoid importing the full
# core.streaming package (which requires aiokafka at import time).
_MODULE_PATH = Path(__file__).parents[2] / "core/streaming/reliability/metrics_collector.py"
spec = importlib.util.spec_from_file_location(
    "metrics_collector", str(_MODULE_PATH)
)
mc_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mc_module)  # type: ignore
MetricsCollector = mc_module.MetricsCollector  # type: ignore


@pytest.mark.asyncio
async def test_metrics_collector_record_success_logs_with_extra(caplog):
    # The loaded module name is "metrics_collector" due to direct file import
    logger_name = getattr(mc_module, "logger").name if hasattr(mc_module, "logger") else mc_module.__name__
    caplog.set_level(logging.DEBUG, logger=logger_name)

    mc = MetricsCollector(service_name="test_service")

    # Should not raise, and should attach duration_ms via `extra`
    await mc.record_success(processing_duration=0.123, broker_context="paper")

    # Find our debug record and verify duration_ms is present
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG and r.name == logger_name]
    assert debug_records, "Expected a DEBUG log record from MetricsCollector.record_success"

    record = debug_records[-1]
    # Message formatting is handled by stdlib logging
    assert "Success recorded for paper" in record.getMessage()
    # Extra field should be attached to the LogRecord
    assert hasattr(record, "duration_ms") and record.duration_ms == pytest.approx(123.0)
