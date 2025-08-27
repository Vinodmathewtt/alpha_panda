"""Dashboard configuration settings."""

from pydantic import BaseModel


class DashboardSettings(BaseModel):
    """Dashboard-specific configuration"""
    # General settings
    enabled: bool = True
    title: str = "Alpha Panda Dashboard"
    theme: str = "corporate"  # DaisyUI theme
    # Update intervals (seconds)
    health_update_interval: int = 10
    pipeline_update_interval: int = 5
    log_update_interval: int = 1
    portfolio_update_interval: int = 30
    # Display settings
    max_log_entries: int = 1000
    chart_data_points: int = 20
    activity_feed_items: int = 50
    # Real-time settings
    enable_sse: bool = True
    enable_websocket_fallback: bool = True
    # Security
    require_authentication: bool = True
    session_timeout_minutes: int = 60
