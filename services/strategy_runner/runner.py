# Individual strategy host/container
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from decimal import Decimal
from strategies.base import BaseStrategy, MarketData
from core.schemas.events import EventType, TradingSignal
from core.schemas.topics import TopicNames, PartitioningKeys
from core.logging import get_logger


class StrategyRunner:
    """Individual strategy host/container - manages one strategy instance"""
    
    def __init__(self, strategy: BaseStrategy):
        self.strategy = strategy
        self.logger = get_logger(f"strategy_runner.{strategy.strategy_id}")
    
    def _parse_timestamp(self, raw_timestamp) -> datetime:
        """Parse timestamp with robust error handling and timezone awareness"""
        if raw_timestamp is None:
            return datetime.now(timezone.utc)
        
        # If already a datetime object, ensure it has timezone info
        if isinstance(raw_timestamp, datetime):
            if raw_timestamp.tzinfo is None:
                # Assume UTC if no timezone info
                return raw_timestamp.replace(tzinfo=timezone.utc)
            return raw_timestamp
        
        # Try to parse string timestamps
        if isinstance(raw_timestamp, str):
            try:
                # Try parsing ISO format
                dt = datetime.fromisoformat(raw_timestamp)
                # Add UTC timezone if none specified
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                # Try other common formats
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]:
                    try:
                        dt = datetime.strptime(raw_timestamp, fmt)
                        return dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                
                self.logger.warning("Failed to parse timestamp, using current time", 
                                   raw_timestamp=raw_timestamp)
                return datetime.now(timezone.utc)
        
        # For numeric timestamps (Unix epoch)
        if isinstance(raw_timestamp, (int, float)):
            try:
                return datetime.fromtimestamp(raw_timestamp, tz=timezone.utc)
            except (ValueError, OSError):
                self.logger.warning("Invalid numeric timestamp, using current time", 
                                   raw_timestamp=raw_timestamp)
                return datetime.now(timezone.utc)
        
        # Fallback to current time
        self.logger.warning("Unknown timestamp format, using current time", 
                           raw_timestamp=raw_timestamp, 
                           timestamp_type=type(raw_timestamp))
        return datetime.now(timezone.utc)
        
    async def process_market_data(self, market_tick_data: Dict[str, Any]) -> List[TradingSignal]:
        """Process market tick and generate signals with robust parsing"""
        
        try:
            # Validate required fields first
            instrument_token = market_tick_data.get("instrument_token")
            if not instrument_token:
                self.logger.error("Missing required field 'instrument_token'", 
                                tick_data=market_tick_data)
                return []
            
            # Safe last_price parsing with validation
            raw_price = market_tick_data.get("last_price")
            if raw_price is None or raw_price == "":
                self.logger.warning("Missing last_price, skipping tick", 
                                   instrument_token=instrument_token)
                return []
            
            try:
                last_price = Decimal(str(raw_price))
                if last_price <= 0:
                    self.logger.warning("Invalid price <= 0, skipping tick", 
                                       instrument_token=instrument_token, 
                                       price=raw_price)
                    return []
            except (ValueError, TypeError, ArithmeticError) as e:
                self.logger.error("Failed to parse last_price", 
                                 instrument_token=instrument_token,
                                 raw_price=raw_price, error=str(e))
                return []
            
            # Safe timestamp parsing with timezone awareness and fallback
            timestamp = self._parse_timestamp(market_tick_data.get("timestamp"))
            
            # Safe volume parsing - MarketTick uses volume_traded field
            volume_traded = market_tick_data.get("volume_traded")
            if volume_traded is not None:
                try:
                    volume_traded = int(volume_traded) if volume_traded != "" else None
                except (ValueError, TypeError):
                    volume_traded = None
                    
            # Convert to MarketTick model (the standardized schema)
            market_data = MarketData(
                instrument_token=instrument_token,
                last_price=last_price,
                timestamp=timestamp,
                volume_traded=volume_traded,
                ohlc=market_tick_data.get("ohlc")
            )
            
            # Generate signals from strategy
            signals = list(self.strategy.on_market_data(market_data))
            
            if signals:
                self.logger.info(
                    "Generated trading signals",
                    count=len(signals),
                    strategy_id=self.strategy.strategy_id,
                    instrument_token=market_tick_data.get("instrument_token")
                )
                
                # Log individual signal details
                for signal in signals:
                    self.logger.info(
                        "Signal details",
                        strategy_id=signal.strategy_id,
                        instrument_token=signal.instrument_token,
                        signal_type=signal.signal_type,
                        quantity=signal.quantity,
                        confidence=signal.confidence
                    )
            
            # FIXED: Return signals instead of emitting via callback
            return signals
                
        except Exception as e:
            self.logger.error(
                "Error processing market data",
                strategy_id=self.strategy.strategy_id,
                instrument_token=market_tick_data.get("instrument_token"),
                error=str(e)
            )
            # Return empty list on error instead of raising
            return []