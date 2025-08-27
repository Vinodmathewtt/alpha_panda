"""Main authentication manager following reference implementation pattern."""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    import select

    HAS_SELECT = True
except ImportError:
    HAS_SELECT = False

from core.auth.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    SessionExpiredError,
    ZerodhaAuthError,
)
from core.auth.models import (
    AuthProvider,
    AuthStatus,
    LoginMethod,
    SessionData,
    SessionInvalidationReason,
    UserProfile,
)
from core.auth.session_manager import SessionManager
from core.config.settings import Settings
from core.utils.exceptions import ConfigurationError
from core.utils.kite_client import kite_client
from core.database.connection import DatabaseManager

logger = logging.getLogger(__name__)


class InteractiveAuthTimeoutException(Exception):
    """Exception raised when interactive authentication times out."""

    pass


class AuthManager:
    """Main authentication manager with comprehensive session management."""

    def __init__(self, settings: Settings, db_manager: DatabaseManager):
        self.settings = settings
        self.db_manager = db_manager

        # Session management
        self.session_manager = SessionManager(settings, db_manager)

        # Authentication state
        self._status = AuthStatus.UNAUTHENTICATED
        self._is_shutting_down = False
        self._cleanup_needed = False

        # Current user profile
        self._user_profile: Optional[UserProfile] = None

        # Initialize kite client
        kite_client.initialize(settings)

        logger.info("AuthManager initialized")

    @property
    def status(self) -> AuthStatus:
        """Get current authentication status."""
        return self._status

    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        try:
            # In mock mode, always consider authenticated - skip all session checks
            if self.settings.mock_market_feed:
                return True

            # Real mode authentication check
            session = self.session_manager.get_current_session()
            if not session:
                return False

            if session.is_expired():
                logger.info("Session has expired")
                # Mark for cleanup instead of creating fire-and-forget task
                self._mark_session_for_cleanup()
                return False

            return True

        except Exception as e:
            logger.warning(f"Authentication check failed: {e}")
            return False

    async def initialize(self) -> bool:
        """Initialize authentication with stored session or interactive flow."""
        try:
            # Start session manager
            await self.session_manager.start()

            # Check if mock mode - completely skip authentication
            if self.settings.mock_market_feed:
                logger.info("🎭 Mock market feed enabled - completely skipping authentication")
                self._status = AuthStatus.AUTHENTICATED

                # Create minimal mock user profile for compatibility
                self._user_profile = UserProfile(
                    user_id="MOCK_USER",
                    user_name="Mock User",
                    user_shortname="Mock User",
                    email="mock@example.com",
                    user_type="individual",
                    broker="MOCK",
                    products=["CNC", "MIS", "NRML"],
                    order_types=["MARKET", "LIMIT", "SL", "SL-M"],
                    exchanges=["NSE", "BSE", "NFO"],
                )

                logger.info("✅ Mock authentication completed - system ready for mock trading")
                return True

            # Real authentication flow for mock_market_feed=false
            logger.info("Starting authentication initialization")

            # Try to load existing session (filter by mode)
            session = await self.session_manager.load_session(mock_mode=False)

            if session and not session.is_expired():
                logger.info(f"Found valid session for user: {session.user_id}")

                # Validate token if configured
                if await self._validate_session(session):
                    # Set the access token in kite_client for API calls
                    if kite_client.kite:
                        kite_client.set_access_token(session.access_token)

                    # Update internal state
                    self._status = AuthStatus.AUTHENTICATED

                    # Try to fetch fresh profile data from Zerodha API
                    try:
                        if kite_client.kite and not self.settings.mock_market_feed:
                            logger.debug("Fetching fresh user profile from Zerodha API")
                            profile_data = await asyncio.get_running_loop().run_in_executor(
                                None, kite_client.get_profile
                            )
                            
                            if isinstance(profile_data, dict):
                                # Create UserProfile from fresh API data
                                self._user_profile = UserProfile.from_kite_response(profile_data)
                                logger.debug(f"✅ Fresh profile fetched: {self._user_profile.user_shortname}")
                            else:
                                raise ValueError("Invalid profile data format")
                        else:
                            raise ValueError("Kite client not available or mock mode")
                            
                    except Exception as e:
                        logger.warning(f"Could not fetch fresh profile from API: {e}, using session data")
                        # Fallback to session data if API call fails
                        self._user_profile = UserProfile(
                            user_id=session.user_id,
                            user_name=session.user_name or "",
                            user_shortname=session.user_shortname or "",
                            email=session.email or "",
                            user_type="",
                            broker=session.broker or "",
                            products=[],
                            order_types=[],
                            exchanges=[],
                        )

                    logger.info(f"✅ Session restored for user: {self._user_profile.user_shortname or self._user_profile.user_name or session.user_id}")
                    return True
                else:
                    logger.warning("Session validation failed")
                    await self._invalidate_session()

            # No valid session - start interactive authentication
            logger.info("No valid session found, starting interactive authentication")
            return await self._interactive_authentication()

        except Exception as e:
            logger.error(f"Authentication initialization failed: {e}")
            self._status = AuthStatus.ERROR
            return False

    async def _validate_session(self, session: SessionData) -> bool:
        """Validate session by testing API access."""
        try:
            # Skip validation for mock sessions
            if session.login_method == LoginMethod.MOCK or self.settings.mock_market_feed:
                logger.debug("Skipping session validation for mock session")
                return True

            # Set access token temporarily for validation
            if kite_client.kite:
                kite_client.set_access_token(session.access_token)
            else:
                logger.warning("KiteConnect client not initialized")
                return True  # Assume valid if client not available

            # Test API call with timeout
            await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(None, kite_client.get_profile), timeout=5.0)

            logger.debug("Session validation successful")
            return True

        except asyncio.TimeoutError:
            logger.warning("Token validation timeout - assuming valid")
            return True  # Assume valid on timeout
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "network" in error_msg.lower():
                logger.warning(f"Network issue during validation - assuming valid: {error_msg}")
                return True
            else:
                logger.warning(f"Token validation failed: {error_msg}")
                return False

    async def _interactive_authentication(self) -> bool:
        """Handle interactive OAuth authentication flow."""
        try:
            self._status = AuthStatus.AUTHENTICATING

            print("\\n🔐 ===== ZERODHA AUTHENTICATION REQUIRED =====")
            print("📋 No valid access token found. Please authenticate with Zerodha.")
            print("🛑 SYSTEM WAITING FOR AUTHENTICATION - No other components will start until auth completes")
            print("")

            # Validate that we have API credentials before proceeding
            if not self._validate_api_credentials():
                print("❌ Zerodha API credentials not configured properly.")
                print("💡 Please check your .env file for TRADING__KITE_API_KEY and TRADING__KITE_API_SECRET")
                return False

            # Get login URL
            try:
                login_url = self.get_login_url()
                print("🌐 Please visit this URL to login:")
                print(f"   {login_url}")
                print("")
                print("📝 After login, you will be redirected to a URL with a 'request_token' parameter.")
                print("   Copy the entire request_token value and paste it below.")
                print("")
                print(f"⏰ You have 300 seconds to complete the authentication process.")
                print(f"   The system will shutdown gracefully if no input is received within 300 seconds.")
                print("🛑 Press Ctrl+C to cancel and shutdown gracefully.")
                print("")
            except Exception as e:
                print(f"❌ Failed to generate login URL: {e}")
                return False

            # Get request token with timeout
            request_token = await self._prompt_for_input("🔑 Enter request_token: ", 300)

            if self._is_shutting_down:
                print("\\n🛑 System shutdown requested, cancelling authentication...")
                return False

            if not request_token or not request_token.strip():
                raise ValueError("Request token is required for authentication")

            # Generate session
            session_data = await self._generate_session(request_token.strip())

            print("✅ Authentication successful! System will now continue...")
            print("🔓 Authentication completed - continuing with system initialization")
            print("")

            self._status = AuthStatus.AUTHENTICATED
            return True

        except InteractiveAuthTimeoutException:
            print(f"\\n⏰ Authentication timeout: No input received within 300 seconds.")
            print("🔄 The system will now shutdown gracefully.")
            print(f"💡 Please restart the application and complete authentication within 300 seconds.\\n")
            return False

        except KeyboardInterrupt:
            print("\\n🛑 Authentication cancelled by user")
            self._status = AuthStatus.UNAUTHENTICATED
            return False
        except Exception as e:
            logger.error(f"Interactive authentication failed: {e}")
            print(f"❌ Authentication failed: {e}")
            print("💡 Please check your internet connection and Zerodha API credentials")
            self._status = AuthStatus.ERROR
            return False

    async def _prompt_for_input(self, prompt: str, timeout_seconds: int) -> str:
        """Prompt for user input with timeout and shutdown handling (cross-platform)."""
        print(prompt, end="", flush=True)

        try:
            # Use asyncio.wait_for with a proper input coroutine
            if os.name == "nt":  # Windows
                # Windows-compatible input handling
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    self._get_input_sync(), timeout=timeout_seconds
                )
            else:
                # Unix-like systems with select support
                result = await asyncio.wait_for(self._get_input_async(), timeout=timeout_seconds)

            if self._is_shutting_down:
                raise InteractiveAuthTimeoutException("Shutdown requested during input")

            return result.strip()

        except asyncio.TimeoutError:
            raise InteractiveAuthTimeoutException(f"No input received within {timeout_seconds} seconds")

    async def _get_input_sync(self) -> str:
        """Asynchronous input for Windows compatibility."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, input)

    async def _get_input_async(self) -> str:
        """Asynchronous input for Unix-like systems."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        line = await reader.readline()
        return line.decode().strip()

    async def _generate_session(self, request_token: str) -> SessionData:
        """Generate session from request token."""
        try:
            logger.info("Generating session with request token...")

            # Validate request token format
            if not request_token or len(request_token) < 10:
                raise ValueError("Invalid request token format")

            # Generate session using KiteConnect
            response = await asyncio.get_running_loop().run_in_executor(None, kite_client.generate_session, request_token)

            if not response or "access_token" not in response:
                raise ZerodhaAuthError("Invalid response from Zerodha API")

            # Create session data
            session_data = await self.session_manager.create_session_from_kite_response(response, LoginMethod.OAUTH)

            # Set access token in kite client
            if kite_client.kite:
                kite_client.set_access_token(session_data.access_token)

            # Save session to database
            success = await self.session_manager.save_session(session_data)
            if not success:
                raise ZerodhaAuthError("Failed to save session to database")

            logger.info(f"Session generated successfully for user: {session_data.user_id}")
            return session_data

        except Exception as e:
            logger.error(f"Session generation failed: {e}")
            if "Invalid request token" in str(e) or "400" in str(e):
                raise ZerodhaAuthError(
                    f"Invalid request token. Please try again with a fresh token from the login URL."
                )
            elif "timeout" in str(e).lower():
                raise ZerodhaAuthError(f"Network timeout during authentication. Please check your internet connection.")
            else:
                raise ZerodhaAuthError(f"Failed to generate session: {e}")

    def get_login_url(self) -> str:
        """Get Zerodha login URL."""
        try:
            return kite_client.get_login_url()
        except Exception as e:
            logger.error(f"Failed to get login URL: {e}")
            raise ZerodhaAuthError(f"Failed to generate login URL: {e}")

    def _validate_api_credentials(self) -> bool:
        """Validate that API credentials are properly configured."""
        try:
            # Check if kite client is initialized
            if not kite_client.is_initialized():
                logger.error("KiteConnect client not initialized")
                return False

            return True
        except Exception as e:
            logger.error(f"API credentials validation failed: {e}")
            return False

    async def get_profile(self) -> Optional[UserProfile]:
        """Get user profile."""
        if not self.is_authenticated():
            raise AuthenticationError("Not authenticated")

        try:
            # If profile not cached or in mock mode, try to fetch it
            if not self._user_profile and not self.settings.mock_market_feed:
                if kite_client.kite:
                    logger.debug("Fetching user profile from Zerodha API")
                    profile_data = await asyncio.get_running_loop().run_in_executor(None, kite_client.get_profile)
                    if isinstance(profile_data, dict):
                        self._user_profile = UserProfile.from_kite_response(profile_data)
                        logger.debug(f"✅ Profile cached: {self._user_profile.user_shortname}")
                    else:
                        logger.warning("Invalid profile data format received")

            # If still no profile, create one from session data as fallback
            if not self._user_profile:
                session = self.session_manager.get_current_session()
                if session:
                    self._user_profile = UserProfile(
                        user_id=session.user_id,
                        user_name=session.user_name or "",
                        user_shortname=session.user_shortname or "",
                        email=session.email or "",
                        user_type="",
                        broker=session.broker or "zerodha",
                        products=[],
                        order_types=[],
                        exchanges=[],
                    )
                    logger.debug(f"✅ Profile created from session: {self._user_profile.user_shortname}")

            return self._user_profile

        except Exception as e:
            logger.error(f"Failed to get profile: {e}")
            raise AuthenticationError(f"Failed to get profile: {e}")

    async def invalidate_session(self) -> bool:
        """Manually invalidate current session."""
        return await self._invalidate_session()

    async def _invalidate_session(self) -> bool:
        """Internal method to invalidate session."""
        try:
            await self.session_manager.invalidate_session()
            self._status = AuthStatus.UNAUTHENTICATED
            self._user_profile = None
            return True

        except Exception as e:
            logger.error(f"Failed to invalidate session: {e}")
            return False

    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information."""
        session = self.session_manager.get_current_session()

        if not session:
            return {
                "authenticated": False,
                "valid": False,
                "user_id": None,
                "expires_at": None,
                "time_to_expiry": 0,
                "status": self._status.value,
            }

        return {
            "authenticated": True,
            "valid": not session.is_expired(),
            "user_id": session.user_id,
            "user_shortname": session.user_shortname,
            "expires_at": session.expires_at.isoformat(),
            "time_to_expiry": session.time_to_expiry(),
            "login_method": session.login_method.value,
            "login_timestamp": session.login_timestamp.isoformat(),
            "last_activity": session.last_activity_timestamp.isoformat(),
            "status": self._status.value,
        }

    def set_shutting_down(self):
        """Set the shutting down flag."""
        self._is_shutting_down = True
        logger.debug("AuthManager marked as shutting down")

    async def ensure_authenticated(self) -> bool:
        """Ensure authentication is complete."""
        # Check if authentication should be skipped
        if self.settings.mock_market_feed:
            logger.debug("🎭 Mock market feed mode - authentication not required")
            if self._status != AuthStatus.AUTHENTICATED:
                # Initialize mock authentication if not already done
                return await self.initialize()
            return True


        # Real mode authentication
        if self.is_authenticated():
            return True

        return await self.initialize()

    def extend_session(self, hours: Optional[int] = None) -> bool:
        """Extend the current session expiry time."""
        # This would need to be implemented in session manager
        logger.warning("Session extension not implemented for Zerodha tokens")
        return False

    async def set_access_token(self, token: str) -> None:
        """Set access token directly if already available."""
        # Set token in kite client first
        if kite_client.kite:
            kite_client.set_access_token(token)

        # Try to fetch user profile from Zerodha API
        profile_data = None
        user_id = "DIRECT_TOKEN_USER"
        user_name = ""
        user_shortname = ""
        email = ""
        broker = "zerodha"
        
        try:
            if kite_client.kite and not self.settings.mock_market_feed:
                logger.debug("Fetching user profile for direct token")
                profile_data = await asyncio.get_running_loop().run_in_executor(
                    None, kite_client.get_profile
                )
                
                if isinstance(profile_data, dict):
                    user_id = profile_data.get("user_id", "DIRECT_TOKEN_USER")
                    user_name = profile_data.get("user_name", "")
                    user_shortname = profile_data.get("user_shortname", "")
                    email = profile_data.get("email", "")
                    broker = "zerodha"
                    
                    # Create UserProfile from API data
                    self._user_profile = UserProfile.from_kite_response(profile_data)
                    logger.debug(f"✅ Profile fetched for direct token: {user_shortname}")
                    
        except Exception as e:
            logger.warning(f"Could not fetch profile for direct token: {e}, using defaults")

        # Create session data with fetched or default values
        now = datetime.now(timezone.utc)
        session_data = SessionData(
            user_id=user_id,
            user_name=user_name,
            user_shortname=user_shortname,
            email=email,
            broker=broker,
            access_token=token,
            expires_at=now + timedelta(hours=24),
            login_timestamp=now,
            last_activity_timestamp=now,
            login_method=LoginMethod.TOKEN,
            created_at=now,
            updated_at=now,
            last_validated=now,
        )

        await self.session_manager.save_session(session_data)
        self._status = AuthStatus.AUTHENTICATED
        logger.info(f"Access token set directly for user: {user_shortname or user_name or user_id}")

    def get_access_token(self) -> Optional[str]:
        """Get current access token."""
        session = self.session_manager.get_current_session()
        return session.access_token if session else None

    def is_session_valid(self) -> bool:
        """Check if session is valid (not expired)."""
        session = self.session_manager.get_current_session()
        return session is not None and not session.is_expired()

    def get_kite_connect(self):
        """Get KiteConnect instance."""
        if not self.is_authenticated():
            raise AuthenticationError("Not authenticated. Please generate session first.")
        return kite_client.get_kite_instance()
    
    def get_kite_client(self):
        """Get KiteConnect client instance - alias for get_kite_connect()."""
        return self.get_kite_connect()

    async def authenticate_zerodha(self, api_key: str, api_secret: str, request_token: str) -> Dict[str, Any]:
        """Authenticate with Zerodha OAuth flow.
        
        Args:
            api_key: Zerodha API key
            api_secret: Zerodha API secret
            request_token: Request token from OAuth flow
            
        Returns:
            Dict containing authentication result and user data
        """
        try:
            # Initialize kite client with credentials
            kite_client.initialize_with_credentials(api_key, api_secret)
            kc = kite_client.get_kite_instance()
            
            # Generate access token
            auth_data = kc.generate_session(request_token, api_secret)
            
            # Get user profile
            profile = kc.profile()
            
            # Create session data
            session_data = SessionData(
                user_id=profile.get("user_id"),
                user_name=profile.get("user_name"),
                user_shortname=profile.get("user_shortname"),
                broker="zerodha",
                email=profile.get("email"),
                access_token=auth_data.get("access_token"),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                login_timestamp=datetime.now(timezone.utc),
                last_activity_timestamp=datetime.now(timezone.utc),
                login_method=LoginMethod.OAUTH,
                session_id=f"zerodha_{auth_data.get('access_token')[:10]}",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                last_validated=datetime.now(timezone.utc)
            )
            
            # Save session
            await self.session_manager.save_session(session_data)
            self._status = AuthStatus.AUTHENTICATED
            
            return {
                "success": True,
                "user_data": profile,
                "access_token": auth_data.get("access_token"),
                "message": "Authentication successful"
            }
            
        except Exception as e:
            logger.error(f"Zerodha authentication failed: {e}")
            raise AuthenticationError(f"Authentication failed: {e}")

    async def create_jwt_token(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create JWT token from user data.
        
        Args:
            user_data: User data dictionary
            
        Returns:
            Dict containing JWT token and expiration
        """
        try:
            from core.auth.jwt_token_manager import JWTTokenManager
            
            jwt_manager = JWTTokenManager(self.settings)
            
            # Create JWT payload
            payload = {
                "user_id": user_data.get("user_id"),
                "user_name": user_data.get("user_name"),
                "broker": "zerodha",
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=24)
            }
            
            # Generate JWT token
            token = jwt_manager.create_token(payload)
            
            return {
                "access_token": token,
                "token_type": "bearer",
                "expires_in": 86400,  # 24 hours
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            }
            
        except Exception as e:
            logger.error(f"JWT token creation failed: {e}")
            raise AuthenticationError(f"Token creation failed: {e}")

    async def refresh_jwt_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh JWT token.
        
        Args:
            refresh_token: Refresh token string
            
        Returns:
            Dict containing new JWT token
        """
        try:
            from core.auth.jwt_token_manager import JWTTokenManager
            
            jwt_manager = JWTTokenManager(self.settings)
            
            # Validate refresh token (implement as needed)
            # For now, get current session data
            session = self.session_manager.get_current_session()
            if not session:
                raise AuthenticationError("No active session for token refresh")
            
            # Create new token payload
            payload = {
                "user_id": session.user_id,
                "user_name": session.user_name,
                "broker": session.broker,
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=24)
            }
            
            # Generate new JWT token
            new_token = jwt_manager.create_token(payload)
            
            # Update session with new token if needed
            session.updated_at = datetime.now(timezone.utc)
            await self.session_manager.save_session(session)
            
            return {
                "access_token": new_token,
                "token_type": "bearer",
                "expires_in": 86400,  # 24 hours
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            }
            
        except Exception as e:
            logger.error(f"JWT token refresh failed: {e}")
            raise AuthenticationError(f"Token refresh failed: {e}")

    def _mark_session_for_cleanup(self) -> None:
        """Mark session for cleanup without creating fire-and-forget tasks."""
        self._cleanup_needed = True
        logger.debug("Session marked for cleanup")

    async def perform_cleanup_if_needed(self) -> None:
        """Perform cleanup of expired sessions if needed."""
        if self._cleanup_needed and not self._is_shutting_down:
            try:
                await self._invalidate_session()
                self._cleanup_needed = False
                logger.debug("Session cleanup completed")
            except Exception as e:
                logger.error(f"Session cleanup failed: {e}")

    async def stop(self) -> None:
        """Stop authentication manager."""
        self._is_shutting_down = True
        # Perform any pending cleanup before shutdown
        await self.perform_cleanup_if_needed()
        await self.session_manager.stop()
        logger.info("Authentication manager stopped")
