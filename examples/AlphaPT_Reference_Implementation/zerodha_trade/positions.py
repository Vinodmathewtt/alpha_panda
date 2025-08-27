"""Zerodha position management for live trading."""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal
from collections import defaultdict

from core.utils.exceptions import TradingError
from core.config.settings import settings
from core.events import EventBusCore
from core.events.event_types import EventFactory, EventType
from core.logging.logger import get_logger
from core.auth.auth_manager import AuthManager

from .models import ZerodhaPosition, ZerodhaAccount
from .types import ZerodhaProductType, ZerodhaExchange


class ZerodhaPositionManager:
    """Manages live trading positions with Zerodha KiteConnect."""
    
    def __init__(
        self,
        auth_manager: AuthManager,
        event_bus: Optional[EventBusCore] = None
    ):
        """Initialize Zerodha position manager."""
        self.logger = get_logger(__name__)
        self.event_bus = event_bus
        self.auth_manager = auth_manager
        
        # Position storage
        self.positions: Dict[str, Dict[str, ZerodhaPosition]] = defaultdict(dict)  # strategy -> position_key -> position
        self.account: Optional[ZerodhaAccount] = None
        
        # KiteConnect client
        self.kite = None
        
        # Position monitoring
        self.monitoring_enabled = True
        self.position_update_interval = 5.0  # Check positions every 5 seconds
        
        # Statistics
        self.stats = {
            "positions_updated": 0,
            "positions_created": 0,
            "margin_checks": 0,
            "api_calls": 0,
            "api_errors": 0
        }
        
        self.logger.info("ZerodhaPositionManager initialized")
    
    async def initialize(self) -> None:
        """Initialize position manager with authentication."""
        try:
            # Ensure authentication
            await self.auth_manager.ensure_authenticated()
            self.kite = self.auth_manager.get_kite_client()
            
            if not self.kite:
                raise TradingError("Zerodha authentication required for position management")
            
            # Load initial account and positions
            await self.refresh_account()
            await self.refresh_positions()
            
            # Start position monitoring
            if self.monitoring_enabled:
                asyncio.create_task(self._position_monitoring_loop())
            
            self.logger.info("Zerodha position manager initialization completed")
            
        except Exception as e:
            self.logger.error(f"Zerodha position manager initialization failed: {e}")
            raise TradingError(f"Failed to initialize Zerodha position manager: {e}")
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        try:
            self.monitoring_enabled = False
            self.logger.info("Zerodha position manager shutdown completed")
        except Exception as e:
            self.logger.error(f"Zerodha position manager shutdown failed: {e}")
    
    # Position Management
    
    async def get_position(
        self,
        strategy_name: str,
        tradingsymbol: str,
        product: str = "MIS"
    ) -> Optional[ZerodhaPosition]:
        """Get position for strategy, symbol, and product."""
        position_key = f"{tradingsymbol}_{product}"
        return self.positions[strategy_name].get(position_key)
    
    async def get_positions(
        self,
        strategy_name: str,
        include_zero: bool = False
    ) -> List[ZerodhaPosition]:
        """Get all positions for strategy."""
        positions = list(self.positions[strategy_name].values())
        
        if not include_zero:
            positions = [p for p in positions if p.quantity != 0]
        
        return sorted(positions, key=lambda p: p.updated_at, reverse=True)
    
    async def get_all_positions(self, include_zero: bool = False) -> List[ZerodhaPosition]:
        """Get all positions across all strategies."""
        all_positions = []
        for strategy_positions in self.positions.values():
            all_positions.extend(strategy_positions.values())
        
        if not include_zero:
            all_positions = [p for p in all_positions if p.quantity != 0]
        
        return sorted(all_positions, key=lambda p: p.updated_at, reverse=True)
    
    async def refresh_positions(self) -> None:
        """Refresh positions from Kite API."""
        try:
            if not self.kite:
                return
            
            self.stats["api_calls"] += 1
            kite_positions = await self._call_kite_api(self.kite.positions)
            
            # Process day positions
            day_positions = kite_positions.get("day", [])
            for kite_position in day_positions:
                await self._process_kite_position(kite_position, "day")
            
            # Process net positions
            net_positions = kite_positions.get("net", [])
            for kite_position in net_positions:
                await self._process_kite_position(kite_position, "net")
            
            self.stats["positions_updated"] += 1
            
        except Exception as e:
            self.logger.error(f"Failed to refresh positions: {e}")
            self.stats["api_errors"] += 1
    
    async def _process_kite_position(self, kite_position: Dict[str, Any], position_type: str) -> None:
        """Process position data from Kite API."""
        try:
            tradingsymbol = kite_position.get("tradingsymbol", "")
            product = kite_position.get("product", "")
            exchange = kite_position.get("exchange", "NSE")
            instrument_token = kite_position.get("instrument_token", 0)
            
            if not tradingsymbol or not product:
                return
            
            # Create position key
            position_key = f"{tradingsymbol}_{product}"
            
            # Find existing position or create new one
            # For simplicity, we'll assign to "default" strategy if no specific mapping
            strategy_name = "default"  # This could be enhanced to map instruments to strategies
            
            position = self.positions[strategy_name].get(position_key)
            
            if not position:
                position = ZerodhaPosition(
                    strategy_name=strategy_name,
                    tradingsymbol=tradingsymbol,
                    exchange=ZerodhaExchange(exchange),
                    instrument_token=instrument_token,
                    product=ZerodhaProductType(product)
                )
                self.positions[strategy_name][position_key] = position
                self.stats["positions_created"] += 1
            
            # Update position from Kite data
            position.update_from_kite_position(kite_position)
            
            # Publish position update event
            if self.event_bus:
                await self._publish_position_event(position)
            
        except Exception as e:
            self.logger.error(f"Failed to process Kite position: {e}")
    
    # Account and Margin Management
    
    async def get_account(self) -> Optional[ZerodhaAccount]:
        """Get account information."""
        return self.account
    
    async def refresh_account(self) -> None:
        """Refresh account and margin information."""
        try:
            if not self.kite:
                return
            
            # Get user profile
            self.stats["api_calls"] += 1
            profile = await self._call_kite_api(self.kite.profile)
            user_id = profile.get("user_id", "")
            
            # Get margins
            self.stats["api_calls"] += 1
            margins = await self._call_kite_api(self.kite.margins)
            
            # Create or update account
            if not self.account:
                self.account = ZerodhaAccount(
                    strategy_name="default",  # Could be enhanced for multi-strategy
                    user_id=user_id
                )
            
            # Update account from margins
            self.account.update_from_kite_margins(margins)
            self.stats["margin_checks"] += 1
            
            # Publish account update event
            if self.event_bus:
                await self._publish_account_event(self.account)
            
        except Exception as e:
            self.logger.error(f"Failed to refresh account: {e}")
            self.stats["api_errors"] += 1
    
    async def check_margin_requirement(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        price: float,
        product: str = "MIS"
    ) -> Dict[str, Any]:
        """Check margin requirement for a potential order."""
        try:
            if not self.kite:
                raise TradingError("Zerodha client not initialized")
            
            # Prepare order parameters for margin calculation
            order_params = [
                {
                    "tradingsymbol": tradingsymbol,
                    "exchange": exchange,
                    "transaction_type": transaction_type,
                    "quantity": quantity,
                    "price": price,
                    "product": product
                }
            ]
            
            self.stats["api_calls"] += 1
            margin_response = await self._call_kite_api(
                self.kite.order_margins,
                order_params
            )
            
            return margin_response
            
        except Exception as e:
            self.logger.error(f"Failed to check margin requirement: {e}")
            self.stats["api_errors"] += 1
            return {"error": str(e)}
    
    # Position Analysis
    
    async def get_portfolio_summary(self, strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """Get portfolio summary."""
        try:
            # Get positions to analyze
            if strategy_name:
                positions = await self.get_positions(strategy_name)
            else:
                positions = await self.get_all_positions()
            
            # Calculate summary metrics
            total_pnl = sum(p.pnl for p in positions)
            total_m2m = sum(p.m2m for p in positions)
            total_unrealised = sum(p.unrealised for p in positions)
            total_realised = sum(p.realised for p in positions)
            
            long_positions = [p for p in positions if p.is_long]
            short_positions = [p for p in positions if p.is_short]
            
            # Account information
            account_info = {}
            if self.account:
                account_info = self.account.to_dict()
            
            return {
                "strategy_name": strategy_name or "all",
                "account": account_info,
                "portfolio_metrics": {
                    "total_pnl": float(total_pnl),
                    "total_m2m": float(total_m2m),
                    "total_unrealised": float(total_unrealised),
                    "total_realised": float(total_realised)
                },
                "positions": {
                    "total_positions": len(positions),
                    "long_positions": len(long_positions),
                    "short_positions": len(short_positions),
                    "positions": [p.to_dict() for p in positions]
                },
                "updated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get portfolio summary: {e}")
            return {"error": str(e)}
    
    async def get_position_pnl(self, strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """Get position-wise P&L breakdown."""
        try:
            if strategy_name:
                positions = await self.get_positions(strategy_name)
            else:
                positions = await self.get_all_positions()
            
            pnl_breakdown = []
            
            for position in positions:
                pnl_breakdown.append({
                    "tradingsymbol": position.tradingsymbol,
                    "exchange": position.exchange.value,
                    "product": position.product.value,
                    "quantity": float(position.quantity),
                    "average_price": float(position.average_price),
                    "last_price": float(position.last_price),
                    "pnl": float(position.pnl),
                    "m2m": float(position.m2m),
                    "unrealised": float(position.unrealised),
                    "realised": float(position.realised),
                    "value": float(position.value),
                    "is_long": position.is_long,
                    "is_short": position.is_short
                })
            
            # Sort by absolute P&L (highest first)
            pnl_breakdown.sort(key=lambda x: abs(x["pnl"]), reverse=True)
            
            return {
                "strategy_name": strategy_name or "all",
                "position_count": len(pnl_breakdown),
                "total_pnl": sum(p["pnl"] for p in pnl_breakdown),
                "positions": pnl_breakdown,
                "updated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get position P&L: {e}")
            return {"error": str(e)}
    
    # Private Methods
    
    async def _position_monitoring_loop(self) -> None:
        """Background position monitoring loop."""
        while self.monitoring_enabled:
            try:
                await self.refresh_positions()
                await self.refresh_account()
                await asyncio.sleep(self.position_update_interval)
            except Exception as e:
                self.logger.error(f"Position monitoring loop error: {e}")
                await asyncio.sleep(10)  # Wait longer on errors
    
    async def _call_kite_api(self, method, *args, **kwargs):
        """Call Kite API method with error handling."""
        try:
            # For async operations, we need to handle this differently
            # This is a placeholder for proper async Kite integration
            return method(*args, **kwargs)
        except Exception as e:
            self.logger.error(f"Kite API call failed: {e}")
            raise
    
    async def _publish_position_event(self, position: ZerodhaPosition) -> None:
        """Publish position update event."""
        try:
            if self.event_bus:
                event = EventFactory.create_system_event(
                    component="zerodha_position_manager",
                    severity="INFO",
                    message=f"Position updated: {position.tradingsymbol}",
                    event_type=EventType.TRADING_SIGNAL_GENERATED,  # Using signal for position updates
                    details=position.to_dict()
                )
                await self.event_bus.publish("trading.position.updated", event)
        
        except Exception as e:
            self.logger.error(f"Failed to publish position event: {e}")
    
    async def _publish_account_event(self, account: ZerodhaAccount) -> None:
        """Publish account update event."""
        try:
            if self.event_bus:
                event = EventFactory.create_system_event(
                    component="zerodha_position_manager",
                    severity="INFO",
                    message="Account updated",
                    event_type=EventType.HEALTH_CHECK,
                    details=account.to_dict()
                )
                await self.event_bus.publish("trading.account.updated", event)
        
        except Exception as e:
            self.logger.error(f"Failed to publish account event: {e}")
    
    # Statistics
    
    async def get_position_statistics(self) -> Dict[str, Any]:
        """Get position management statistics."""
        try:
            all_positions = await self.get_all_positions(include_zero=True)
            active_positions = [p for p in all_positions if p.quantity != 0]
            
            total_value = sum(abs(p.value) for p in active_positions)
            total_pnl = sum(p.pnl for p in active_positions)
            
            return {
                **self.stats,
                "total_positions": len(all_positions),
                "active_positions": len(active_positions),
                "total_value": float(total_value),
                "total_pnl": float(total_pnl),
                "api_error_rate": (self.stats["api_errors"] / max(1, self.stats["api_calls"]) * 100)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get position statistics: {e}")
            return {"error": str(e)}