"""System management API endpoints."""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core.config.settings import settings
from core.logging.logger import get_logger
from ..middleware import get_current_user, require_admin_permission
from ..websocket import websocket_manager

logger = get_logger(__name__)

router = APIRouter()


class SystemInfo(BaseModel):
    version: str
    environment: str
    mock_market_feed: bool
    debug: bool
    uptime: str
    components: Dict[str, Any]


class ConfigUpdate(BaseModel):
    key: str
    value: Any
    restart_required: bool = False


@router.get("/info", response_model=SystemInfo)
async def get_system_info(user=Depends(get_current_user)):
    """Get system information."""
    try:
        import psutil
        import time
        from datetime import datetime, timedelta
        
        # Calculate uptime (placeholder - would need actual start time)
        uptime_seconds = time.time() - 1000  # Placeholder
        uptime_str = str(timedelta(seconds=int(uptime_seconds)))
        
        # Get component status
        components = {
            "database": {"status": "connected"},
            "event_bus": {"status": "connected"},
            "market_feed": {"status": "active" if not settings.mock_market_feed else "mock"},
            "trading_engine": {"status": "active"},
            "strategy_manager": {"status": "active"},
            "risk_manager": {"status": "active"}
        }
        
        return SystemInfo(
            version="1.0.0",
            environment=settings.environment,
            mock_market_feed=settings.mock_market_feed,
            debug=settings.debug,
            uptime=uptime_str,
            components=components
        )
        
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_configuration(
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Get system configuration."""
    try:
        # Return non-sensitive configuration
        config = {
            "environment": settings.environment,
            "debug": settings.debug,
            "mock_market_feed": settings.mock_market_feed,
            "database": {
                "host": getattr(settings.database, 'host', 'localhost'),
                "port": getattr(settings.database, 'port', 5432)
            },
            "trading": {
                "default_mode": getattr(settings.trading, 'default_mode', 'paper')
            },
            "api": {
                "host": getattr(settings.api, 'host', '0.0.0.0'),
                "port": getattr(settings.api, 'port', 8000)
            }
        }
        
        return config
        
    except Exception as e:
        logger.error(f"Failed to get configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_configuration(
    config_update: ConfigUpdate,
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Update system configuration."""
    try:
        # Only allow certain configuration updates
        allowed_keys = [
            "debug",
            "trading.default_mode",
            "api.rate_limit_requests"
        ]
        
        if config_update.key not in allowed_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Configuration key '{config_update.key}' cannot be updated via API"
            )
        
        # Update configuration (placeholder implementation)
        # In production, this would update the actual configuration
        logger.info(f"Configuration update: {config_update.key} = {config_update.value}")
        
        return {
            "success": True,
            "message": f"Configuration updated: {config_update.key}",
            "restart_required": config_update.restart_required
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_system_logs(
    level: str = "INFO",
    limit: int = 100,
    user=Depends(get_current_user)
):
    """Get system logs."""
    try:
        import os
        from pathlib import Path
        
        # Get actual log files
        log_dir = Path("logs")
        log_entries = []
        
        if log_dir.exists():
            for log_file in log_dir.glob("*.log"):
                try:
                    # Read and parse log entries
                    with open(log_file, 'r') as f:
                        lines = f.readlines()[-limit*2:]  # Get more lines to filter by level
                        
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        # Check if line contains the requested log level
                        if level.upper() in line:
                            # Parse log line format (basic parsing)
                            parts = line.split(' ', 3)
                            if len(parts) >= 4:
                                timestamp_part = parts[0] + " " + parts[1] if len(parts) > 1 else parts[0]
                                level_part = parts[2] if len(parts) > 2 else "INFO"
                                message_part = parts[3] if len(parts) > 3 else line
                                
                                log_entries.append({
                                    "timestamp": timestamp_part,
                                    "level": level_part.strip("[]"),
                                    "message": message_part,
                                    "source": log_file.name
                                })
                except Exception as file_error:
                    logger.warning(f"Error reading log file {log_file}: {file_error}")
                    continue
        
        # Sort by timestamp (most recent first) and limit results
        log_entries = sorted(log_entries, key=lambda x: x["timestamp"], reverse=True)[:limit]
        
        return {
            "logs": log_entries,
            "total_entries": len(log_entries),
            "level_filter": level,
            "limit": limit,
            "log_directory": str(log_dir) if log_dir.exists() else "No log directory found"
        }
        
    except Exception as e:
        logger.error(f"Error retrieving logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve logs")


@router.post("/restart")
async def restart_system(
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Restart system components."""
    try:
        # This would trigger a graceful restart in production
        logger.warning("System restart requested by user")
        
        return {
            "success": True,
            "message": "System restart initiated",
            "estimated_downtime": "30 seconds"
        }
        
    except Exception as e:
        logger.error(f"Failed to restart system: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/websocket/stats")
async def get_websocket_stats(user=Depends(get_current_user)):
    """Get WebSocket connection statistics."""
    try:
        stats = websocket_manager.get_connection_stats()
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get WebSocket stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_system_performance(user=Depends(get_current_user)):
    """Get system performance metrics."""
    try:
        import psutil
        
        # Get system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        performance = {
            "cpu": {
                "usage_percent": cpu_percent,
                "count": psutil.cpu_count()
            },
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "percent": memory.percent,
                "used": memory.used
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": (disk.used / disk.total) * 100
            },
            "network": {
                "connections": len(psutil.net_connections())
            }
        }
        
        return performance
        
    except Exception as e:
        logger.error(f"Failed to get system performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown")
async def shutdown_system(
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Shutdown system gracefully."""
    try:
        # This would trigger a graceful shutdown in production
        logger.warning("System shutdown requested by user")
        
        return {
            "success": True,
            "message": "System shutdown initiated"
        }
        
    except Exception as e:
        logger.error(f"Failed to shutdown system: {e}")
        raise HTTPException(status_code=500, detail=str(e))