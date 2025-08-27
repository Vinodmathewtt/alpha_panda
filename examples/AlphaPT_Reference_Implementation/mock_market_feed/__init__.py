"""Mock market feed module for development and testing.

This module provides realistic market data simulation without external dependencies.
It follows the zerodha market feed interface exactly for seamless switching.

Key Components:
- MockFeedManager: Main orchestrator for mock market data
- RealisticDataGenerator: Generates realistic market movements
- ConfigurableScenarios: Different market condition simulations
- Historical data replay capabilities

⚠️ IMPORTANT: This module is for development/testing ONLY and will be 
removed during production deployment.
"""

from .mock_feed_manager import MockFeedManager

# Global instance for API access
# This will be initialized by the application
mock_feed_manager: MockFeedManager = None
from .data_generator import RealisticDataGenerator
from .scenarios import MarketScenarios, ScenarioType
from .models import MockTickData, MarketDepth

__all__ = [
    "MockFeedManager",
    "mock_feed_manager",
    "RealisticDataGenerator", 
    "MarketScenarios",
    "ScenarioType",
    "MockTickData",
    "MarketDepth",
]