# alphaP/services/auth/auth_manager.py

"""Manages broker authentication and session state."""

import asyncio
import logging
import os
import sys
from typing import Optional
from datetime import datetime, timedelta, timezone

try:
    import select
    HAS_SELECT = True
except ImportError:
    HAS_SELECT = False

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from .exceptions import AuthenticationError, InvalidCredentialsError, ZerodhaAuthError
from .kite_client import kite_client
from .models import AuthStatus, LoginMethod, SessionData, UserProfile
from .session_manager import SessionManager

logger = logging.getLogger(__name__)

class InteractiveAuthTimeoutException(Exception):
    """Exception raised when interactive authentication times out."""
    pass

class AuthManager:
    """Manages broker authentication via externally provided access tokens."""

    def __init__(self, settings: Settings, db_manager: DatabaseManager, shutdown_event: Optional[asyncio.Event] = None):
        self.settings = settings
        self.session_manager = SessionManager(settings, db_manager)
        self._status = AuthStatus.UNAUTHENTICATED
        self._user_profile: Optional[UserProfile] = None
        self._is_shutting_down = False
        self._shutdown_event = shutdown_event  # Connect to global shutdown event
        kite_client.initialize(settings)
        logger.info("AuthManager initialized for token-based flow.")

    @property
    def status(self) -> AuthStatus:
        return self._status

    async def initialize(self) -> bool:
        """
        MANDATORY Zerodha authentication - system will not start without valid Zerodha credentials.
        """
        logger.info("🔐 Starting MANDATORY Zerodha authentication...")
        
        # Validate API credentials are provided
        if not self.settings.zerodha.api_key or not self.settings.zerodha.api_secret:
            logger.critical("❌ CRITICAL: Zerodha API credentials are missing")
            logger.critical("💡 Alpha Panda requires valid Zerodha API key and secret")
            logger.critical("🔧 Please set ZERODHA__API_KEY and ZERODHA__API_SECRET in your .env file")
            self._status = AuthStatus.ERROR
            return False

        # Check if KiteConnect client is properly initialized
        if not kite_client.is_initialized():
            logger.critical("❌ CRITICAL: KiteConnect client failed to initialize")
            logger.critical("💡 This indicates a problem with Zerodha API credentials")
            logger.critical("🔧 Please verify your ZERODHA__API_KEY and ZERODHA__API_SECRET")
            self._status = AuthStatus.ERROR
            return False

        # Try to load existing valid session
        session = await self.session_manager.load_session()
        if session and not session.is_expired():
            logger.info(f"Found valid session for user: {session.user_id}")
            
            # Set access token and validate it with Zerodha API
            kite_client.set_access_token(session.access_token)
            
            # MANDATORY: Validate session by fetching fresh profile data
            try:
                logger.debug("Validating session with Zerodha API...")
                profile_data = await asyncio.get_running_loop().run_in_executor(
                    None, kite_client.get_profile
                )
                
                if not isinstance(profile_data, dict):
                    raise ValueError("Invalid profile data format from Zerodha API")
                
                # Create UserProfile from fresh API data
                self._user_profile = UserProfile.from_kite_response(profile_data)
                self._status = AuthStatus.AUTHENTICATED
                
                logger.info(f"✅ Fresh profile validated: {self._user_profile.user_shortname}")
                logger.info(f"✅ Session restored for user: {self._user_profile.user_shortname or self._user_profile.user_name}")
                return True
                
            except Exception as e:
                logger.error(f"❌ Session validation failed with Zerodha API: {e}")
                logger.error("💡 Existing session token may be expired or invalid")
                
                # Invalidate the bad session
                await self.session_manager.invalidate_session()

        # No valid session - start interactive authentication
        logger.info("No valid session found, starting interactive authentication")
        auth_success = await self._interactive_authentication()
        
        if not auth_success:
            logger.critical("❌ CRITICAL: Zerodha authentication failed")
            logger.critical("💡 Alpha Panda cannot operate without valid Zerodha authentication")
            logger.critical("🔄 Please restart the application and complete authentication")
            self._status = AuthStatus.ERROR
            
        return auth_success

    async def login_with_token(self, access_token: str) -> SessionData:
        """
        Validates a Zerodha access token, fetches user profile, and creates a persistent session.
        """
        if not kite_client.is_initialized():
            raise AuthenticationError("Cannot login with token: Kite client not initialized.")

        try:
            # 1. Set the token and validate it by fetching the user profile
            kite_client.set_access_token(access_token)
            profile_data = kite_client.get_profile()
            self._user_profile = UserProfile.from_kite_response(profile_data)
            logger.info(f"Access token successfully validated for user: {self._user_profile.user_id}")

            # 2. Create a session data object
            session_data = SessionData(
                user_id=self._user_profile.user_id,
                access_token=access_token,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24), # Match Zerodha token validity
                login_timestamp=datetime.now(timezone.utc),
                last_activity_timestamp=datetime.now(timezone.utc),
                login_method=LoginMethod.EXTERNAL_TOKEN,
                user_name=self._user_profile.user_name,
                user_shortname=self._user_profile.user_shortname,
                broker=self._user_profile.broker,
                email=self._user_profile.email,
            )

            # 3. Save the session to the database
            await self.session_manager.save_session(session_data)
            self._status = AuthStatus.AUTHENTICATED
            logger.info(f"New session created and persisted for user: {session_data.user_id}")

            return session_data

        except Exception as e:
            self._status = AuthStatus.ERROR
            logger.error(f"Failed to login with token: {e}")
            raise ZerodhaAuthError(f"Token validation or session creation failed: {e}") from e

    async def logout(self) -> bool:
        """Invalidates the current session."""
        logged_out = await self.session_manager.invalidate_session()
        if logged_out:
            self._status = AuthStatus.UNAUTHENTICATED
            self._user_profile = None
        return logged_out

    async def get_access_token(self) -> Optional[str]:
        """Returns the current access token if available."""
        if self._status == AuthStatus.AUTHENTICATED:
            session = await self.session_manager.load_session()
            if session and not session.is_expired():
                return session.access_token
        return None

    async def _interactive_authentication(self) -> bool:
        """Handle interactive OAuth authentication flow."""
        try:
            self._status = AuthStatus.AUTHENTICATING

            print("\n🔐 ===== ZERODHA AUTHENTICATION REQUIRED =====")
            print("📋 No valid access token found. Please authenticate with Zerodha.")
            print("🛑 SYSTEM WAITING FOR AUTHENTICATION - No other components will start until auth completes")
            print("")

            # Validate that we have API credentials before proceeding
            if not self._validate_api_credentials():
                print("❌ Zerodha API credentials not configured properly.")
                print("💡 Please check your .env file for ZERODHA__API_KEY and ZERODHA__API_SECRET")
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
                print("\n🛑 System shutdown requested, cancelling authentication...")
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
            print(f"\n⏰ CRITICAL: Authentication timeout - No input received within 300 seconds.")
            print("🔄 Alpha Panda will now shutdown gracefully.")
            print(f"💡 Please restart the application and complete authentication within 300 seconds.")
            print("🚫 System cannot operate without valid Zerodha authentication.\n")
            self._status = AuthStatus.ERROR
            return False

        except KeyboardInterrupt:
            print("\n🛑 CRITICAL: Authentication cancelled by user")
            print("🚫 Alpha Panda requires Zerodha authentication to operate")
            print("🔄 Please restart the application to try authentication again")
            self._status = AuthStatus.ERROR
            self.set_shutting_down()
            return False
        except Exception as e:
            logger.error(f"Interactive authentication failed: {e}")
            print(f"\n❌ CRITICAL: Zerodha authentication failed - {e}")
            print("💡 Common causes:")
            print("   • Invalid or expired request token")
            print("   • Internet connectivity issues") 
            print("   • Zerodha API server issues")
            print("   • Incorrect API credentials")
            print("🔧 Troubleshooting:")
            print("   • Verify your .env file has correct ZERODHA__API_KEY and ZERODHA__API_SECRET")
            print("   • Check your internet connection")
            print("   • Try generating a fresh request token from the login URL")
            print("🚫 Alpha Panda cannot start without valid Zerodha authentication")
            self._status = AuthStatus.ERROR
            return False

    async def _prompt_for_input(self, prompt: str, timeout_seconds: int) -> str:
        """Prompt for user input with timeout and shutdown handling (cross-platform)."""
        print(prompt, end="", flush=True)

        try:
            # Create tasks for input and shutdown monitoring
            if os.name == "nt":  # Windows
                # Windows-compatible input handling
                input_task = asyncio.create_task(self._get_input_sync())
            else:
                # Unix-like systems with select support
                input_task = asyncio.create_task(self._get_input_async())
            
            # Create shutdown monitoring task if shutdown_event is available
            shutdown_task = None
            if self._shutdown_event:
                shutdown_task = asyncio.create_task(self._shutdown_event.wait())
            
            try:
                if shutdown_task:
                    # Wait for either input or shutdown signal
                    done, pending = await asyncio.wait(
                        [input_task, shutdown_task],
                        timeout=timeout_seconds,
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    
                    if shutdown_task in done:
                        self._is_shutting_down = True
                        raise InteractiveAuthTimeoutException("Shutdown requested during input")
                    
                    if input_task in done:
                        result = input_task.result()
                    else:
                        raise InteractiveAuthTimeoutException(f"No input received within {timeout_seconds} seconds")
                else:
                    # Fallback to simple timeout if no shutdown event
                    result = await asyncio.wait_for(input_task, timeout=timeout_seconds)
                
                if self._is_shutting_down or (self._shutdown_event and self._shutdown_event.is_set()):
                    raise InteractiveAuthTimeoutException("Shutdown requested during input")

                return result.strip()
                
            except asyncio.TimeoutError:
                input_task.cancel()
                try:
                    await input_task
                except asyncio.CancelledError:
                    pass
                raise InteractiveAuthTimeoutException(f"No input received within {timeout_seconds} seconds")

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
            response = await asyncio.get_running_loop().run_in_executor(
                None, kite_client.generate_session, request_token, self.settings.zerodha.api_secret
            )

            if not response or "access_token" not in response:
                raise ZerodhaAuthError("Invalid response from Zerodha API")

            # Get user profile
            kite_client.set_access_token(response["access_token"])
            profile_data = await asyncio.get_running_loop().run_in_executor(None, kite_client.get_profile)
            self._user_profile = UserProfile.from_kite_response(profile_data)

            # Create session data
            session_data = SessionData(
                user_id=self._user_profile.user_id,
                access_token=response["access_token"],
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24), # Match Zerodha token validity
                login_timestamp=datetime.now(timezone.utc),
                last_activity_timestamp=datetime.now(timezone.utc),
                login_method=LoginMethod.OAUTH,
                user_name=self._user_profile.user_name,
                user_shortname=self._user_profile.user_shortname,
                broker=self._user_profile.broker,
                email=self._user_profile.email,
            )

            # Save the session to the database
            await self.session_manager.save_session(session_data)
            logger.info(f"New session created and persisted for user: {session_data.user_id}")

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

            # Check if API key and secret are configured
            if not self.settings.zerodha.api_key or not self.settings.zerodha.api_secret:
                logger.error("Zerodha API key or secret not configured")
                return False

            return True
        except Exception as e:
            logger.error(f"API credentials validation failed: {e}")
            return False

    def set_shutting_down(self):
        """Set the shutting down flag."""
        self._is_shutting_down = True
        # If we have a shutdown event, set it to signal other parts of the system
        if self._shutdown_event and not self._shutdown_event.is_set():
            self._shutdown_event.set()
        logger.debug("AuthManager marked as shutting down")
    
    async def stop(self) -> None:
        """Stop authentication manager and cleanup resources."""
        self._is_shutting_down = True
        await self.session_manager.stop()
        logger.info("Authentication manager stopped")
