# alphaP/services/auth/kite_client.py

"""Zerodha KiteConnect integration utilities."""

import logging
from typing import Any, Dict, Optional
from core.config.settings import Settings
from .exceptions import AuthenticationError

logger = logging.getLogger(__name__)

try:
    from kiteconnect import KiteConnect
    KITECONNECT_AVAILABLE = True
except ImportError:
    logger.warning("KiteConnect not available. Install with: pip install kiteconnect")
    KITECONNECT_AVAILABLE = False
    KiteConnect = None

class KiteClientWrapper:
    """A simplified wrapper for the KiteConnect client."""

    def __init__(self):
        self.kite: Optional[KiteConnect] = None
        self._initialized = False

    def initialize(self, settings: Settings) -> bool:
        """Initializes the client with the API key."""
        if not KITECONNECT_AVAILABLE:
            return False

        try:
            api_key = settings.zerodha.api_key
            if not api_key:
                logger.error("Zerodha API key is not configured.")
                return False

            self.kite = KiteConnect(api_key=api_key)
            self._initialized = True
            logger.info("KiteConnect client initialized.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize KiteConnect client: {e}")
            return False

    def is_initialized(self) -> bool:
        """Check if the client is initialized."""
        return self._initialized and self.kite is not None

    def set_access_token(self, access_token: str):
        """Sets the access token for subsequent API calls."""
        if not self.is_initialized():
            raise AuthenticationError("Kite client not initialized.")
        self.kite.set_access_token(access_token)

    def get_profile(self) -> Dict[str, Any]:
        """Fetches the user profile from Zerodha to validate a token."""
        if not self.is_initialized():
            raise AuthenticationError("Kite client not initialized.")
        return self.kite.profile()

    def get_kite_instance(self) -> Optional[KiteConnect]:
        """Returns the KiteConnect instance if initialized and authenticated."""
        if self.is_initialized():
            return self.kite
        return None

    def get_login_url(self) -> str:
        """Get the login URL for OAuth authentication."""
        if not self.is_initialized():
            raise AuthenticationError("Kite client not initialized.")
        return self.kite.login_url()

    def generate_session(self, request_token: str, api_secret: str) -> Dict[str, Any]:
        """Generate access token from request token."""
        if not self.is_initialized():
            raise AuthenticationError("Kite client not initialized.")
        return self.kite.generate_session(request_token, api_secret)

# Global singleton instance
kite_client = KiteClientWrapper()