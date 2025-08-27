"""Enhanced authentication service with interactive flows and Zerodha integration."""

from .service import AuthService
from .auth_manager import AuthManager
from .session_manager import SessionManager
from .kite_client import kite_client
from .models import (
    AuthProvider,
    AuthStatus,
    LoginMethod,
    SessionData,
    UserProfile,
    LoginRequest,
    LoginResponse,
    TradingSession,
)
from .exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    SessionExpiredError,
    SessionNotFoundError,
    ZerodhaAuthError,
    TokenValidationError,
    InteractiveAuthTimeoutError,
    ConfigurationError,
)

__all__ = [
    "AuthService",
    "AuthManager", 
    "SessionManager",
    "kite_client",
    "AuthProvider",
    "AuthStatus",
    "LoginMethod",
    "SessionData",
    "UserProfile",
    "LoginRequest",
    "LoginResponse",
    "TradingSession",
    "AuthenticationError",
    "InvalidCredentialsError",
    "SessionExpiredError",
    "SessionNotFoundError",
    "ZerodhaAuthError",
    "TokenValidationError",
    "InteractiveAuthTimeoutError",
    "ConfigurationError",
]