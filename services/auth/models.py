"""Authentication models for a non-interactive, token-based session flow."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AuthProvider(str, Enum):
    """Authentication provider types."""
    ZERODHA = "zerodha"
    LOCAL = "local" # For application user management, not trading

class AuthStatus(Enum):
    """Authentication status enumeration."""
    UNAUTHENTICATED = "unauthenticated"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    ERROR = "error"

class LoginMethod(Enum):
    """Login method enumeration."""
    EXTERNAL_TOKEN = "external_token"
    STORED_SESSION = "stored_session"
    OAUTH = "oauth"


@dataclass
class SessionData:
    """Standardized session data structure."""
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
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Audit fields
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_validated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with datetime serialization."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, LoginMethod):
                result[key] = value.value
            else:
                result[key] = value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionData":
        """Create from dictionary with datetime deserialization."""
        # Convert datetime strings back to datetime objects
        datetime_fields = {
            "expires_at", "login_timestamp", "last_activity_timestamp",
            "created_at", "updated_at", "last_validated"
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


@dataclass
class UserProfile:
    """User profile structure from Zerodha API."""
    user_id: str
    user_name: str
    user_shortname: str
    email: str
    broker: str

    @classmethod
    def from_kite_response(cls, data: Dict[str, Any]) -> "UserProfile":
        """Create from KiteConnect API response."""
        return cls(
            user_id=data.get("user_id", ""),
            user_name=data.get("user_name", ""),
            user_shortname=data.get("user_shortname", ""),
            email=data.get("email", ""),
            broker=data.get("broker", "zerodha"),
        )


class LoginRequest(BaseModel):
    """Login request model, now token-based for Zerodha."""
    provider: AuthProvider
    broker_access_token: Optional[str] = Field(None, description="Pre-authorized access token from Zerodha")

class LoginResponse(BaseModel):
    """Login response model."""
    success: bool
    message: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class SessionStatus(str, Enum):
    """Session status enumeration."""
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class SessionInvalidationReason(str, Enum):
    """Session invalidation reason enumeration."""
    MANUAL_INVALIDATION = "manual_invalidation"
    TOKEN_EXPIRED = "token_expired"
    SECURITY_BREACH = "security_breach"
    LOGOUT = "logout"
    ADMIN_ACTION = "admin_action"


@dataclass
class TradingSession:
    """Trading session model for auth service."""
    session_id: str
    user_id: str
    access_token: str
    start_time: datetime
    end_time: datetime
    is_active: bool
    login_method: LoginMethod
    status: SessionStatus = SessionStatus.ACTIVE
    user_profile: Optional[UserProfile] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        """Check if the session has expired."""
        return datetime.now(timezone.utc) >= self.end_time