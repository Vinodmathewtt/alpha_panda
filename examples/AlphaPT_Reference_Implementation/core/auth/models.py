"""Authentication data models following reference implementation."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import jwt
from pydantic import BaseModel, Field


class AuthProvider(str, Enum):
    """Authentication provider types."""

    ZERODHA = "zerodha"
    LOCAL = "local"
    MOCK = "mock"


class UserRole(str, Enum):
    """User role types."""

    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"


class SessionStatus(str, Enum):
    """Session status types."""

    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class AuthStatus(Enum):
    """Authentication status enumeration."""

    UNAUTHENTICATED = "unauthenticated"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    INVALID = "invalid"
    ERROR = "error"


class LoginMethod(Enum):
    """Login method enumeration."""

    OAUTH = "oauth"
    TOKEN = "token"
    STORED = "stored"
    MOCK = "mock"


class SessionInvalidationReason(Enum):
    """Session invalidation reason enumeration."""

    TOKEN_EXPIRED = "token_expired"
    VALIDATION_FAILED = "validation_failed"
    USER_LOGOUT = "user_logout"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SECURITY_VIOLATION = "security_violation"
    SESSION_EXPIRY = "session_expiry"
    MANUAL_INVALIDATION = "manual_invalidation"


@dataclass
class User:
    """User model."""

    user_id: str
    username: str
    provider: AuthProvider
    roles: List[UserRole] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True

    def has_role(self, role: UserRole) -> bool:
        """Check if user has specific role."""
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission."""
        # Define role-based permissions
        permissions = {
            UserRole.ADMIN: ["*"],  # All permissions
            UserRole.TRADER: [
                "trading.place_order",
                "trading.cancel_order",
                "trading.view_positions",
                "market_data.view",
                "strategies.view",
                "strategies.start",
                "strategies.stop",
            ],
            UserRole.VIEWER: [
                "trading.view_positions",
                "market_data.view",
                "strategies.view",
            ],
        }

        for role in self.roles:
            role_permissions = permissions.get(role, [])
            if "*" in role_permissions or permission in role_permissions:
                return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "provider": self.provider.value,
            "roles": [r.value for r in self.roles],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
        }


@dataclass
class AuthToken:
    """Authentication token model."""

    token_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    token_type: str = "access"  # access, refresh
    token_value: str = ""
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_revoked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if token is expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def is_valid(self) -> bool:
        """Check if token is valid."""
        return not self.is_revoked and not self.is_expired()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "token_id": self.token_id,
            "user_id": self.user_id,
            "token_type": self.token_type,
            "token_value": self.token_value,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
            "is_revoked": self.is_revoked,
            "metadata": self.metadata,
        }


@dataclass
class SessionData:
    """Session data structure matching the reference implementation."""

    user_id: str
    access_token: str
    expires_at: datetime
    login_timestamp: datetime
    last_activity_timestamp: datetime
    login_method: LoginMethod

    # Optional user details
    user_name: Optional[str] = None
    user_shortname: Optional[str] = None
    broker: Optional[str] = None
    email: Optional[str] = None

    # Session metadata
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4()))

    # Audit fields
    created_at: Optional[datetime] = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = field(default_factory=lambda: datetime.now(timezone.utc))
    last_validated: Optional[datetime] = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with datetime serialization."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, (LoginMethod, SessionInvalidationReason)):
                result[key] = value.value
            else:
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionData":
        """Create from dictionary with datetime deserialization."""
        # Convert datetime strings back to datetime objects
        datetime_fields = {
            "expires_at",
            "login_timestamp",
            "last_activity_timestamp",
            "created_at",
            "updated_at",
            "last_validated",
        }

        processed_data = {}
        for key, value in data.items():
            if key in datetime_fields and isinstance(value, str):
                try:
                    processed_data[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    processed_data[key] = datetime.fromisoformat(value)
            elif key == "login_method" and isinstance(value, str):
                processed_data[key] = LoginMethod(value)
            else:
                processed_data[key] = value

        return cls(**processed_data)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "SessionData":
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def is_expired(self) -> bool:
        """Check if the session has expired."""
        # Ensure both datetimes are timezone-aware for comparison
        now = datetime.now(timezone.utc)
        expires_at = self.expires_at

        # Handle timezone-naive expires_at by assuming UTC
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return now >= expires_at

    def time_to_expiry(self) -> float:
        """Get time to expiry in seconds."""
        now = datetime.now(timezone.utc)
        expires_at = self.expires_at

        # Handle timezone-naive expires_at by assuming UTC
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        delta = expires_at - now
        return max(0, delta.total_seconds())

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity_timestamp = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


@dataclass
class TradingSession:
    """Trading session model for backward compatibility."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    provider: AuthProvider = AuthProvider.MOCK
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    request_token: Optional[str] = None
    public_token: Optional[str] = None
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_activity: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if session is expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def is_active(self) -> bool:
        """Check if session is active."""
        return self.status == SessionStatus.ACTIVE and not self.is_expired()

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "provider": self.provider.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_activity": self.last_activity.isoformat(),
            "metadata": self.metadata,
            # Don't expose sensitive data in dict
        }


@dataclass
class AuthResponse:
    """Authentication response structure."""

    success: bool
    message: str
    session_data: Optional[SessionData] = None
    error_code: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None


@dataclass
class UserProfile:
    """User profile structure from Zerodha API."""

    user_id: str
    user_name: str
    user_shortname: str
    email: str
    user_type: str
    broker: str
    products: list
    order_types: list
    exchanges: list

    @classmethod
    def from_kite_response(cls, data: Dict[str, Any]) -> "UserProfile":
        """Create from KiteConnect API response."""
        return cls(
            user_id=data.get("user_id", ""),
            user_name=data.get("user_name", ""),
            user_shortname=data.get("user_shortname", ""),
            email=data.get("email", ""),
            user_type=data.get("user_type", ""),
            broker=data.get("broker", ""),
            products=data.get("products", []),
            order_types=data.get("order_types", []),
            exchanges=data.get("exchanges", []),
        )


class LoginRequest(BaseModel):
    """Login request model."""

    username: str = Field(..., min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=1)
    provider: AuthProvider = Field(AuthProvider.LOCAL)
    api_key: Optional[str] = Field(None, min_length=1)
    api_secret: Optional[str] = Field(None, min_length=1)
    request_token: Optional[str] = Field(None, min_length=1)
    remember_me: bool = Field(False)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LoginResponse(BaseModel):
    """Login response model."""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: Dict[str, Any]
    session: Dict[str, Any]


class TokenRequest(BaseModel):
    """Token refresh request model."""

    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None


class JWTTokenManager:
    """JWT token management utilities."""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm

    def create_access_token(
        self,
        user_id: str,
        expires_delta: Optional[timedelta] = None,
        additional_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create JWT access token."""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=30)

        to_encode = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access",
        }

        if additional_claims:
            to_encode.update(additional_claims)

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def create_refresh_token(self, user_id: str, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT refresh token."""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(days=7)

        to_encode = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "refresh",
        }

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {e}")

    def get_token_user_id(self, token: str) -> str:
        """Get user ID from token."""
        payload = self.decode_token(token)
        return payload.get("sub", "")

    def is_token_expired(self, token: str) -> bool:
        """Check if token is expired."""
        try:
            payload = self.decode_token(token)
            exp = payload.get("exp", 0)
            return datetime.now(timezone.utc).timestamp() > exp
        except Exception:
            return True


class InvalidTokenError(Exception):
    """Exception raised when token is invalid."""

    pass
