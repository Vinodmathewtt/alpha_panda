"""Realistic market data generator for mock market feed.

This module generates realistic market movements using various models:
- Random walk with drift
- Mean reversion
- Volatility clustering
- Microstructure noise
- Volume-price relationships
"""

import math
import random
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from .models import MockTickData, InstrumentConfig, OHLCData
from .scenarios import ScenarioEngine, ScenarioType, MarketScenarios


@dataclass
class GeneratorState:
    """Internal state for price generator."""
    instrument_token: int
    current_price: float
    previous_prices: List[float]
    current_volatility: float
    volume_profile: Dict[int, int]  # Hour -> average volume
    last_update: datetime
    cumulative_volume: int = 0
    ticks_generated: int = 0
    
    def __post_init__(self):
        """Initialize derived fields."""
        if not self.previous_prices:
            self.previous_prices = [self.current_price] * 20
        if not self.volume_profile:
            self.volume_profile = self._default_volume_profile()
    
    def _default_volume_profile(self) -> Dict[int, int]:
        """Default intraday volume profile."""
        return {
            9: 100000,   # Market open - high volume
            10: 80000,
            11: 60000,
            12: 40000,   # Pre-lunch
            13: 20000,   # Lunch time - low volume
            14: 30000,   # Post-lunch
            15: 70000,   # Afternoon pickup
            16: 90000,   # Market close - high volume
        }


class RealisticDataGenerator:
    """Generates realistic market tick data using multiple models."""
    
    def __init__(self, seed: Optional[int] = None):
        """
        Initialize data generator.
        
        Args:
            seed: Random seed for reproducible testing
        """
        self.random = random.Random()
        if seed is not None:
            self.random.seed(seed)
        
        self.states: Dict[int, GeneratorState] = {}
        self.scenario_engines: Dict[int, ScenarioEngine] = {}
        
        # Market microstructure parameters
        self.tick_size = 0.05
        self.spread_factor = 0.001  # Typical bid-ask spread as % of price
        self.noise_factor = 0.0005  # Microstructure noise
        
    def initialize_instrument(
        self, 
        config: InstrumentConfig,
        scenario_type: ScenarioType = ScenarioType.RANGING
    ) -> MockTickData:
        """
        Initialize instrument for data generation.
        
        Args:
            config: Instrument configuration
            scenario_type: Initial market scenario
            
        Returns:
            Initial tick data for the instrument
        """
        # Initialize generator state
        self.states[config.instrument_token] = GeneratorState(
            instrument_token=config.instrument_token,
            current_price=config.base_price,
            previous_prices=[config.base_price] * 20,
            current_volatility=config.volatility,
            volume_profile={},
            last_update=datetime.now(timezone.utc),
        )
        
        # Initialize scenario engine
        scenario_config = MarketScenarios.get_scenario_config(scenario_type)
        self.scenario_engines[config.instrument_token] = ScenarioEngine(scenario_config)
        
        # Create initial tick
        return MockTickData.from_base_instrument(
            config.instrument_token,
            config.tradingsymbol,
            config.base_price,
            config.exchange
        )
    
    def generate_next_tick(
        self, 
        instrument_token: int,
        time_step: float = 1.0
    ) -> Optional[MockTickData]:
        """
        Generate next realistic tick for instrument.
        
        Args:
            instrument_token: Instrument token
            time_step: Time step in seconds
            
        Returns:
            New tick data or None if instrument not initialized
        """
        if instrument_token not in self.states:
            return None
        
        state = self.states[instrument_token]
        scenario = self.scenario_engines.get(instrument_token)
        
        # Generate price change
        price_change = self._generate_price_change(state, scenario, time_step)
        
        # Update price with realistic constraints
        new_price = self._apply_price_constraints(
            state.current_price + price_change, 
            state.current_price
        )
        
        # Generate volume
        volume = self._generate_volume(state, scenario)
        
        # Update state
        state.previous_prices.append(new_price)
        if len(state.previous_prices) > 100:
            state.previous_prices.pop(0)
        
        state.current_price = new_price
        state.cumulative_volume += volume
        state.ticks_generated += 1
        state.last_update = datetime.now(timezone.utc)
        
        # Update volatility (GARCH-like)
        self._update_volatility(state, price_change)
        
        # Create tick data
        tick = self._create_tick_from_state(state, volume)
        
        return tick
    
    def _generate_price_change(
        self, 
        state: GeneratorState, 
        scenario: Optional[ScenarioEngine],
        time_step: float
    ) -> float:
        """Generate realistic price change."""
        # Base random walk component
        volatility = state.current_volatility
        if scenario:
            volatility *= scenario.config.volatility_multiplier
        
        # Random walk with mean reversion
        base_change = self.random.gauss(0, volatility * math.sqrt(time_step))
        
        # Mean reversion component
        if len(state.previous_prices) >= 20:
            mean_price = sum(state.previous_prices[-20:]) / 20
            reversion_force = (mean_price - state.current_price) * 0.01
            base_change += reversion_force
        
        # Apply scenario effects
        if scenario:
            base_change = scenario.apply_scenario_to_price_change(
                base_change, state.current_price, time_step
            )
        
        # Add microstructure noise
        noise = self.random.gauss(0, state.current_price * self.noise_factor)
        base_change += noise
        
        return base_change
    
    def _apply_price_constraints(self, new_price: float, current_price: float) -> float:
        """Apply realistic price constraints."""
        # Minimum tick size constraint
        price_diff = new_price - current_price
        ticks = round(price_diff / self.tick_size)
        constrained_price = current_price + (ticks * self.tick_size)
        
        # Ensure positive price
        return max(0.05, constrained_price)
    
    def _generate_volume(
        self, 
        state: GeneratorState, 
        scenario: Optional[ScenarioEngine]
    ) -> int:
        """Generate realistic trade volume."""
        # Base volume from time of day
        current_hour = state.last_update.hour
        base_volume = state.volume_profile.get(current_hour, 50000)
        
        # Scale by price volatility
        recent_volatility = self._calculate_recent_volatility(state)
        volatility_multiplier = 1.0 + (recent_volatility * 10)
        
        # Apply scenario effects
        scenario_multiplier = 1.0
        if scenario:
            scenario_multiplier = scenario.get_volume_multiplier()
        
        # Generate volume with some randomness
        expected_volume = base_volume * volatility_multiplier * scenario_multiplier
        volume = max(1, int(self.random.gammavariate(2, expected_volume / 100)))
        
        return volume
    
    def _calculate_recent_volatility(self, state: GeneratorState) -> float:
        """Calculate recent price volatility."""
        if len(state.previous_prices) < 10:
            return state.current_volatility
        
        recent_prices = state.previous_prices[-10:]
        returns = []
        for i in range(1, len(recent_prices)):
            if recent_prices[i-1] > 0:
                returns.append((recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1])
        
        if not returns:
            return state.current_volatility
        
        # Calculate standard deviation of returns
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        return math.sqrt(variance)
    
    def _update_volatility(self, state: GeneratorState, price_change: float):
        """Update volatility using GARCH-like model."""
        if state.current_price <= 0:
            return
        
        # Current return
        current_return = price_change / state.current_price
        
        # GARCH(1,1) style update
        alpha = 0.1  # Weight on recent shock
        beta = 0.85  # Weight on previous volatility
        omega = 0.000001  # Long-term volatility base
        
        new_volatility = math.sqrt(
            omega + alpha * (current_return ** 2) + beta * (state.current_volatility ** 2)
        )
        
        # Bound volatility
        state.current_volatility = max(0.005, min(0.1, new_volatility))
    
    def _create_tick_from_state(self, state: GeneratorState, volume: int) -> MockTickData:
        """Create tick data from current state."""
        # Calculate OHLC for the day (simplified)
        prices = state.previous_prices[-100:] if len(state.previous_prices) >= 100 else state.previous_prices
        
        ohlc = OHLCData(
            open=prices[0] if prices else state.current_price,
            high=max(prices) if prices else state.current_price,
            low=min(prices) if prices else state.current_price,
            close=state.current_price
        )
        
        # Calculate average traded price (simplified)
        avg_price = sum(prices[-20:]) / len(prices[-20:]) if len(prices) >= 20 else state.current_price
        
        # Generate market sentiment indicators
        total_buy = int(volume * self.random.uniform(0.4, 0.6))
        total_sell = volume - total_buy
        
        # Create tick data
        tick = MockTickData(
            instrument_token=state.instrument_token,
            last_price=state.current_price,
            last_traded_quantity=volume,
            average_traded_price=avg_price,
            volume_traded=state.cumulative_volume,
            total_buy_quantity=total_buy,
            total_sell_quantity=total_sell,
            ohlc=ohlc,
            exchange_timestamp=state.last_update
        )
        
        return tick
    
    def update_scenario(
        self, 
        instrument_token: int, 
        scenario_type: ScenarioType
    ) -> bool:
        """
        Update scenario for specific instrument.
        
        Args:
            instrument_token: Instrument token
            scenario_type: New scenario type
            
        Returns:
            True if scenario updated successfully
        """
        if instrument_token not in self.states:
            return False
        
        scenario_config = MarketScenarios.get_scenario_config(scenario_type)
        self.scenario_engines[instrument_token] = ScenarioEngine(scenario_config)
        
        return True
    
    def get_instrument_statistics(self, instrument_token: int) -> Dict[str, float]:
        """Get statistics for instrument."""
        if instrument_token not in self.states:
            return {}
        
        state = self.states[instrument_token]
        recent_prices = state.previous_prices[-50:]
        
        return {
            "current_price": state.current_price,
            "volatility": state.current_volatility,
            "price_range_50": max(recent_prices) - min(recent_prices) if recent_prices else 0,
            "average_price_50": sum(recent_prices) / len(recent_prices) if recent_prices else 0,
            "cumulative_volume": state.cumulative_volume,
            "ticks_generated": state.ticks_generated,
        }
    
    def reset_instrument(self, instrument_token: int, base_price: Optional[float] = None):
        """Reset instrument state."""
        if instrument_token not in self.states:
            return
        
        state = self.states[instrument_token]
        if base_price:
            state.current_price = base_price
        
        state.previous_prices = [state.current_price] * 20
        state.cumulative_volume = 0
        state.ticks_generated = 0
        state.current_volatility = 0.02  # Reset to 2%
        state.last_update = datetime.now(timezone.utc)


class HistoricalDataReplay:
    """Replay historical market data for backtesting."""
    
    def __init__(self, historical_data: List[Dict]):
        """
        Initialize with historical tick data.
        
        Args:
            historical_data: List of historical tick dictionaries
        """
        self.historical_data = sorted(historical_data, key=lambda x: x.get('timestamp', ''))
        self.current_index = 0
        self.replay_speed = 1.0  # 1.0 = real-time
    
    def set_replay_speed(self, speed: float):
        """Set replay speed multiplier."""
        self.replay_speed = max(0.1, min(100.0, speed))
    
    def get_next_tick(self) -> Optional[MockTickData]:
        """Get next tick from historical data."""
        if self.current_index >= len(self.historical_data):
            return None
        
        data = self.historical_data[self.current_index]
        self.current_index += 1
        
        # Convert to MockTickData format
        return self._convert_historical_to_mock(data)
    
    def _convert_historical_to_mock(self, data: Dict) -> MockTickData:
        """Convert historical data format to MockTickData."""
        return MockTickData(
            instrument_token=data.get('instrument_token', 0),
            last_price=data.get('last_price', 0.0),
            last_traded_quantity=data.get('last_quantity', 0),
            average_traded_price=data.get('average_price', 0.0),
            volume_traded=data.get('volume', 0),
            # Add other fields as needed from historical format
        )
    
    def seek_to_time(self, target_time: datetime) -> bool:
        """Seek to specific time in historical data."""
        for i, data in enumerate(self.historical_data):
            timestamp = data.get('timestamp')
            if timestamp and datetime.fromisoformat(timestamp) >= target_time:
                self.current_index = i
                return True
        return False
    
    def get_progress(self) -> float:
        """Get replay progress as percentage."""
        if not self.historical_data:
            return 100.0
        return (self.current_index / len(self.historical_data)) * 100.0