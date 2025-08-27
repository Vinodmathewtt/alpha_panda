import asyncio
import json
from typing import List, Set
from fastapi import WebSocket, WebSocketDisconnect
import structlog

logger = structlog.get_logger()

class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        """Accept and manage new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("WebSocket connection established", total_connections=len(self.active_connections))
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.discard(websocket)
        logger.info("WebSocket connection closed", total_connections=len(self.active_connections))
    
    async def send_json(self, data: dict, websocket: WebSocket):
        """Send JSON data to specific WebSocket"""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error("Failed to send WebSocket message", error=str(e))
            self.disconnect(websocket)
    
    async def broadcast(self, data: dict):
        """Broadcast JSON data to all connected WebSockets"""
        disconnected = set()
        
        for websocket in self.active_connections:
            try:
                await websocket.send_json(data)
            except Exception as e:
                logger.error("Failed to broadcast to WebSocket", error=str(e))
                disconnected.add(websocket)
        
        # Remove disconnected sockets
        for websocket in disconnected:
            self.disconnect(websocket)

class RealtimeService:
    """Service for managing real-time data streams"""
    
    def __init__(self):
        self.connection_manager = ConnectionManager()
        self._tasks: Set[asyncio.Task] = set()
    
    async def start_health_monitoring(self, dashboard_service):
        """Start health monitoring broadcast"""
        async def health_broadcast():
            while True:
                try:
                    health_data = await dashboard_service.get_health_summary()
                    await self.connection_manager.broadcast({
                        "type": "health_update",
                        "data": health_data,
                        "timestamp": health_data.get("timestamp")
                    })
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Health broadcast error", error=str(e))
                    await asyncio.sleep(10)
        
        task = asyncio.create_task(health_broadcast())
        self._tasks.add(task)
        return task
    
    async def start_pipeline_monitoring(self, dashboard_service):
        """Start pipeline monitoring broadcast"""
        async def pipeline_broadcast():
            while True:
                try:
                    pipeline_data = await dashboard_service.get_pipeline_summary()
                    await self.connection_manager.broadcast({
                        "type": "pipeline_update",
                        "data": pipeline_data,
                        "timestamp": pipeline_data.get("timestamp")
                    })
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Pipeline broadcast error", error=str(e))
                    await asyncio.sleep(5)
        
        task = asyncio.create_task(pipeline_broadcast())
        self._tasks.add(task)
        return task
    
    async def stop_all_tasks(self):
        """Stop all background tasks"""
        for task in self._tasks:
            task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()