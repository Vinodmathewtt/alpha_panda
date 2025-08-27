"""
Mock Market Server for Testing
HTTP/WebSocket server that provides realistic market data for testing.
CRITICAL: This is for testing only - never part of main application.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Any
import websockets
from websockets.exceptions import ConnectionClosed
from aiohttp import web, WSMsgType
import aiohttp_cors
from dataclasses import asdict

from .realistic_data_generator import RealisticMarketDataGenerator, MarketScenarios
from .mock_zerodha_api import MockZerodhaAPI


class MockMarketServer:
    """
    Mock market data server providing HTTP REST API and WebSocket streaming.
    Simulates realistic market data server for testing trading systems.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8888):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.data_generator = RealisticMarketDataGenerator(seed=42)
        self.zerodha_api = MockZerodhaAPI()
        
        # WebSocket connections
        self.ws_connections: Set[web.WebSocketResponse] = set()
        self.subscribed_instruments: Dict[web.WebSocketResponse, Set[int]] = {}
        
        # Server state
        self.is_running = False
        self.tick_broadcast_task: Optional[asyncio.Task] = None
        
        # Performance settings
        self.tick_rate = 2.0  # Ticks per second per instrument
        self.max_connections = 100
        
        # Error injection for testing
        self.error_rate = 0.0  # 0-1, probability of injecting errors
        self.latency_ms = 0  # Additional latency in milliseconds
        
        self._setup_routes()
        self._setup_cors()
        
    def _setup_routes(self):
        """Setup HTTP routes"""
        # Market data endpoints
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/market/instruments', self.get_instruments)
        self.app.router.add_get('/market/quote/{symbol}', self.get_quote)
        self.app.router.add_get('/market/quotes', self.get_quotes)
        self.app.router.add_get('/market/snapshot', self.get_market_snapshot)
        
        # WebSocket endpoint
        self.app.router.add_get('/ws/market', self.websocket_handler)
        
        # Mock Zerodha API endpoints
        self.app.router.add_post('/zerodha/login', self.zerodha_login)
        self.app.router.add_get('/zerodha/profile', self.zerodha_profile)
        self.app.router.add_get('/zerodha/margins', self.zerodha_margins)
        self.app.router.add_post('/zerodha/orders', self.zerodha_place_order)
        self.app.router.add_get('/zerodha/orders', self.zerodha_get_orders)
        self.app.router.add_get('/zerodha/positions', self.zerodha_get_positions)
        
        # Control endpoints for testing
        self.app.router.add_post('/control/scenario', self.set_scenario)
        self.app.router.add_post('/control/error_injection', self.set_error_injection)
        self.app.router.add_post('/control/market_event', self.simulate_market_event)
        
    def _setup_cors(self):
        """Setup CORS for cross-origin requests"""
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })
        
        # Add CORS to all routes
        for route in list(self.app.router.routes()):
            cors.add(route)
            
    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        await self._simulate_latency()
        
        return web.json_response({
            "status": "healthy",
            "server": "mock_market_server",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "connections": len(self.ws_connections),
            "subscribed_instruments": sum(len(subs) for subs in self.subscribed_instruments.values())
        })
        
    async def get_instruments(self, request: web.Request) -> web.Response:
        """Get available instruments"""
        await self._simulate_latency()
        
        if self._should_inject_error():
            return web.json_response(
                {"error": "Instruments service temporarily unavailable"}, 
                status=503
            )
            
        instruments = []
        for token, config in self.data_generator.instruments.items():
            instruments.append({
                "instrument_token": token,
                "symbol": config.symbol,
                "exchange": "NSE",
                "tick_size": float(config.tick_size),
                "lot_size": config.lot_size
            })
            
        return web.json_response({"instruments": instruments})
        
    async def get_quote(self, request: web.Request) -> web.Response:
        """Get quote for a single symbol"""
        await self._simulate_latency()
        
        symbol = request.match_info['symbol']
        
        # Find instrument by symbol
        instrument_token = None
        for token, config in self.data_generator.instruments.items():
            if config.symbol.replace(" ", "").lower() == symbol.lower():
                instrument_token = token
                break
                
        if not instrument_token:
            return web.json_response(
                {"error": f"Symbol {symbol} not found"}, 
                status=404
            )
            
        if self._should_inject_error():
            return web.json_response(
                {"error": "Quote service temporarily unavailable"}, 
                status=503
            )
            
        try:
            tick = self.data_generator.generate_tick(instrument_token)
            
            quote = {
                "instrument_token": instrument_token,
                "symbol": symbol,
                "last_price": float(tick.last_price),
                "volume": tick.last_traded_quantity or 0,
                "timestamp": tick.timestamp.isoformat(),
                "ohlc": {
                    "open": float(tick.ohlc["open"]) if tick.ohlc else float(tick.last_price),
                    "high": float(tick.ohlc["high"]) if tick.ohlc else float(tick.last_price),
                    "low": float(tick.ohlc["low"]) if tick.ohlc else float(tick.last_price),
                    "close": float(tick.ohlc["close"]) if tick.ohlc else float(tick.last_price)
                },
                "change": float(tick.change) if tick.change else 0.0,
                "buy_quantity": tick.total_buy_quantity or 0,
                "sell_quantity": tick.total_sell_quantity or 0
            }
            
            return web.json_response(quote)
            
        except Exception as e:
            return web.json_response(
                {"error": f"Error generating quote: {str(e)}"}, 
                status=500
            )
            
    async def get_quotes(self, request: web.Request) -> web.Response:
        """Get quotes for multiple symbols"""
        await self._simulate_latency()
        
        # Get symbols from query parameters
        symbols_param = request.query.get('symbols', '')
        if not symbols_param:
            return web.json_response(
                {"error": "symbols parameter required"}, 
                status=400
            )
            
        symbols = [s.strip() for s in symbols_param.split(',')]
        quotes = {}
        
        for symbol in symbols:
            # Find instrument by symbol
            instrument_token = None
            for token, config in self.data_generator.instruments.items():
                if config.symbol.replace(" ", "").lower() == symbol.lower():
                    instrument_token = token
                    break
                    
            if not instrument_token:
                quotes[symbol] = {"error": "Symbol not found"}
                continue
                
            try:
                tick = self.data_generator.generate_tick(instrument_token)
                quotes[symbol] = {
                    "instrument_token": instrument_token,
                    "last_price": float(tick.last_price),
                    "volume": tick.last_traded_quantity or 0,
                    "timestamp": tick.timestamp.isoformat(),
                    "change": float(tick.change) if tick.change else 0.0
                }
            except Exception as e:
                quotes[symbol] = {"error": str(e)}
                
        return web.json_response({"quotes": quotes})
        
    async def get_market_snapshot(self, request: web.Request) -> web.Response:
        """Get complete market snapshot"""
        await self._simulate_latency()
        
        if self._should_inject_error():
            return web.json_response(
                {"error": "Market snapshot service temporarily unavailable"}, 
                status=503
            )
            
        snapshot = self.data_generator.get_current_snapshot()
        return web.json_response({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_status": "open",
            "instruments": snapshot
        })
        
    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections for real-time market data"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        if len(self.ws_connections) >= self.max_connections:
            await ws.close(code=1013, message="Too many connections")
            return ws
            
        self.ws_connections.add(ws)
        self.subscribed_instruments[ws] = set()
        
        try:
            # Send welcome message
            await ws.send_str(json.dumps({
                "type": "connection",
                "status": "connected",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_websocket_message(ws, data)
                    except json.JSONDecodeError:
                        await ws.send_str(json.dumps({
                            "type": "error",
                            "message": "Invalid JSON message"
                        }))
                elif msg.type == WSMsgType.ERROR:
                    print(f'WebSocket error: {ws.exception()}')
                    break
                    
        except ConnectionClosed:
            pass
        finally:
            self.ws_connections.discard(ws)
            self.subscribed_instruments.pop(ws, None)
            
        return ws
        
    async def _handle_websocket_message(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        message_type = data.get("type")
        
        if message_type == "subscribe":
            instruments = data.get("instruments", [])
            for token in instruments:
                self.subscribed_instruments[ws].add(int(token))
                
            await ws.send_str(json.dumps({
                "type": "subscription",
                "status": "subscribed",
                "instruments": list(self.subscribed_instruments[ws])
            }))
            
        elif message_type == "unsubscribe":
            instruments = data.get("instruments", [])
            for token in instruments:
                self.subscribed_instruments[ws].discard(int(token))
                
            await ws.send_str(json.dumps({
                "type": "subscription", 
                "status": "unsubscribed",
                "instruments": list(self.subscribed_instruments[ws])
            }))
            
        elif message_type == "ping":
            await ws.send_str(json.dumps({
                "type": "pong",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
        else:
            await ws.send_str(json.dumps({
                "type": "error",
                "message": f"Unknown message type: {message_type}"
            }))
            
    async def _broadcast_ticks(self):
        """Broadcast market ticks to subscribed WebSocket connections"""
        while self.is_running:
            try:
                # Get all subscribed instruments
                all_subscribed = set()
                for instruments in self.subscribed_instruments.values():
                    all_subscribed.update(instruments)
                    
                if not all_subscribed:
                    await asyncio.sleep(1.0)
                    continue
                    
                # Generate ticks for subscribed instruments
                for instrument_token in all_subscribed:
                    try:
                        tick = self.data_generator.generate_tick(instrument_token)
                        
                        tick_data = {
                            "type": "tick",
                            "instrument_token": instrument_token,
                            "last_price": float(tick.last_price),
                            "last_quantity": tick.last_traded_quantity or 0,
                            "volume": tick.volume_traded or 0,
                            "timestamp": tick.timestamp.isoformat(),
                            "change": float(tick.change) if tick.change else 0.0
                        }
                        
                        # Add additional data if available
                        if tick.ohlc:
                            tick_data["ohlc"] = {
                                "open": float(tick.ohlc["open"]),
                                "high": float(tick.ohlc["high"]),
                                "low": float(tick.ohlc["low"]),
                                "close": float(tick.ohlc["close"])
                            }
                            
                        if tick.depth:
                            tick_data["depth"] = {
                                "buy": [
                                    {
                                        "price": float(level["price"]),
                                        "quantity": level["quantity"],
                                        "orders": level["orders"]
                                    } for level in tick.depth["buy"]
                                ],
                                "sell": [
                                    {
                                        "price": float(level["price"]),
                                        "quantity": level["quantity"], 
                                        "orders": level["orders"]
                                    } for level in tick.depth["sell"]
                                ]
                            }
                        
                        # Broadcast to subscribed connections
                        message = json.dumps(tick_data)
                        disconnected = set()
                        
                        for ws in self.ws_connections:
                            if instrument_token in self.subscribed_instruments.get(ws, set()):
                                try:
                                    await self._simulate_latency()
                                    
                                    if self._should_inject_error():
                                        # Simulate connection error
                                        continue
                                        
                                    await ws.send_str(message)
                                except ConnectionClosed:
                                    disconnected.add(ws)
                                except Exception as e:
                                    print(f"Error sending tick to WebSocket: {e}")
                                    disconnected.add(ws)
                                    
                        # Clean up disconnected connections
                        for ws in disconnected:
                            self.ws_connections.discard(ws)
                            self.subscribed_instruments.pop(ws, None)
                            
                    except Exception as e:
                        print(f"Error generating tick for instrument {instrument_token}: {e}")
                        
                # Control tick rate
                await asyncio.sleep(1.0 / self.tick_rate)
                
            except Exception as e:
                print(f"Error in tick broadcasting: {e}")
                await asyncio.sleep(1.0)
                
    # Mock Zerodha API endpoints
    async def zerodha_login(self, request: web.Request) -> web.Response:
        """Mock Zerodha login endpoint"""
        await self._simulate_latency()
        
        data = await request.json()
        api_key = data.get("api_key")
        request_token = data.get("request_token")
        api_secret = data.get("api_secret")
        
        try:
            session = self.zerodha_api.generate_session(request_token, api_secret)
            self.zerodha_api.set_access_token(session["access_token"])
            return web.json_response(session)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)
            
    async def zerodha_profile(self, request: web.Request) -> web.Response:
        """Mock Zerodha profile endpoint"""
        await self._simulate_latency()
        
        try:
            profile = self.zerodha_api.profile()
            return web.json_response(profile)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=401)
            
    async def zerodha_margins(self, request: web.Request) -> web.Response:
        """Mock Zerodha margins endpoint"""
        await self._simulate_latency()
        
        try:
            margins = self.zerodha_api.margins()
            return web.json_response(margins)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=401)
            
    async def zerodha_place_order(self, request: web.Request) -> web.Response:
        """Mock Zerodha place order endpoint"""
        await self._simulate_latency()
        
        try:
            data = await request.json()
            result = self.zerodha_api.place_order(**data)
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)
            
    async def zerodha_get_orders(self, request: web.Request) -> web.Response:
        """Mock Zerodha get orders endpoint"""
        await self._simulate_latency()
        
        try:
            orders = self.zerodha_api.orders()
            return web.json_response(orders)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=401)
            
    async def zerodha_get_positions(self, request: web.Request) -> web.Response:
        """Mock Zerodha get positions endpoint"""
        await self._simulate_latency()
        
        try:
            positions = self.zerodha_api.positions()
            return web.json_response(positions)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=401)
            
    # Control endpoints for testing
    async def set_scenario(self, request: web.Request) -> web.Response:
        """Set market scenario for testing"""
        data = await request.json()
        scenario = data.get("scenario")
        
        if scenario == "trending_up":
            MarketScenarios.trending_up_market(self.data_generator)
        elif scenario == "volatile":
            MarketScenarios.volatile_market(self.data_generator)
        elif scenario == "low_volume":
            MarketScenarios.low_volume_market(self.data_generator)
        elif scenario == "high_frequency":
            MarketScenarios.high_frequency_market(self.data_generator)
        else:
            return web.json_response({"error": f"Unknown scenario: {scenario}"}, status=400)
            
        return web.json_response({"status": f"Scenario set to {scenario}"})
        
    async def set_error_injection(self, request: web.Request) -> web.Response:
        """Configure error injection for testing"""
        data = await request.json()
        self.error_rate = data.get("error_rate", 0.0)
        self.latency_ms = data.get("latency_ms", 0)
        
        return web.json_response({
            "status": "Error injection configured",
            "error_rate": self.error_rate,
            "latency_ms": self.latency_ms
        })
        
    async def simulate_market_event(self, request: web.Request) -> web.Response:
        """Simulate market events"""
        data = await request.json()
        event_type = data.get("event_type")
        instrument_token = data.get("instrument_token")
        
        if not event_type or not instrument_token:
            return web.json_response(
                {"error": "event_type and instrument_token required"}, 
                status=400
            )
            
        try:
            self.data_generator.simulate_market_event(event_type, instrument_token)
            return web.json_response({
                "status": f"Market event {event_type} simulated for instrument {instrument_token}"
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)
            
    # Helper methods
    async def _simulate_latency(self):
        """Simulate network latency"""
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)
            
    def _should_inject_error(self) -> bool:
        """Check if should inject error"""
        import random
        return random.random() < self.error_rate
        
    async def start(self):
        """Start the mock market server"""
        self.is_running = True
        
        # Start tick broadcasting task
        self.tick_broadcast_task = asyncio.create_task(self._broadcast_ticks())
        
        # Start HTTP server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        print(f"Mock Market Server started on http://{self.host}:{self.port}")
        print(f"WebSocket endpoint: ws://{self.host}:{self.port}/ws/market")
        print(f"Health check: http://{self.host}:{self.port}/health")
        
    async def stop(self):
        """Stop the mock market server"""
        self.is_running = False
        
        if self.tick_broadcast_task:
            self.tick_broadcast_task.cancel()
            try:
                await self.tick_broadcast_task
            except asyncio.CancelledError:
                pass
                
        # Close all WebSocket connections
        for ws in list(self.ws_connections):
            await ws.close()
            
        print("Mock Market Server stopped")


async def main():
    """Run the mock market server"""
    server = MockMarketServer()
    
    try:
        await server.start()
        
        # Keep server running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await server.stop()


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Run server
    asyncio.run(main())