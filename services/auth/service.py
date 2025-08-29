# alphaP/services/auth/service.py

import asyncio
import logging
from typing import Optional

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from .auth_manager import AuthManager
from .models import LoginRequest, LoginResponse, AuthProvider, AuthStatus, UserProfile

logger = logging.getLogger(__name__)

class AuthService:
    """High-level authentication service for managing trading sessions."""

    def __init__(self, settings: Settings, db_manager: DatabaseManager, shutdown_event: Optional[asyncio.Event] = None):
        self.settings = settings
        self.db_manager = db_manager
        self.auth_manager = AuthManager(settings, db_manager, shutdown_event)

    async def start(self):
        """Initializes the authentication manager."""
        await self.auth_manager.initialize()
        logger.info(f"AuthService started. Current status: {self.auth_manager.status.value}")

    async def stop(self):
        """Stops the authentication manager."""
        await self.auth_manager.stop()
        logger.info("AuthService stopped.")

    async def get_access_token(self) -> Optional[str]:
        """
        Public method to get access token for authenticated services.
        Returns None if not authenticated.
        """
        if not self.is_authenticated():
            return None
        
        try:
            return await self.auth_manager.get_access_token()
        except Exception as e:
            logger.error(f"Failed to retrieve access token: {e}")
            return None

    async def get_status(self) -> bool:
        """Returns the current status of the authentication service."""
        return self.auth_manager.status != AuthStatus.STOPPED

    async def establish_zerodha_session(self, access_token: str) -> LoginResponse:
        """
        Establishes a new trading session using a pre-authorized Zerodha access token.
        """
        if not access_token:
            return LoginResponse(success=False, message="Access token is required.")

        try:
            session_data = await self.auth_manager.login_with_token(access_token)
            return LoginResponse(
                success=True,
                message="Zerodha session established successfully.",
                user_id=session_data.user_id,
                session_id=session_data.session_id
            )
        except Exception as e:
            logger.error(f"Failed to establish Zerodha session: {e}")
            return LoginResponse(success=False, message=str(e))

    def is_authenticated(self) -> bool:
        """Checks if a valid trading session is active."""
        return self.auth_manager.status == AuthStatus.AUTHENTICATED

    async def get_current_user_profile(self) -> Optional[UserProfile]:
        """Returns the current user profile if authenticated."""
        if not self.is_authenticated():
            return None
        
        # Get user profile from the AuthManager
        if self.auth_manager._user_profile:
            return self.auth_manager._user_profile
        
        # If not cached, try to fetch from session and validate with Zerodha API
        try:
            from .kite_client import kite_client
            access_token = await self.auth_manager.get_access_token()
            if access_token and kite_client.is_initialized():
                kite_client.set_access_token(access_token)
                # FIX: Run the blocking call in a separate thread to avoid blocking the event loop
                loop = asyncio.get_running_loop()
                profile_data = await loop.run_in_executor(
                    None, kite_client.get_profile
                )
                user_profile = UserProfile.from_kite_response(profile_data)
                # Cache it in auth manager
                self.auth_manager._user_profile = user_profile
                return user_profile
        except Exception as e:
            logger.error(f"Failed to fetch user profile: {e}")
        
        return None

    async def authenticate_user(self, username: str, plain_password: str) -> Optional[dict]:
        """
        DEPRECATED: Alpha Panda uses only Zerodha authentication.
        This method is kept for API compatibility but always returns None.
        """
        logger.warning("User authentication is not supported. Alpha Panda uses only Zerodha broker authentication.")
        return None

    async def create_user(self, username: str, plain_password: str) -> Optional[dict]:
        """
        DEPRECATED: Alpha Panda uses only Zerodha authentication.
        This method is kept for API compatibility but always raises an exception.
        """
        logger.error("User creation is not supported. Alpha Panda uses only Zerodha broker authentication.")
        raise Exception("User creation not supported. System uses Zerodha authentication only.")