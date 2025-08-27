# Individual strategy host/container
from typing import Dict, Any, List, Optional
from datetime import datetime
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
        
    async def process_market_data(self, market_tick_data: Dict[str, Any]) -> List[TradingSignal]:
        """Process market tick and generate signals - FIXED: Returns signals instead of using callback"""
        
        try:
            # Convert to MarketData model
            market_data = MarketData(
                instrument_token=market_tick_data["instrument_token"],
                last_price=Decimal(str(market_tick_data["last_price"])),
                volume=market_tick_data.get("volume_traded"),
                timestamp=datetime.fromisoformat(market_tick_data["timestamp"]) 
                    if isinstance(market_tick_data["timestamp"], str) 
                    else market_tick_data["timestamp"],
                ohlc=market_tick_data.get("ohlc")
            )
            
            # Generate signals from strategy
            signals = list(self.strategy.on_market_data(market_data))
            
            if signals:
                self.logger.info(
                    "Generated trading signals",
                    count=len(signals),
                    strategy_id=self.strategy.strategy_id,
                    instrument_token=market_tick_data["instrument_token"]
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