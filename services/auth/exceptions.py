"""Authentication exceptions for Alpha Panda."""

class AuthenticationError(Exception):
    """Base authentication error."""
    pass

class InvalidCredentialsError(AuthenticationError):
    """Invalid credentials or token provided."""
    pass

class SessionExpiredError(AuthenticationError):
    """Session has expired."""
    pass

class SessionNotFoundError(AuthenticationError):
    """Session not found in the persistent store."""
    pass

class ZerodhaAuthError(AuthenticationError):
    """Zerodha API-specific authentication error."""
    pass

class TokenValidationError(AuthenticationError):
    """Token validation failed."""
    pass

class InteractiveAuthTimeoutError(AuthenticationError):
    """Interactive authentication timed out."""
    pass

class ConfigurationError(AuthenticationError):
    """Configuration error in authentication setup."""
    pass