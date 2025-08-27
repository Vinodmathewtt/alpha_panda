"""WebSocket route handlers for real-time data streaming."""

import asyncio
import json
import uuid
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect, Query, Path
from fastapi.routing import APIWebSocketRoute

from core.logging.logger import get_logger
from .websocket import websocket_manager

logger = get_logger(__name__)


async def websocket_endpoint(websocket: WebSocket, client_id: str = Path(...)):
    """Main WebSocket endpoint for real-time data streaming."""
    
    # client_id is now a required path parameter
    
    try:
        # Connect client
        connection = await websocket_manager.connect_client(websocket, client_id)
        logger.info(f"WebSocket client connected: {client_id}")
        
        # Handle messages
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle the message
                await websocket_manager.handle_client_message(client_id, message)
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket client disconnected: {client_id}")
                break
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from client {client_id}")
                await connection.send_message({
                    "type": "error",
                    "message": "Invalid JSON format"
                })
            except Exception as e:
                logger.error(f"Error handling message from {client_id}: {e}")
                await connection.send_message({
                    "type": "error", 
                    "message": "Message processing error"
                })
                
    except Exception as e:
        logger.error(f"WebSocket connection error for {client_id}: {e}")
    finally:
        # Ensure cleanup
        await websocket_manager.disconnect_client(client_id)


def create_websocket_routes():
    """Create WebSocket routes for the FastAPI app."""
    return [
        APIWebSocketRoute("/ws", websocket_endpoint, name="websocket"),
        APIWebSocketRoute("/ws/{client_id}", websocket_endpoint, name="websocket_with_id")
    ]