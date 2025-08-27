"""Centralized KiteConnect client wrapper following reference implementation."""

import logging
from typing import Any, Dict, Optional

from kiteconnect import KiteConnect

from core.config.settings import Settings

logger = logging.getLogger(__name__)


class KiteClientWrapper:
    """Centralized KiteConnect client wrapper."""

    def __init__(self):
        self.kite: Optional[KiteConnect] = None
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self._initialized = False

        logger.info("KiteClientWrapper initialized")

    def initialize(self, settings: Settings) -> bool:
        """Initialize KiteConnect client with API credentials."""
        try:
            if not settings.trading.kite_api_key or not settings.trading.kite_api_secret:
                logger.warning("Kite API credentials not configured")
                return False

            self.api_key = settings.trading.kite_api_key
            self.api_secret = settings.trading.kite_api_secret

            # Create KiteConnect instance
            self.kite = KiteConnect(api_key=self.api_key)
            self._initialized = True

            logger.info("KiteConnect client initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize KiteConnect client: {e}")
            return False

    def get_login_url(self) -> str:
        """Get Zerodha login URL for OAuth authentication."""
        if not self.kite:
            raise RuntimeError("KiteConnect client not initialized")

        try:
            login_url = self.kite.login_url()
            logger.info("Generated Zerodha login URL")
            return login_url
        except Exception as e:
            logger.error(f"Failed to generate login URL: {e}")
            raise

    def generate_session(self, request_token: str) -> Dict[str, Any]:
        """Generate session using request token."""
        if not self.kite or not self.api_secret:
            raise RuntimeError("KiteConnect client not properly initialized")

        try:
            session_data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            logger.info("Generated session successfully")
            return session_data
        except Exception as e:
            logger.error(f"Failed to generate session: {e}")
            raise

    def set_access_token(self, access_token: str) -> None:
        """Set access token for API calls."""
        if not self.kite:
            raise RuntimeError("KiteConnect client not initialized")

        self.kite.set_access_token(access_token)
        logger.debug("Access token set in KiteConnect client")

    def get_profile(self) -> Dict[str, Any]:
        """Get user profile from Zerodha API."""
        if not self.kite:
            raise RuntimeError("KiteConnect client not initialized")

        try:
            profile = self.kite.profile()
            logger.debug("Retrieved user profile")
            return profile
        except Exception as e:
            logger.error(f"Failed to get profile: {e}")
            raise

    def validate_token(self, access_token: str) -> bool:
        """Validate access token by making a test API call."""
        if not self.kite:
            return False

        try:
            # Temporarily set token and test with profile call
            original_token = getattr(self.kite, "access_token", None)
            self.kite.set_access_token(access_token)

            # Test API call
            self.kite.profile()

            # Restore original token if it existed
            if original_token:
                self.kite.set_access_token(original_token)

            return True

        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            return False

    def is_initialized(self) -> bool:
        """Check if client is properly initialized."""
        return self._initialized and self.kite is not None

    def get_kite_instance(self) -> Optional[KiteConnect]:
        """Get the underlying KiteConnect instance."""
        return self.kite


# Global instance
kite_client = KiteClientWrapper()
