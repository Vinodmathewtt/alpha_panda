from fastapi import APIRouter, Depends
from typing import Dict, Any
import platform
import psutil
from datetime import datetime

from api.dependencies import get_settings
from core.config.settings import Settings
from api.schemas.responses import StandardResponse

router = APIRouter(prefix="/system", tags=["System"])

@router.get("/info", response_model=StandardResponse[Dict[str, Any]])
async def get_system_info(
    settings: Settings = Depends(get_settings)
):
    """Get system information and environment details"""
    try:
        # System information
        system_info = {
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version()
            },
            "hardware": {
                "cpu_count": psutil.cpu_count(logical=True),
                "cpu_count_physical": psutil.cpu_count(logical=False),
                "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 2)
            },
            "application": {
                "active_brokers": settings.active_brokers,
                "environment": getattr(settings, 'environment', 'development'),
                "api_version": "2.1.0",
                "startup_time": datetime.utcnow().isoformat()
            }
        }
        
        return StandardResponse(
            status="success",
            data=system_info,
            message="System information retrieved",
            broker=settings.active_brokers[0] if settings.active_brokers else "unknown"
        )
    except Exception as e:
        return StandardResponse(
            status="error",
            message=f"Failed to get system info: {str(e)}",
            broker=settings.active_brokers[0] if settings.active_brokers else "unknown"
        )

@router.get("/metrics", response_model=StandardResponse[Dict[str, Any]])
async def get_system_metrics(
    settings: Settings = Depends(get_settings)
):
    """Get current system resource usage metrics"""
    try:
        # Current system metrics
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        metrics = {
            "cpu": {
                "usage_percent": psutil.cpu_percent(interval=1),
                "load_average": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "usage_percent": memory.percent
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "usage_percent": round((disk.used / disk.total) * 100, 2)
            },
            "network": {
                "connections": len(psutil.net_connections()),
                "stats": dict(psutil.net_io_counters()._asdict()) if hasattr(psutil.net_io_counters(), '_asdict') else {}
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return StandardResponse(
            status="success",
            data=metrics,
            message="System metrics retrieved",
            broker=settings.active_brokers[0] if settings.active_brokers else "unknown"
        )
    except Exception as e:
        return StandardResponse(
            status="error",
            message=f"Failed to get system metrics: {str(e)}",
            broker=settings.active_brokers[0] if settings.active_brokers else "unknown"
        )

@router.get("/processes", response_model=StandardResponse[Dict[str, Any]])
async def get_process_info(
    settings: Settings = Depends(get_settings)
):
    """Get information about running processes"""
    try:
        # Current process info
        current_process = psutil.Process()
        process_info = {
            "current_process": {
                "pid": current_process.pid,
                "name": current_process.name(),
                "status": current_process.status(),
                "cpu_percent": current_process.cpu_percent(),
                "memory_percent": current_process.memory_percent(),
                "memory_info_mb": round(current_process.memory_info().rss / (1024**2), 2),
                "create_time": datetime.fromtimestamp(current_process.create_time()).isoformat(),
                "num_threads": current_process.num_threads(),
                "connections": len(current_process.connections())
            },
            "system_processes": {
                "total_processes": len(psutil.pids()),
                "python_processes": len([p for p in psutil.process_iter(['name']) if 'python' in p.info['name'].lower()]),
                "top_memory_processes": []
            }
        }
        
        # Get top memory consuming processes
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Sort by memory usage and get top 5
        top_processes = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:5]
        process_info["system_processes"]["top_memory_processes"] = top_processes
        
        return StandardResponse(
            status="success",
            data=process_info,
            message="Process information retrieved",
            broker=settings.active_brokers[0] if settings.active_brokers else "unknown"
        )
    except Exception as e:
        return StandardResponse(
            status="error",
            message=f"Failed to get process info: {str(e)}",
            broker=settings.active_brokers[0] if settings.active_brokers else "unknown"
        )

@router.get("/environment", response_model=StandardResponse[Dict[str, Any]])
async def get_environment_info(
    settings: Settings = Depends(get_settings)
):
    """Get environment configuration (non-sensitive)"""
    try:
        env_info = {
            "active_brokers": settings.active_brokers,
            "redis_config": {
                "url": settings.redis.url if hasattr(settings, 'redis') else "unknown"
            },
            "database_config": {
                "postgres_url": settings.database.postgres_url if hasattr(settings, 'database') else "unknown"
            },
            "api_config": {
                "cors_enabled": True,
                "docs_enabled": True,
                "rate_limiting_enabled": True
            },
            "features": {
                "real_time_streaming": True,
                "websocket_support": True,
                "sse_support": True,
                "log_management": True,
                "alert_management": True,
                "service_management": True
            }
        }
        
        return StandardResponse(
            status="success",
            data=env_info,
            message="Environment information retrieved",
            broker=settings.active_brokers[0] if settings.active_brokers else "unknown"
        )
    except Exception as e:
        return StandardResponse(
            status="error",
            message=f"Failed to get environment info: {str(e)}",
            broker=settings.active_brokers[0] if settings.active_brokers else "unknown"
        )