"""Authentication API endpoints."""

from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from core.auth.auth_manager import AuthManager
from core.logging.logger import get_logger
from core.config.settings import get_settings
from core.database.connection import DatabaseManager

logger = get_logger(__name__)

router = APIRouter()
security = HTTPBearer()


def get_auth_manager() -> AuthManager:
    """Get AuthManager instance with proper dependency injection."""
    settings = get_settings()
    db_manager = DatabaseManager(settings)
    return AuthManager(settings, db_manager)


class LoginRequest(BaseModel):
    api_key: str
    api_secret: str
    request_token: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    permissions: dict


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    user_id: str
    username: str
    email: Optional[str]
    permissions: dict
    created_at: datetime
    last_login: Optional[datetime]


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, auth_manager: AuthManager = Depends(get_auth_manager)):
    """Authenticate user and return access token."""
    try:
        # Authenticate with Zerodha if request_token provided
        if credentials.request_token:
            auth_result = await auth_manager.authenticate_zerodha(
                api_key=credentials.api_key,
                api_secret=credentials.api_secret,
                request_token=credentials.request_token
            )
        else:
            # Authenticate with API key/secret only
            auth_result = await auth_manager.authenticate_api_key(
                api_key=credentials.api_key,
                api_secret=credentials.api_secret
            )
        
        if not auth_result["success"]:
            raise HTTPException(
                status_code=401,
                detail=auth_result.get("error", "Authentication failed")
            )
        
        # Generate JWT token
        user_data = auth_result["user_data"]
        token_data = await auth_manager.create_jwt_token(user_data)
        
        return LoginResponse(
            access_token=token_data["access_token"],
            expires_in=token_data["expires_in"],
            user_id=user_data["user_id"],
            permissions=user_data.get("permissions", {})
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail="Authentication service error")


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(refresh_request: TokenRefreshRequest, auth_manager: AuthManager = Depends(get_auth_manager)):
    """Refresh access token using refresh token."""
    try:
        token_data = await auth_manager.refresh_jwt_token(refresh_request.refresh_token)
        
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        return LoginResponse(
            access_token=token_data["access_token"],
            expires_in=token_data["expires_in"],
            user_id=token_data["user_id"],
            permissions=token_data.get("permissions", {})
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=500, detail="Token refresh service error")


@router.post("/logout")
async def logout(token: str = Depends(security), auth_manager: AuthManager = Depends(get_auth_manager)):
    """Logout user and invalidate token."""
    try:
        success = await auth_manager.logout(token.credentials)
        
        if not success:
            raise HTTPException(status_code=400, detail="Logout failed")
        
        return {"message": "Logout successful"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Logout failed: {e}")
        raise HTTPException(status_code=500, detail="Logout service error")


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(token: str = Depends(security), auth_manager: AuthManager = Depends(get_auth_manager)):
    """Get current user information."""
    try:
        user_data = await auth_manager.get_user_from_token(token.credentials)
        
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return UserInfo(
            user_id=user_data["user_id"],
            username=user_data.get("username", ""),
            email=user_data.get("email"),
            permissions=user_data.get("permissions", {}),
            created_at=user_data.get("created_at", datetime.now()),
            last_login=user_data.get("last_login")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user info failed: {e}")
        raise HTTPException(status_code=500, detail="User service error")


@router.get("/status")
async def get_auth_status(auth_manager: AuthManager = Depends(get_auth_manager)):
    """Get authentication system status."""
    try:
        status = await auth_manager.get_auth_status()
        return status
        
    except Exception as e:
        logger.error(f"Get auth status failed: {e}")
        raise HTTPException(status_code=500, detail="Auth status service error")


@router.get("/zerodha/login-url")
async def get_zerodha_login_url(auth_manager: AuthManager = Depends(get_auth_manager)):
    """Get Zerodha login URL for OAuth flow."""
    try:
        login_url = auth_manager.get_zerodha_login_url()
        
        return {
            "login_url": login_url,
            "instructions": "Visit this URL to authorize the application with Zerodha"
        }
        
    except Exception as e:
        logger.error(f"Get Zerodha login URL failed: {e}")
        raise HTTPException(status_code=500, detail="Zerodha auth service error")


@router.post("/validate")
async def validate_token(token: str = Depends(security), auth_manager: AuthManager = Depends(get_auth_manager)):
    """Validate access token."""
    try:
        is_valid = await auth_manager.validate_token(token.credentials)
        
        return {
            "valid": is_valid,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(status_code=500, detail="Token validation service error")