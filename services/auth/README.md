# Authentication Service

## Overview

The Authentication Service manages user authentication, session handling, and broker authentication for Alpha Panda. It provides unified authentication across different providers (Zerodha KiteConnect, user authentication) and maintains secure session state.

## Architecture

The service follows a layered architecture with clear separation of concerns:
- **Service Layer**: High-level authentication operations and service lifecycle
- **Auth Manager**: Core authentication logic and provider coordination
- **Session Manager**: Session state management and persistence
- **Kite Client**: Zerodha KiteConnect API integration
- **Security**: Token validation and security utilities

## Components

### `service.py`
Main authentication service with lifecycle management:

- **AuthService**: Primary service class with start/stop lifecycle
- **Provider Coordination**: Manages multiple authentication providers
- **Service Integration**: Integration with other Alpha Panda services
- **Health Monitoring**: Authentication service health checks

### `auth_manager.py`
Core authentication management:

- **AuthManager**: Central authentication coordinator
- **Provider Management**: Multi-provider authentication support
- **Authentication Flow**: Login, logout, and session validation
- **Status Tracking**: Real-time authentication status monitoring

### `session_manager.py`
Session state management and persistence:

- **SessionManager**: Session lifecycle management
- **State Persistence**: Database-backed session storage
- **Session Validation**: Session expiry and validation
- **Multi-User Support**: Support for multiple concurrent sessions

### `kite_client.py`
Zerodha KiteConnect integration:

- **KiteClient**: Zerodha API authentication wrapper
- **Token Management**: Access token and session token handling
- **API Integration**: Zerodha login flow integration
- **Error Handling**: Zerodha-specific error handling and recovery

### `models.py`
Pydantic models for authentication data:

- **LoginRequest/Response**: Login flow data models
- **AuthProvider**: Authentication provider enumeration
- **AuthStatus**: Authentication status tracking
- **UserProfile**: User profile and session data

### `security.py`
Security utilities and token management:

- **Token Validation**: JWT and session token validation
- **Security Utils**: Password hashing and security functions
- **Session Security**: Session security and validation

### `exceptions.py`
Authentication-specific exception handling:

- **AuthException**: Base authentication exception
- **LoginError**: Login process failures
- **SessionError**: Session management errors
- **ProviderError**: Provider-specific errors

## Key Features

- **Multi-Provider Support**: Zerodha KiteConnect and user authentication
- **Session Management**: Secure session state with database persistence
- **Token Security**: JWT and session token validation
- **Health Monitoring**: Authentication status monitoring and alerts
- **Graceful Degradation**: Fallback authentication mechanisms
- **Broker Integration**: Seamless integration with trading broker APIs
- **Concurrent Sessions**: Support for multiple user sessions

## Usage

### Service Initialization
```python
from services.auth.service import AuthService
from core.config.settings import get_settings
from core.database.connection import DatabaseManager

# Initialize authentication service
settings = get_settings()
db_manager = DatabaseManager(settings.database.postgres_url)
auth_service = AuthService(settings, db_manager)

# Start service
await auth_service.start()
```

### Authentication Operations
```python
# User login
login_request = LoginRequest(
    provider=AuthProvider.ZERODHA,
    credentials={"api_key": "xxx", "api_secret": "yyy"}
)

login_response = await auth_service.login(login_request)
if login_response.success:
    session_token = login_response.session_token
    print(f"Login successful: {session_token}")

# Session validation
is_valid = await auth_service.validate_session(session_token)
if is_valid:
    user_profile = await auth_service.get_user_profile(session_token)
```

### Zerodha Authentication Flow
```python
from services.auth.kite_client import KiteClient

# Initialize Zerodha client
kite_client = KiteClient(api_key, api_secret)

# Step 1: Get login URL
login_url = kite_client.get_login_url()
print(f"Visit: {login_url}")

# Step 2: Complete authentication with request token
request_token = "received_from_callback"
session_data = await kite_client.generate_session(request_token)

# Step 3: Use access token for API calls
kite_client.set_access_token(session_data.access_token)
```

## Authentication Providers

### Zerodha KiteConnect
- **Provider ID**: `AuthProvider.ZERODHA`
- **Flow**: OAuth-style flow with request token and access token
- **Session**: Long-lived access token with daily refresh
- **API Integration**: Full Zerodha API access after authentication

### User Authentication (Future)
- **Provider ID**: `AuthProvider.USER`
- **Flow**: Username/password authentication
- **Session**: JWT-based session management
- **Integration**: Internal user management system

## Session Management

### Session Lifecycle
```python
# Create session
session_id = await session_manager.create_session(user_id, auth_data)

# Update session
await session_manager.update_session(session_id, updated_data)

# Validate session
is_active = await session_manager.is_session_active(session_id)

# End session
await session_manager.end_session(session_id)
```

### Session Data Structure
```python
{
    "session_id": "sess_123_abc",
    "user_id": "user_123",
    "auth_provider": "zerodha",
    "created_at": "2024-08-30T12:00:00Z",
    "expires_at": "2024-08-31T12:00:00Z",
    "auth_data": {
        "access_token": "xxx",
        "api_key": "yyy",
        "user_profile": {...}
    },
    "status": "active"
}
```

## Security Features

### Token Security
- **JWT Tokens**: Secure JSON Web Tokens for internal session management
- **Access Token Encryption**: Secure storage of broker access tokens
- **Token Expiry**: Automatic token expiration and cleanup
- **Refresh Logic**: Automatic token refresh where supported

### Session Security
- **Secure Storage**: Database-backed session storage with encryption
- **Session Expiry**: Configurable session timeout and cleanup
- **Concurrent Sessions**: Support for multiple sessions per user
- **Security Validation**: Session tampering detection and validation

## Configuration

Authentication configuration through settings:

```python
class AuthSettings(BaseModel):
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    enable_user_auth: bool = False
    primary_auth_provider: str = "zerodha"

class ZerodhaSettings(BaseModel):
    enabled: bool = True
    api_key: str = ""
    api_secret: str = ""
    redirect_url: str = "http://localhost:8000/auth/callback"
```

## Error Handling

### Authentication Errors
- **LoginError**: Failed login attempts with retry logic
- **SessionError**: Session validation and management errors
- **ProviderError**: Provider-specific authentication failures
- **TokenError**: Token validation and expiry errors

### Error Recovery
```python
try:
    await auth_service.login(login_request)
except LoginError as e:
    # Handle login failure
    if e.retryable:
        await asyncio.sleep(e.retry_delay)
        # Retry login
except SessionError as e:
    # Handle session management error
    await auth_service.cleanup_session(session_id)
```

## Health Monitoring

### Authentication Health Checks
```python
# Service health check
health = await auth_service.health_check()

# Sample health response
{
    "status": "healthy",
    "active_sessions": 5,
    "auth_providers": {
        "zerodha": "connected",
        "user": "disabled"
    },
    "last_login": "2024-08-30T12:00:00Z",
    "uptime": 3600
}
```

### Monitoring Metrics
- **Active Sessions**: Number of active user sessions
- **Login Success Rate**: Authentication success metrics
- **Provider Health**: Individual provider connectivity status
- **Token Expiry**: Upcoming token expiration alerts

## Best Practices

1. **Secure Token Storage**: Store sensitive tokens securely with encryption
2. **Session Validation**: Validate sessions on every request
3. **Provider Abstraction**: Use provider abstraction for multi-broker support
4. **Error Handling**: Implement proper error handling and recovery
5. **Monitoring**: Monitor authentication health and performance
6. **Security Updates**: Regular security updates and token rotation

## Dependencies

- **core.config**: Configuration management and settings
- **core.database**: Session persistence and user data storage
- **core.logging**: Authentication event logging and monitoring
- **pydantic**: Data validation and model management
- **asyncio**: Async authentication operations