"""
Realistic Market Data Generator for Testing
Generates market data patterns that closely mimic real trading data without using actual live feeds.
CRITICAL: This is for testing only - never part of main application.
"""

import random
import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Generator
from dataclasses import dataclass
import asyncio

from core.schemas.events import MarketTick


@dataclass
class InstrumentConfig:
    """Configuration for generating realistic data for an instrument"""
    instrument_token: int
    symbol: str
    base_price: Decimal
    volatility: float  # Daily volatility (e.g., 0.02 = 2%)
    volume_base: int
    tick_size: Decimal
    lot_size: int


class RealisticMarketDataGenerator:
    """
    Generate realistic market data for testing purposes.
    Simulates price movements, volume patterns, and market behavior.
    """
    
    def __init__(self, seed: Optional[int] = None):
        if seed:
            random.seed(seed)
        
        self.instruments = {
            256265: InstrumentConfig(  # NIFTY 50
                instrument_token=256265,
                symbol="NIFTY 50",
                base_price=Decimal("21500.00"),
                volatility=0.015,  # 1.5% daily volatility
                volume_base=50000,
                tick_size=Decimal("0.05"),
                lot_size=50
            ),
            260105: InstrumentConfig(  # BANKNIFTY
                instrument_token=260105,
                symbol="BANKNIFTY",
                base_price=Decimal("45000.00"),
                volatility=0.025,  # 2.5% daily volatility
                volume_base=30000,
                tick_size=Decimal("0.05"),
                lot_size=25
            ),
            738561: InstrumentConfig(  # RELIANCE
                instrument_token=738561,
                symbol="RELIANCE",
                base_price=Decimal("2450.00"),
                volatility=0.020,  # 2% daily volatility
                volume_base=100000,
                tick_size=Decimal("0.05"),
                lot_size=1
            )
        }
        
        # Market state for each instrument
        self.current_prices = {}
        self.cumulative_volumes = {}
        self.last_tick_time = {}
        
        # Initialize starting states
        for token, config in self.instruments.items():
            self.current_prices[token] = config.base_price
            self.cumulative_volumes[token] = 0
            self.last_tick_time[token] = datetime.now(timezone.utc)
    
    def generate_price_movement(self, instrument_token: int, time_delta_seconds: float) -> Decimal:
        """
        Generate realistic price movement using geometric Brownian motion.
        This simulates how actual stock prices move with drift and volatility.
        """
        config = self.instruments[instrument_token]
        current_price = self.current_prices[instrument_token]
        
        # Geometric Brownian Motion parameters
        # drift = small positive trend (0.05% annual ~= 0.0002% per minute)
        annual_drift = 0.0005  # 0.05% annual drift
        drift_per_second = annual_drift / (365 * 24 * 3600)
        
        # Volatility per second (scale down from daily)
        volatility_per_second = config.volatility / math.sqrt(365 * 24 * 3600)
        
        # Random walk component
        random_factor = random.gauss(0, 1)  # Normal distribution
        
        # Price movement calculation
        dt = time_delta_seconds
        drift_component = drift_per_second * dt
        volatility_component = volatility_per_second * random_factor * math.sqrt(dt)
        
        # Apply movement: P(t+dt) = P(t) * exp((drift - vol²/2)*dt + vol*sqrt(dt)*random)
        price_multiplier = math.exp(drift_component - (volatility_per_second**2)/2 * dt + volatility_component)
        
        new_price = current_price * Decimal(str(price_multiplier))
        
        # Round to tick size
        tick_size = config.tick_size
        new_price = (new_price / tick_size).quantize(Decimal('1')) * tick_size
        
        self.current_prices[instrument_token] = new_price
        return new_price
    
    def generate_volume(self, instrument_token: int, price_movement_pct: float) -> int:
        """
        Generate realistic volume based on price movement and time of day.
        Higher volatility typically correlates with higher volume.
        """
        config = self.instruments[instrument_token]
        base_volume = config.volume_base
        
        # Volume increases with price volatility
        volatility_factor = 1 + abs(price_movement_pct) * 10
        
        # Time-of-day factor (higher volume during market open/close)
        now = datetime.now()
        hour = now.hour
        if 9 <= hour <= 10 or 15 <= hour <= 16:  # Market open/close hours
            time_factor = 1.5
        elif 11 <= hour <= 14:  # Mid-day
            time_factor = 0.8
        else:
            time_factor = 0.6
        
        # Random factor
        random_factor = random.uniform(0.5, 2.0)
        
        # Calculate volume
        volume = int(base_volume * volatility_factor * time_factor * random_factor / 100)
        volume = max(volume, 1)  # Ensure at least 1 share traded
        
        # Update cumulative volume
        self.cumulative_volumes[instrument_token] += volume
        
        return volume
    
    def generate_ohlc_data(self, instrument_token: int, current_price: Decimal):
        """Generate OHLC data for the current period"""
        from core.schemas.events import OHLCData
        
        # For simplicity, generate OHLC around current price
        price_float = float(current_price)
        variation = price_float * 0.001  # 0.1% variation
        
        high = current_price + Decimal(str(random.uniform(0, variation)))
        low = current_price - Decimal(str(random.uniform(0, variation)))
        open_price = current_price + Decimal(str(random.uniform(-variation/2, variation/2)))
        
        return OHLCData(
            open=open_price,
            high=max(high, current_price, open_price),
            low=min(low, current_price, open_price),
            close=current_price
        )
    
    def generate_market_depth(self, instrument_token: int, current_price: Decimal):
        """Generate realistic 5-level market depth"""
        from core.schemas.events import MarketDepth, MarketDepthLevel
        
        config = self.instruments[instrument_token]
        tick_size = config.tick_size
        
        # Generate buy orders (below current price)
        buy_levels = []
        for i in range(5):
            price = current_price - (tick_size * (i + 1))
            quantity = random.randint(50, 500) * config.lot_size
            orders = random.randint(1, 10)
            buy_levels.append(MarketDepthLevel(
                price=price,
                quantity=quantity,
                orders=orders
            ))
        
        # Generate sell orders (above current price)
        sell_levels = []
        for i in range(5):
            price = current_price + (tick_size * (i + 1))
            quantity = random.randint(50, 500) * config.lot_size
            orders = random.randint(1, 10)
            sell_levels.append(MarketDepthLevel(
                price=price,
                quantity=quantity,
                orders=orders
            ))
        
        return MarketDepth(
            buy=buy_levels,
            sell=sell_levels
        )
    
    def generate_tick(self, instrument_token: int, mode: str = "full") -> MarketTick:
        """Generate a single realistic market tick in PyKiteConnect format"""
        if instrument_token not in self.instruments:
            raise ValueError(f"Unknown instrument token: {instrument_token}")
        
        config = self.instruments[instrument_token]
        current_time = datetime.now(timezone.utc)
        
        # Calculate time since last tick
        last_time = self.last_tick_time[instrument_token]
        time_delta = (current_time - last_time).total_seconds()
        time_delta = max(time_delta, 0.1)  # Minimum 0.1 second
        
        # Generate new price
        old_price = self.current_prices[instrument_token]
        new_price = self.generate_price_movement(instrument_token, time_delta)
        
        # Calculate price movement percentage
        price_movement_pct = float((new_price - old_price) / old_price)
        
        # Generate volume
        last_traded_qty = self.generate_volume(instrument_token, price_movement_pct)
        
        # Update cumulative volume
        self.cumulative_volumes[instrument_token] += last_traded_qty
        
        # Update last tick time
        self.last_tick_time[instrument_token] = current_time
        
        # Generate base tick data (always present)
        tick_data = {
            "instrument_token": instrument_token,
            "last_price": new_price,
            "timestamp": current_time,
            "mode": mode,
            "tradable": True
        }
        
        # Add data based on mode (similar to PyKiteConnect)
        if mode in ["quote", "full"]:
            # Quote mode adds volume and basic market data
            tick_data.update({
                "volume_traded": self.cumulative_volumes[instrument_token],
                "last_traded_quantity": last_traded_qty,
                "average_traded_price": new_price * Decimal(str(random.uniform(0.999, 1.001))),
                "total_buy_quantity": random.randint(5000, 50000),
                "total_sell_quantity": random.randint(5000, 50000),
                "change": Decimal(str(price_movement_pct * 100)),  # Percentage change
                "last_trade_time": current_time,
                "exchange_timestamp": current_time
            })
            
            # Add OHLC data
            ohlc_data = self.generate_ohlc_data(instrument_token, new_price)
            tick_data["ohlc"] = ohlc_data
        
        if mode == "full":
            # Full mode adds market depth and OI data
            depth_data = self.generate_market_depth(instrument_token, new_price)
            tick_data["depth"] = depth_data
            
            # Add Open Interest for derivatives (simulate F&O instruments)
            if instrument_token in [260105]:  # BANKNIFTY - simulate as derivative
                tick_data.update({
                    "oi": random.randint(1000000, 5000000),
                    "oi_day_high": random.randint(3000000, 6000000), 
                    "oi_day_low": random.randint(500000, 2000000)
                })
        
        # Create market tick using the schema
        tick = MarketTick(**tick_data)
        return tick
    
    def generate_tick_stream(self, instrument_tokens: List[int], 
                           duration_seconds: int = 60,
                           ticks_per_second: float = 2.0) -> Generator[MarketTick, None, None]:
        """
        Generate a continuous stream of market ticks for multiple instruments.
        
        Args:
            instrument_tokens: List of instrument tokens to generate data for
            duration_seconds: How long to generate data for
            ticks_per_second: Average ticks per second per instrument
        """
        start_time = datetime.now(timezone.utc)
        tick_interval = 1.0 / ticks_per_second
        
        while True:
            current_time = datetime.now(timezone.utc)
            elapsed = (current_time - start_time).total_seconds()
            
            if elapsed > duration_seconds:
                break
            
            # Generate tick for random instrument
            instrument_token = random.choice(instrument_tokens)
            
            try:
                tick = self.generate_tick(instrument_token)
                yield tick
            except ValueError:
                # Skip unknown instruments
                continue
            
            # Wait for next tick (simulate realistic timing)
            import time
            time.sleep(tick_interval * random.uniform(0.5, 1.5))
    
    async def generate_async_tick_stream(self, instrument_tokens: List[int],
                                       duration_seconds: int = 60,
                                       ticks_per_second: float = 2.0) -> Generator[MarketTick, None, None]:
        """
        Async version of tick stream generation for use in async contexts.
        """
        start_time = datetime.now(timezone.utc)
        tick_interval = 1.0 / ticks_per_second
        
        while True:
            current_time = datetime.now(timezone.utc)
            elapsed = (current_time - start_time).total_seconds()
            
            if elapsed > duration_seconds:
                break
            
            # Generate tick for random instrument
            instrument_token = random.choice(instrument_tokens)
            
            try:
                tick = self.generate_tick(instrument_token)
                yield tick
            except ValueError:
                continue
            
            # Async sleep
            await asyncio.sleep(tick_interval * random.uniform(0.5, 1.5))
    
    def simulate_market_event(self, event_type: str, instrument_token: int):
        """
        Simulate major market events that cause significant price/volume changes.
        
        Args:
            event_type: "news", "circuit_breaker", "volume_spike"
            instrument_token: Instrument to affect
        """
        if instrument_token not in self.instruments:
            return
        
        config = self.instruments[instrument_token]
        current_price = self.current_prices[instrument_token]
        
        if event_type == "news":
            # Sudden price jump/drop
            direction = random.choice([-1, 1])
            movement = Decimal(str(random.uniform(0.02, 0.05)))  # 2-5% movement
            multiplier = Decimal('1') + Decimal(str(direction)) * movement
            new_price = current_price * multiplier
            self.current_prices[instrument_token] = new_price
            
        elif event_type == "circuit_breaker":
            # Halt trading (simulate by not updating price for a while)
            pass
            
        elif event_type == "volume_spike":
            # Increase base volume temporarily
            self.instruments[instrument_token].volume_base *= 3
            
    def get_current_snapshot(self) -> Dict[int, Dict]:
        """Get current market snapshot for all instruments"""
        snapshot = {}
        for instrument_token in self.instruments:
            config = self.instruments[instrument_token]
            snapshot[instrument_token] = {
                "symbol": config.symbol,
                "current_price": self.current_prices[instrument_token],
                "cumulative_volume": self.cumulative_volumes[instrument_token],
                "last_update": self.last_tick_time[instrument_token].isoformat()
            }
        return snapshot


# Predefined market scenarios for consistent testing
class MarketScenarios:
    """Predefined market scenarios for consistent testing"""
    
    @staticmethod
    def trending_up_market(generator: RealisticMarketDataGenerator):
        """Configure generator for upward trending market"""
        for token in generator.instruments:
            # Increase drift for upward trend
            generator.instruments[token].volatility *= 0.8  # Lower volatility
            
    @staticmethod
    def volatile_market(generator: RealisticMarketDataGenerator):
        """Configure generator for high volatility market"""
        for token in generator.instruments:
            generator.instruments[token].volatility *= 2.0  # Double volatility
            
    @staticmethod
    def low_volume_market(generator: RealisticMarketDataGenerator):
        """Configure generator for low volume market"""
        for token in generator.instruments:
            generator.instruments[token].volume_base //= 3  # Reduce volume
            
    @staticmethod
    def high_frequency_market(generator: RealisticMarketDataGenerator):
        """Configure generator for high frequency updates"""
        for token in generator.instruments:
            generator.instruments[token].volume_base *= 2  # Increase volume
            generator.instruments[token].volatility *= 1.5  # Increase volatility


if __name__ == "__main__":
    # Example usage
    generator = RealisticMarketDataGenerator(seed=42)  # Reproducible for testing
    
    # Generate some sample ticks
    print("Generating sample market ticks...")
    
    for i in range(10):
        tick = generator.generate_tick(256265)  # NIFTY
        print(f"Tick {i+1}: {tick.last_price} @ {tick.timestamp} (Vol: {tick.last_traded_quantity})")
        
    print("\nCurrent market snapshot:")
    snapshot = generator.get_current_snapshot()
    for token, data in snapshot.items():
        print(f"{data['symbol']}: ₹{data['current_price']} (Vol: {data['cumulative_volume']})")