"""Log management API endpoints for AlphaPT."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from core.config.settings import settings
from core.logging import get_channel_statistics, MULTI_CHANNEL_AVAILABLE
from core.logging.log_channels import LogChannel, get_all_channels
from core.logging.log_management import (
    LogRotationManager,
    LogAnalyzer,
    LogExporter,
    ensure_log_directory_structure
)
from api.middleware import require_admin_permission


router = APIRouter(prefix="/logs", tags=["logs"])


class LogChannelStatus(BaseModel):
    """Log channel status response."""
    channel: str
    exists: bool
    size_mb: float
    total_size_mb: float
    backup_files_count: int
    last_modified: Optional[datetime]


class LogHealthSummary(BaseModel):
    """Log health summary response."""
    total_channels: int
    healthy_channels: int
    warning_channels: int
    error_channels: int
    channel_details: Dict[str, Dict[str, Any]]


class LogAnalysisResult(BaseModel):
    """Log analysis result response."""
    total_lines: int
    log_levels: Dict[str, int]
    components: Dict[str, int]
    error_count: int
    warning_count: int
    time_range: Dict[str, Optional[str]]
    recent_errors: List[Dict[str, Any]]


class LogCleanupRequest(BaseModel):
    """Log cleanup request."""
    older_than_days: int = Field(default=30, ge=1, le=365)
    dry_run: bool = Field(default=True)


class LogExportRequest(BaseModel):
    """Log export request."""
    channel: str
    format: str = Field(default="json", pattern="^(json|csv)$")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


@router.get("/status", response_model=Dict[str, LogChannelStatus])
async def get_log_status():
    """Get status of all log channels."""
    if not MULTI_CHANNEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="Multi-channel logging not available")
    
    ensure_log_directory_structure(settings)
    rotation_manager = LogRotationManager(settings)
    
    status = rotation_manager.get_all_log_status()
    
    result = {}
    for channel_name, info in status.items():
        result[channel_name] = LogChannelStatus(
            channel=channel_name,
            exists=info['exists'],
            size_mb=info.get('size_mb', 0),
            total_size_mb=info.get('total_size_mb', 0),
            backup_files_count=len(info.get('backup_files', [])),
            last_modified=info.get('modified')
        )
    
    return result


@router.get("/health", response_model=LogHealthSummary)
async def get_log_health():
    """Get log health summary."""
    if not MULTI_CHANNEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="Multi-channel logging not available")
    
    analyzer = LogAnalyzer(settings)
    summary = analyzer.get_log_health_summary()
    
    return LogHealthSummary(**summary)


@router.get("/channels")
async def get_available_channels():
    """Get list of available log channels."""
    if not MULTI_CHANNEL_AVAILABLE:
        return {"error": "Multi-channel logging not available", "channels": []}
    
    channels = {}
    all_channels = get_all_channels()
    
    for channel, config in all_channels.items():
        channels[channel.value] = {
            "name": config.name,
            "file_path": config.file_path,
            "level": config.level,
            "retention_days": config.retention_days,
            "max_bytes": config.max_bytes,
            "backup_count": config.backup_count
        }
    
    return {"channels": channels}


@router.get("/statistics")
async def get_log_statistics():
    """Get channel statistics if available."""
    try:
        stats = get_channel_statistics()
        return stats
    except Exception as e:
        return {"error": str(e), "multi_channel_available": MULTI_CHANNEL_AVAILABLE}


@router.get("/analyze/{channel}", response_model=LogAnalysisResult)
async def analyze_channel_logs(
    channel: str,
    lines: int = Query(default=1000, ge=1, le=10000, description="Number of lines to analyze")
):
    """Analyze logs for a specific channel."""
    if not MULTI_CHANNEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="Multi-channel logging not available")
    
    try:
        log_channel = LogChannel(channel)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid channel: {channel}")
    
    analyzer = LogAnalyzer(settings)
    analysis = analyzer.analyze_channel_logs(log_channel, lines)
    
    if 'error' in analysis:
        raise HTTPException(status_code=500, detail=analysis['error'])
    
    return LogAnalysisResult(**analysis)


@router.post("/cleanup", dependencies=[Depends(require_admin_permission)])
async def cleanup_old_logs(request: LogCleanupRequest):
    """Clean up old log files."""
    if not MULTI_CHANNEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="Multi-channel logging not available")
    
    rotation_manager = LogRotationManager(settings)
    
    if request.dry_run:
        # For dry run, we'd need to implement a preview function
        return {
            "message": "Dry run not implemented yet",
            "dry_run": True,
            "older_than_days": request.older_than_days
        }
    
    cleanup_stats = rotation_manager.cleanup_old_logs(request.older_than_days)
    total_removed = sum(cleanup_stats.values())
    
    return {
        "message": f"Cleaned up {total_removed} files",
        "cleanup_stats": cleanup_stats,
        "older_than_days": request.older_than_days
    }


@router.post("/compress", dependencies=[Depends(require_admin_permission)])
async def compress_old_logs(
    older_than_days: int = Query(default=7, ge=1, le=365, description="Compress files older than N days")
):
    """Compress old log files."""
    if not MULTI_CHANNEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="Multi-channel logging not available")
    
    rotation_manager = LogRotationManager(settings)
    compression_stats = rotation_manager.compress_old_logs(older_than_days)
    total_compressed = sum(compression_stats.values())
    
    return {
        "message": f"Compressed {total_compressed} files",
        "compression_stats": compression_stats,
        "older_than_days": older_than_days
    }


@router.post("/export/{channel}")
async def export_channel_logs(channel: str, request: LogExportRequest):
    """Export logs for a channel."""
    if not MULTI_CHANNEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="Multi-channel logging not available")
    
    try:
        log_channel = LogChannel(channel)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid channel: {channel}")
    
    if request.format not in ["json", "csv"]:
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")
    
    exporter = LogExporter(settings)
    
    time_range = None
    if request.start_date and request.end_date:
        time_range = (request.start_date, request.end_date)
    
    try:
        exported_file = await exporter.export_channel_logs(
            log_channel, request.format, time_range
        )
        
        # Get file size
        file_size = Path(exported_file).stat().st_size
        
        return {
            "message": "Export completed",
            "file_path": exported_file,
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / 1024 / 1024, 2),
            "format": request.format,
            "channel": channel
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/tail/{channel}")
async def tail_channel_logs(
    channel: str,
    lines: int = Query(default=50, ge=1, le=500, description="Number of lines to tail")
):
    """Get the last N lines from a channel's log file."""
    if not MULTI_CHANNEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="Multi-channel logging not available")
    
    try:
        log_channel = LogChannel(channel)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid channel: {channel}")
    
    analyzer = LogAnalyzer(settings)
    analysis = analyzer.analyze_channel_logs(log_channel, lines)
    
    if 'error' in analysis:
        raise HTTPException(status_code=500, detail=analysis['error'])
    
    # Get the actual log lines (simplified version)
    from core.logging.log_channels import get_channel_config
    config = get_channel_config(log_channel)
    log_file = config.get_file_path(settings.logs_dir)
    
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    try:
        # Read last N lines
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return {
            "channel": channel,
            "lines_requested": lines,
            "lines_returned": len(tail_lines),
            "log_lines": [line.strip() for line in tail_lines if line.strip()]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log file: {str(e)}")


@router.get("/search/{channel}")
async def search_channel_logs(
    channel: str,
    query: str = Query(..., description="Search query"),
    lines: int = Query(default=1000, ge=1, le=5000, description="Number of lines to search"),
    case_sensitive: bool = Query(default=False, description="Case sensitive search")
):
    """Search for a pattern in channel logs."""
    if not MULTI_CHANNEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="Multi-channel logging not available")
    
    try:
        log_channel = LogChannel(channel)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid channel: {channel}")
    
    from core.logging.log_channels import get_channel_config
    config = get_channel_config(log_channel)
    log_file = config.get_file_path(settings.logs_dir)
    
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    try:
        matches = []
        line_number = 0
        
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            search_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            for i, line in enumerate(search_lines):
                line_number = len(all_lines) - len(search_lines) + i + 1
                
                # Perform search
                search_line = line if case_sensitive else line.lower()
                search_query = query if case_sensitive else query.lower()
                
                if search_query in search_line:
                    matches.append({
                        "line_number": line_number,
                        "content": line.strip(),
                        "timestamp": None  # Could extract timestamp if needed
                    })
        
        return {
            "channel": channel,
            "query": query,
            "case_sensitive": case_sensitive,
            "lines_searched": len(search_lines),
            "matches_found": len(matches),
            "matches": matches[-100:]  # Limit to last 100 matches
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# Health check for logging system
@router.get("/ping")
async def ping_logging_system():
    """Health check for the logging system."""
    return {
        "status": "ok",
        "multi_channel_available": MULTI_CHANNEL_AVAILABLE,
        "logs_directory": str(settings.logs_dir),
        "logs_directory_exists": settings.logs_dir.exists(),
        "timestamp": datetime.utcnow().isoformat()
    }