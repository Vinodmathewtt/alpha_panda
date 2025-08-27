"""Market scenario configurations for realistic simulation.

This module provides different market condition scenarios:
- Trending markets (bullish/bearish)
- Ranging/sideways markets
- High volatility periods
- Low volatility periods
- Market open/close behaviors
"""

import math
import random
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass


class ScenarioType(str, Enum):
    """Market scenario types."""
    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear" 
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    MARKET_OPEN = "market_open"
    MARKET_CLOSE = "market_close"
    LUNCH_TIME = "lunch_time"
    BREAKOUT = "breakout"
    REVERSAL = "reversal"


@dataclass
class ScenarioConfig:
    """Configuration for market scenario."""
    scenario_type: ScenarioType
    volatility_multiplier: float = 1.0
    trend_strength: float = 0.0  # -1 (strong bear) to 1 (strong bull)
    volume_multiplier: float = 1.0
    tick_frequency_multiplier: float = 1.0
    duration_minutes: Optional[int] = None  # None for indefinite
    description: str = ""


class MarketScenarios:
    """Pre-configured market scenarios for realistic simulation."""
    
    @staticmethod
    def get_scenario_configs() -> Dict[ScenarioType, ScenarioConfig]:
        """Get all predefined scenario configurations."""
        return {
            ScenarioType.TRENDING_BULL: ScenarioConfig(
                scenario_type=ScenarioType.TRENDING_BULL,
                volatility_multiplier=1.2,
                trend_strength=0.7,
                volume_multiplier=1.5,
                tick_frequency_multiplier=1.3,
                description="Strong bullish trend with increased activity"
            ),
            
            ScenarioType.TRENDING_BEAR: ScenarioConfig(
                scenario_type=ScenarioType.TRENDING_BEAR,
                volatility_multiplier=1.4,
                trend_strength=-0.8,
                volume_multiplier=1.8,
                tick_frequency_multiplier=1.5,
                description="Strong bearish trend with high selling pressure"
            ),
            
            ScenarioType.RANGING: ScenarioConfig(
                scenario_type=ScenarioType.RANGING,
                volatility_multiplier=0.6,
                trend_strength=0.0,
                volume_multiplier=0.8,
                tick_frequency_multiplier=0.9,
                description="Sideways market with low directional movement"
            ),
            
            ScenarioType.HIGH_VOLATILITY: ScenarioConfig(
                scenario_type=ScenarioType.HIGH_VOLATILITY,
                volatility_multiplier=2.5,
                trend_strength=0.0,
                volume_multiplier=2.0,
                tick_frequency_multiplier=2.0,
                description="High volatility with rapid price swings"
            ),
            
            ScenarioType.LOW_VOLATILITY: ScenarioConfig(
                scenario_type=ScenarioType.LOW_VOLATILITY,
                volatility_multiplier=0.3,
                trend_strength=0.0,
                volume_multiplier=0.5,
                tick_frequency_multiplier=0.6,
                description="Low volatility with minimal price movement"
            ),
            
            ScenarioType.MARKET_OPEN: ScenarioConfig(
                scenario_type=ScenarioType.MARKET_OPEN,
                volatility_multiplier=2.0,
                trend_strength=0.3,
                volume_multiplier=3.0,
                tick_frequency_multiplier=2.5,
                duration_minutes=30,
                description="Market opening with high activity and gaps"
            ),
            
            ScenarioType.MARKET_CLOSE: ScenarioConfig(
                scenario_type=ScenarioType.MARKET_CLOSE,
                volatility_multiplier=1.5,
                trend_strength=0.0,
                volume_multiplier=2.0,
                tick_frequency_multiplier=1.8,
                duration_minutes=30,
                description="Market closing with increased activity"
            ),
            
            ScenarioType.LUNCH_TIME: ScenarioConfig(
                scenario_type=ScenarioType.LUNCH_TIME,
                volatility_multiplier=0.4,
                trend_strength=0.0,
                volume_multiplier=0.3,
                tick_frequency_multiplier=0.5,
                duration_minutes=90,
                description="Lunch time with reduced activity"
            ),
            
            ScenarioType.BREAKOUT: ScenarioConfig(
                scenario_type=ScenarioType.BREAKOUT,
                volatility_multiplier=2.0,
                trend_strength=0.9,
                volume_multiplier=2.5,
                tick_frequency_multiplier=2.2,
                duration_minutes=15,
                description="Price breakout with strong directional move"
            ),
            
            ScenarioType.REVERSAL: ScenarioConfig(
                scenario_type=ScenarioType.REVERSAL,
                volatility_multiplier=1.8,
                trend_strength=0.0,  # Will reverse during scenario
                volume_multiplier=1.8,
                tick_frequency_multiplier=1.6,
                duration_minutes=20,
                description="Market reversal pattern"
            ),
        }
    
    @staticmethod
    def get_scenario_config(scenario_type: ScenarioType) -> ScenarioConfig:
        """Get configuration for specific scenario type."""
        configs = MarketScenarios.get_scenario_configs()
        return configs.get(scenario_type, configs[ScenarioType.RANGING])


class ScenarioEngine:
    """Engine for applying market scenarios to price generation."""
    
    def __init__(self, scenario_config: ScenarioConfig):
        self.config = scenario_config
        self.start_time = None
        self.elapsed_time = 0
        self.base_random = random.Random()
        self.base_random.seed(42)  # Deterministic for testing
        
    def apply_scenario_to_price_change(
        self, 
        base_change: float, 
        current_price: float,
        time_step: float = 1.0
    ) -> float:
        """Apply scenario effects to a base price change."""
        self.elapsed_time += time_step
        
        # Apply volatility multiplier
        adjusted_change = base_change * self.config.volatility_multiplier
        
        # Apply trend bias
        trend_component = self._calculate_trend_component(current_price, time_step)
        adjusted_change += trend_component
        
        # Apply scenario-specific modifications
        scenario_modifier = self._get_scenario_modifier()
        adjusted_change *= scenario_modifier
        
        return adjusted_change
    
    def _calculate_trend_component(self, current_price: float, time_step: float) -> float:
        """Calculate trend contribution to price change."""
        if self.config.trend_strength == 0:
            return 0.0
        
        # Base trend component (percentage of price)
        base_trend = current_price * (self.config.trend_strength * 0.0001 * time_step)
        
        # Add some randomness to trend
        trend_noise = self.base_random.gauss(0, abs(base_trend) * 0.3)
        
        return base_trend + trend_noise
    
    def _get_scenario_modifier(self) -> float:
        """Get scenario-specific price change modifier."""
        scenario = self.config.scenario_type
        
        if scenario == ScenarioType.MARKET_OPEN:
            # Higher volatility at the beginning, tapering off
            time_factor = max(0.3, 1.0 - (self.elapsed_time / 1800))  # 30 minutes
            return 0.5 + (time_factor * 1.5)
        
        elif scenario == ScenarioType.MARKET_CLOSE:
            # Increasing activity towards the end
            time_factor = min(2.0, 0.5 + (self.elapsed_time / 900))  # 15 minutes
            return time_factor
        
        elif scenario == ScenarioType.LUNCH_TIME:
            # Consistently low activity
            return 0.3
        
        elif scenario == ScenarioType.BREAKOUT:
            # Strong initial move, then consolidation
            if self.elapsed_time < 300:  # First 5 minutes
                return 2.0
            else:
                return 0.7
        
        elif scenario == ScenarioType.REVERSAL:
            # Gradual reversal over time
            progress = self.elapsed_time / (self.config.duration_minutes * 60)
            if progress < 0.5:
                return 1.0 + progress  # Accelerating
            else:
                return 2.0 - progress  # Decelerating
        
        elif scenario == ScenarioType.HIGH_VOLATILITY:
            # Random spikes in volatility
            if self.base_random.random() < 0.1:  # 10% chance of spike
                return 3.0
            else:
                return 1.5
        
        elif scenario == ScenarioType.LOW_VOLATILITY:
            # Consistently low volatility
            return 0.3
        
        else:
            return 1.0
    
    def get_volume_multiplier(self) -> float:
        """Get current volume multiplier based on scenario."""
        base_multiplier = self.config.volume_multiplier
        
        scenario = self.config.scenario_type
        
        if scenario == ScenarioType.MARKET_OPEN:
            # High volume at open, declining
            time_factor = max(0.5, 1.0 - (self.elapsed_time / 1800))
            return base_multiplier * (0.5 + time_factor * 1.5)
        
        elif scenario == ScenarioType.BREAKOUT:
            # Volume spike during breakout
            if self.elapsed_time < 600:  # First 10 minutes
                return base_multiplier * 2.0
            else:
                return base_multiplier * 0.8
        
        else:
            return base_multiplier
    
    def get_tick_frequency_multiplier(self) -> float:
        """Get current tick frequency multiplier based on scenario."""
        return self.config.tick_frequency_multiplier
    
    def is_scenario_complete(self) -> bool:
        """Check if scenario duration is complete."""
        if self.config.duration_minutes is None:
            return False
        
        duration_seconds = self.config.duration_minutes * 60
        return self.elapsed_time >= duration_seconds
    
    def reset(self):
        """Reset scenario timing."""
        self.elapsed_time = 0
        self.start_time = None


class ScenarioScheduler:
    """Scheduler for rotating through different market scenarios."""
    
    def __init__(self, scenario_sequence: Optional[Dict[int, ScenarioType]] = None):
        """
        Initialize with scenario sequence.
        
        Args:
            scenario_sequence: Dict mapping minute of day to scenario type
                              e.g., {540: MARKET_OPEN, 570: TRENDING_BULL, ...}
                              If None, uses default trading day schedule
        """
        self.scenario_sequence = scenario_sequence or self._get_default_schedule()
        self.current_scenario_engine: Optional[ScenarioEngine] = None
        self.current_minute = 0
        
    def _get_default_schedule(self) -> Dict[int, ScenarioType]:
        """Get default trading day scenario schedule."""
        return {
            540: ScenarioType.MARKET_OPEN,      # 9:00 AM
            570: ScenarioType.TRENDING_BULL,     # 9:30 AM  
            660: ScenarioType.RANGING,           # 11:00 AM
            750: ScenarioType.LUNCH_TIME,        # 12:30 PM
            840: ScenarioType.HIGH_VOLATILITY,   # 2:00 PM
            900: ScenarioType.TRENDING_BEAR,     # 3:00 PM
            945: ScenarioType.MARKET_CLOSE,      # 3:45 PM
        }
    
    def update_minute(self, minute_of_day: int) -> Optional[ScenarioEngine]:
        """
        Update current minute and return new scenario engine if changed.
        
        Args:
            minute_of_day: Current minute of day (0-1439)
            
        Returns:
            New ScenarioEngine if scenario changed, None otherwise
        """
        self.current_minute = minute_of_day
        
        # Check if we need to switch scenarios
        if minute_of_day in self.scenario_sequence:
            scenario_type = self.scenario_sequence[minute_of_day]
            config = MarketScenarios.get_scenario_config(scenario_type)
            self.current_scenario_engine = ScenarioEngine(config)
            return self.current_scenario_engine
        
        return None
    
    def get_current_scenario_engine(self) -> Optional[ScenarioEngine]:
        """Get current active scenario engine."""
        return self.current_scenario_engine