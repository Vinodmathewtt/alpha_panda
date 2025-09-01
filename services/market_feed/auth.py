# alphaP/services/market_feed/auth.py

from kiteconnect import KiteTicker
from core.config.settings import Settings
from services.auth.service import AuthService
from core.logging import get_api_logger_safe

logger = get_api_logger_safe("market_feed_auth")

class BrokerAuthenticator:
    """
    Handles the machine-to-machine authentication for Zerodha KiteTicker.
    It retrieves the established session from the AuthService.
    """

    def __init__(self, auth_service: AuthService, settings: Settings):
        self._auth_service = auth_service
        self._settings = settings

    async def get_ticker(self) -> KiteTicker:
        """
        Performs authentication and returns a ready-to-use KiteTicker instance.
        """
        if not self._auth_service.is_authenticated():
            raise ConnectionError("Cannot start market feed: No authenticated Zerodha session found.")

        try:
            # Use public API instead of reaching into protected attributes
            access_token = await self._auth_service.get_access_token()
            api_key = self._settings.zerodha.api_key

            if not all([api_key, access_token]):
                raise ValueError("Zerodha API key or access token is missing.")

            # Create and return the WebSocket Ticker instance
            ticker = KiteTicker(api_key, access_token)
            logger.info("BrokerAuthenticator successfully created a KiteTicker instance.")
            return ticker

        except Exception as e:
            logger.error(f"FATAL: Broker authentication for market feed failed: {e}")
            raise
