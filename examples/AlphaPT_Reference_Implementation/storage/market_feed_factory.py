"""Factory for creating appropriate market feed manager based on environment configuration."""

import logging
from typing import Optional, Union

from core.config.settings import settings
from core.logging.logger import get_logger

logger = get_logger(__name__)


class MarketFeedFactory:
    """Factory class to create appropriate market feed manager based on configuration."""
    
    @staticmethod
    def create_market_feed_manager():
        """Create market feed manager based on MOCK_MARKET_FEED environment variable."""
        if settings.mock_market_feed:
            logger.info("🎭 Creating Mock Market Feed Manager")
            logger.info("Environment: MOCK_MARKET_FEED=true")
            
            # Import mock feed manager
            from mock_market_feed.mock_feed_manager import MockFeedManager
            return MockFeedManager()
        
        else:
            logger.info("📊 Creating Zerodha Market Feed Manager")
            logger.info("Environment: MOCK_MARKET_FEED=false (or not set)")
            
            # Import Zerodha market feed manager
            from zerodha_market_feed.zerodha_feed_manager import ZerodhaFeedManager
            return ZerodhaFeedManager()
    
    @staticmethod
    def is_mock_feed_enabled() -> bool:
        """Check if mock market feed is enabled."""
        return settings.mock_market_feed
    
    @staticmethod
    def is_auth_required() -> bool:
        """Check if authentication is required (not required for mock feed)."""
        return not MarketFeedFactory.is_mock_feed_enabled()
    
    @staticmethod
    def get_feed_type() -> str:
        """Get the current feed type."""
        return 'mock' if MarketFeedFactory.is_mock_feed_enabled() else 'zerodha'
    
    @staticmethod
    def should_skip_authentication() -> bool:
        """Check if authentication should be skipped based on configuration."""
        # Skip auth if mock feed is enabled OR if skip_token_validation is set in development
        return (MarketFeedFactory.is_mock_feed_enabled() or 
                settings.should_skip_auth())


# Global factory instance
market_feed_factory = MarketFeedFactory()