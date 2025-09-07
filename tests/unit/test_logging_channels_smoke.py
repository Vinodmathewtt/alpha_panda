import os
from pathlib import Path

from core.config.settings import Settings
from core.logging import (
    configure_logging,
    get_trading_logger_safe,
    get_market_data_logger_safe,
    get_api_logger_safe,
    get_error_logger_safe,
    get_statistics,
)


def test_logging_channels_write_files(tmp_path):
    # Use a temporary logs directory to avoid polluting repo logs
    logs_dir = tmp_path / "logs"
    os.environ["LOGGING__FILE_ENABLED"] = "true"
    os.environ["LOGGING__MULTI_CHANNEL_ENABLED"] = "true"
    os.environ["LOGGING__QUEUE_ENABLED"] = "false"
    os.environ["LOGGING__LOGS_DIR"] = str(logs_dir)
    os.environ["ENVIRONMENT"] = "testing"

    settings = Settings()
    configure_logging(settings)

    # Log to a few key channels
    get_trading_logger_safe("test").info("trading smoke message")
    get_market_data_logger_safe("test").info("market smoke message")
    get_api_logger_safe("test").info("api smoke message")
    get_error_logger_safe("test").error("error smoke message")

    # Ensure file handlers flush
    import time as _time
    _time.sleep(0.05)

    # Validate files exist
    paths = [
        logs_dir / "trading.log",
        logs_dir / "market_data.log",
        logs_dir / "api.log",
        logs_dir / "error.log",
    ]
    for p in paths:
        assert p.exists(), f"expected log file not found: {p}"
        # Should be non-empty after writes
        assert p.stat().st_size > 0, f"expected log file to have content: {p}"

    # Basic statistics call should not error
    stats = get_statistics()
    assert isinstance(stats, dict)
