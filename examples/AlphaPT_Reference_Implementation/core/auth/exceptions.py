"""Authentication-specific exceptions."""

from core.utils.exceptions import AlphaPTException


class AuthenticationError(AlphaPTException):
    """Authentication-related errors."""

    pass


class AuthorizationError(AlphaPTException):
    """Authorization-related errors."""

    pass


class InvalidTokenError(AuthenticationError):
    """Invalid or expired token error."""

    pass


class InvalidCredentialsError(AuthenticationError):
    """Invalid credentials error."""

    pass


class SessionExpiredError(AuthenticationError):
    """Session expired error."""

    pass


class SessionNotFoundError(AuthenticationError):
    """Session not found error."""

    pass


class ProviderError(AuthenticationError):
    """Authentication provider error."""

    pass


class ZerodhaAuthError(ProviderError):
    """Zerodha-specific authentication error."""

    pass
