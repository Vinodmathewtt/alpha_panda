"""WebSocket manager for real-time data streaming."""

import asyncio
import json
from typing import Dict, Set, Any, Optional, List
from datetime import datetime
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from core.events import get_event_bus_core
from core.events.event_types import BaseEvent
from core.logging.logger import get_logger
from core.config.settings import settings

logger = get_logger(__name__)


class WebSocketConnection:
    """Represents a WebSocket connection with metadata."""
    
    def __init__(self, websocket: WebSocket, client_id: str, user_id: Optional[str] = None):
        self.websocket = websocket
        self.client_id = client_id
        self.user_id = user_id
        self.connected_at = datetime.now()
        self.subscriptions: Set[str] = set()
        self.last_ping = datetime.now()
        
    async def send_message(self, message: Dict[str, Any]):
        """Send message to WebSocket client."""
        try:
            await self.websocket.send_text(json.dumps(message))
        except (ConnectionClosed, WebSocketDisconnect):
            logger.debug(f"Connection closed for client {self.client_id}")
            raise
        except Exception as e:
            logger.error(f"Error sending message to {self.client_id}: {e}")
            raise
    
    async def send_event(self, event_type: str, data: Any):
        """Send event message to client."""
        message = {
            "type": "event",
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_message(message)
    
    def add_subscription(self, topic: str):
        """Add subscription to a topic."""
        self.subscriptions.add(topic)
    
    def remove_subscription(self, topic: str):
        """Remove subscription from a topic."""
        self.subscriptions.discard(topic)
    
    def is_subscribed(self, topic: str) -> bool:
        """Check if subscribed to a topic."""
        return topic in self.subscriptions


class WebSocketManager:
    """Manages WebSocket connections and real-time data streaming."""
    
    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.topic_subscribers: Dict[str, Set[str]] = defaultdict(set)
        self.running = False
        self._heartbeat_task = None
        self._event_listener_task = None
        
    async def initialize(self):
        """Initialize WebSocket manager."""
        logger.info("Initializing WebSocket manager...")
        
        self.running = True
        
        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Start event listener
        self._event_listener_task = asyncio.create_task(self._event_listener())
        
        logger.info("✅ WebSocket manager initialized")
    
    async def stop(self):
        """Stop WebSocket manager."""
        logger.info("Stopping WebSocket manager...")
        
        self.running = False
        
        # Cancel tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._event_listener_task:
            self._event_listener_task.cancel()
        
        # Close all connections
        for connection in list(self.connections.values()):
            await self.disconnect_client(connection.client_id)
        
        logger.info("✅ WebSocket manager stopped")
    
    async def connect_client(self, websocket: WebSocket, client_id: str, user_id: Optional[str] = None):
        """Connect a new WebSocket client."""
        try:
            await websocket.accept()
            
            connection = WebSocketConnection(websocket, client_id, user_id)
            self.connections[client_id] = connection
            
            logger.info(f"WebSocket client connected: {client_id}")
            
            # Send welcome message
            await connection.send_message({
                "type": "welcome",
                "client_id": client_id,
                "timestamp": datetime.now().isoformat(),
                "available_topics": self._get_available_topics()
            })
            
            return connection
            
        except Exception as e:
            logger.error(f"Error connecting WebSocket client {client_id}: {e}")
            raise
    
    async def disconnect_client(self, client_id: str):
        """Disconnect a WebSocket client."""
        if client_id in self.connections:
            connection = self.connections[client_id]
            
            # Remove from all topic subscriptions
            for topic in list(connection.subscriptions):
                self.unsubscribe_from_topic(client_id, topic)
            
            # Close connection
            try:
                await connection.websocket.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket for {client_id}: {e}")
            
            # Remove from connections
            del self.connections[client_id]
            
            logger.info(f"WebSocket client disconnected: {client_id}")
    
    def subscribe_to_topic(self, client_id: str, topic: str):
        """Subscribe client to a topic."""
        if client_id in self.connections:
            connection = self.connections[client_id]
            connection.add_subscription(topic)
            self.topic_subscribers[topic].add(client_id)
            logger.debug(f"Client {client_id} subscribed to {topic}")
    
    def unsubscribe_from_topic(self, client_id: str, topic: str):
        """Unsubscribe client from a topic."""
        if client_id in self.connections:
            connection = self.connections[client_id]
            connection.remove_subscription(topic)
            self.topic_subscribers[topic].discard(client_id)
            logger.debug(f"Client {client_id} unsubscribed from {topic}")
    
    async def broadcast_to_topic(self, topic: str, event_type: str, data: Any):
        """Broadcast message to all subscribers of a topic."""
        if topic not in self.topic_subscribers:
            return
        
        subscribers = list(self.topic_subscribers[topic])
        if not subscribers:
            return
        
        # Send to all subscribers
        disconnected_clients = []
        for client_id in subscribers:
            if client_id in self.connections:
                try:
                    connection = self.connections[client_id]
                    await connection.send_event(event_type, data)
                except (ConnectionClosed, WebSocketDisconnect):
                    disconnected_clients.append(client_id)
                except Exception as e:
                    logger.error(f"Error broadcasting to {client_id}: {e}")
                    disconnected_clients.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.disconnect_client(client_id)
    
    async def send_to_client(self, client_id: str, event_type: str, data: Any):
        """Send message to specific client."""
        if client_id in self.connections:
            try:
                connection = self.connections[client_id]
                await connection.send_event(event_type, data)
            except (ConnectionClosed, WebSocketDisconnect):
                await self.disconnect_client(client_id)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
                await self.disconnect_client(client_id)
    
    async def handle_client_message(self, client_id: str, message: Dict[str, Any]):
        """Handle message from WebSocket client."""
        try:
            msg_type = message.get("type")
            
            if msg_type == "subscribe":
                topic = message.get("topic")
                if topic:
                    self.subscribe_to_topic(client_id, topic)
                    await self.send_to_client(client_id, "subscribed", {"topic": topic})
            
            elif msg_type == "unsubscribe":
                topic = message.get("topic")
                if topic:
                    self.unsubscribe_from_topic(client_id, topic)
                    await self.send_to_client(client_id, "unsubscribed", {"topic": topic})
            
            elif msg_type == "ping":
                if client_id in self.connections:
                    self.connections[client_id].last_ping = datetime.now()
                await self.send_to_client(client_id, "pong", {"timestamp": datetime.now().isoformat()})
            
            else:
                logger.warning(f"Unknown message type from {client_id}: {msg_type}")
                
        except Exception as e:
            logger.error(f"Error handling client message from {client_id}: {e}")
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat to detect dead connections."""
        while self.running:
            try:
                current_time = datetime.now()
                timeout_threshold = current_time.timestamp() - 60  # 60 seconds timeout
                
                disconnected_clients = []
                for client_id, connection in self.connections.items():
                    if connection.last_ping.timestamp() < timeout_threshold:
                        disconnected_clients.append(client_id)
                
                # Clean up disconnected clients
                for client_id in disconnected_clients:
                    await self.disconnect_client(client_id)
                
                # Send heartbeat to active connections
                for connection in self.connections.values():
                    try:
                        await connection.send_message({
                            "type": "heartbeat",
                            "timestamp": current_time.isoformat()
                        })
                    except Exception as e:
                        logger.debug(f"Heartbeat failed for {connection.client_id}: {e}")
                
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(30)
    
    async def _event_listener(self):
        """Listen to events from event bus and broadcast to WebSocket clients."""
        while self.running:
            try:
                # Get event bus instance
                event_bus = get_event_bus_core()
                
                # Subscribe to relevant events
                await event_bus.subscribe("market.tick.*", self._handle_market_tick)
                await event_bus.subscribe("trading.signal.*", self._handle_trading_signal)
                await event_bus.subscribe("trading.order.*", self._handle_order_event)
                await event_bus.subscribe("system.risk.*", self._handle_risk_event)
                
                # Keep listening
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in event listener: {e}")
                await asyncio.sleep(5)
    
    async def _handle_market_tick(self, event: BaseEvent):
        """Handle market tick events."""
        await self.broadcast_to_topic("market_data", "market_tick", event.data)
    
    async def _handle_trading_signal(self, event: BaseEvent):
        """Handle trading signal events."""
        await self.broadcast_to_topic("trading_signals", "trading_signal", event.data)
    
    async def _handle_order_event(self, event: BaseEvent):
        """Handle order events."""
        await self.broadcast_to_topic("orders", "order_update", event.data)
    
    async def _handle_risk_event(self, event: BaseEvent):
        """Handle risk events."""
        await self.broadcast_to_topic("risk_alerts", "risk_alert", event.data)
    
    def _get_available_topics(self) -> List[str]:
        """Get list of available WebSocket topics."""
        return [
            "market_data",
            "trading_signals", 
            "orders",
            "positions",
            "risk_alerts",
            "system_health"
        ]
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get WebSocket connection statistics."""
        return {
            "total_connections": len(self.connections),
            "topics_with_subscribers": len([t for t, subs in self.topic_subscribers.items() if subs]),
            "total_subscriptions": sum(len(conn.subscriptions) for conn in self.connections.values()),
            "connections": [
                {
                    "client_id": conn.client_id,
                    "user_id": conn.user_id,
                    "connected_at": conn.connected_at.isoformat(),
                    "subscriptions": list(conn.subscriptions)
                }
                for conn in self.connections.values()
            ]
        }


# Global WebSocket manager instance
websocket_manager = WebSocketManager()