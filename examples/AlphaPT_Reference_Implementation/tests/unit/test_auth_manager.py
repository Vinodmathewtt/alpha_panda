"""
Unit tests for authentication manager.

Tests authentication, session management, and security features.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from typing import Optional

import pytest

from core.auth.auth_manager import AuthManager
from core.auth.models import SessionData, LoginMethod
from core.auth.exceptions import AuthenticationError, SessionExpiredError
from core.config.settings import Settings
from core.database.connection import DatabaseManager


@pytest.mark.unit
class TestAuthManager:
    """Test the AuthManager class."""
    
    async def test_auth_manager_initialization(self, mock_settings, mock_database_manager):
        """Test AuthManager initialization."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        assert auth_manager.settings == mock_settings
        assert auth_manager.db_manager == mock_database_manager
        assert auth_manager.session_manager is not None
        
    async def test_auth_manager_initialize(self, mock_settings, mock_database_manager):
        """Test AuthManager initialization process."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        with patch.object(auth_manager.session_manager, 'start', new_callable=AsyncMock) as mock_start:
            result = await auth_manager.initialize()
            
            mock_start.assert_called_once()
            assert result is True
            
    async def test_auth_manager_cleanup(self, mock_settings, mock_database_manager):
        """Test AuthManager cleanup process."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        with patch.object(auth_manager.session_manager, 'stop', new_callable=AsyncMock) as mock_stop:
            await auth_manager.cleanup()
            mock_stop.assert_called_once()
            
    async def test_is_authenticated_no_session(self, mock_settings, mock_database_manager):
        """Test is_authenticated when no session exists."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=None):
            result = auth_manager.is_authenticated()
            assert result is False
            
    async def test_is_authenticated_expired_session(self, mock_settings, mock_database_manager):
        """Test is_authenticated with expired session."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Create expired session
        expired_session = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="expired_token",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
            login_timestamp=datetime.now(timezone.utc),
            last_activity_timestamp=datetime.now(timezone.utc),
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_validated=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=expired_session):
            result = auth_manager.is_authenticated()
            assert result is False
            
    async def test_is_authenticated_valid_session(self, mock_settings, mock_database_manager):
        """Test is_authenticated with valid session."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Create valid session
        valid_session = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="valid_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),  # Valid
            login_timestamp=datetime.now(timezone.utc),
            last_activity_timestamp=datetime.now(timezone.utc),
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_validated=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=valid_session):
            result = auth_manager.is_authenticated()
            assert result is True
            
    async def test_get_access_token_no_session(self, mock_settings, mock_database_manager):
        """Test get_access_token when no session exists."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=None):
            token = auth_manager.get_access_token()
            assert token is None
            
    async def test_get_access_token_valid_session(self, mock_settings, mock_database_manager):
        """Test get_access_token with valid session."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Create valid session with token
        session_with_token = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="test_access_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            login_timestamp=datetime.now(timezone.utc),
            last_activity_timestamp=datetime.now(timezone.utc),
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_validated=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=session_with_token):
            token = auth_manager.get_access_token()
            assert token == "test_access_token"
            
    async def test_set_access_token(self, mock_settings, mock_database_manager):
        """Test setting access token."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Create session without token
        session_without_token = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            login_timestamp=datetime.now(timezone.utc),
            last_activity_timestamp=datetime.now(timezone.utc),
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_validated=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=session_without_token), \
             patch.object(auth_manager.session_manager, 'save_session', new_callable=AsyncMock) as mock_save:
            
            await auth_manager.set_access_token("new_access_token")
            
            # Verify save was called with updated session
            mock_save.assert_called_once()
            saved_session = mock_save.call_args[0][0]
            assert saved_session.access_token == "new_access_token"
            
    async def test_authenticate_zerodha_success(self, mock_settings, mock_database_manager):
        """Test successful Zerodha authentication."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Mock successful authentication response
        mock_auth_response = {
            "user_id": "ZD1234",
            "user_name": "Test User",
            "user_shortname": "TU",
            "email": "test@example.com",
            "broker": "ZERODHA",
            "access_token": "auth_token_123"
        }
        
        with patch('core.auth.auth_manager.authenticate_with_zerodha', new_callable=AsyncMock, return_value=mock_auth_response), \
             patch.object(auth_manager.session_manager, 'save_session', new_callable=AsyncMock) as mock_save:
            
            request_token = "test_request_token"
            result = await auth_manager.authenticate_zerodha(request_token)
            
            assert result is True
            mock_save.assert_called_once()
            
            # Verify session was created with correct data
            saved_session = mock_save.call_args[0][0]
            assert saved_session.user_id == "ZD1234"
            assert saved_session.access_token == "auth_token_123"
            assert saved_session.login_method == LoginMethod.OAUTH
            
    async def test_authenticate_zerodha_failure(self, mock_settings, mock_database_manager):
        """Test failed Zerodha authentication."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        with patch('core.auth.auth_manager.authenticate_with_zerodha', new_callable=AsyncMock, side_effect=AuthenticationError("Invalid request token")):
            request_token = "invalid_request_token"
            
            with pytest.raises(AuthenticationError):
                await auth_manager.authenticate_zerodha(request_token)
                
    async def test_get_profile_no_session(self, mock_settings, mock_database_manager):
        """Test get_profile when no session exists."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=None):
            profile = auth_manager.get_profile()
            assert profile is None
            
    async def test_get_profile_valid_session(self, mock_settings, mock_database_manager):
        """Test get_profile with valid session."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Create valid session
        valid_session = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="valid_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            login_timestamp=datetime.now(timezone.utc),
            last_activity_timestamp=datetime.now(timezone.utc),
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_validated=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=valid_session):
            profile = auth_manager.get_profile()
            
            assert profile is not None
            assert profile["user_id"] == "test_user"
            assert profile["user_name"] == "Test User"
            assert profile["broker"] == "zerodha"
            assert profile["email"] == "test@example.com"
            
    async def test_get_session_info_no_session(self, mock_settings, mock_database_manager):
        """Test get_session_info when no session exists."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=None):
            session_info = auth_manager.get_session_info()
            assert session_info is None
            
    async def test_get_session_info_valid_session(self, mock_settings, mock_database_manager):
        """Test get_session_info with valid session."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Create valid session
        login_time = datetime.now(timezone.utc)
        valid_session = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="valid_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            login_timestamp=login_time,
            last_activity_timestamp=datetime.now(timezone.utc),
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_validated=datetime.now(timezone.utc)
        )
        
        with patch.object(auth_manager.session_manager, 'get_current_session', return_value=valid_session):
            session_info = auth_manager.get_session_info()
            
            assert session_info is not None
            assert session_info["session_id"] == "test_session"
            assert session_info["login_method"] == "oauth"
            assert session_info["login_timestamp"] == login_time
            assert session_info["is_expired"] is False
            
    async def test_logout(self, mock_settings, mock_database_manager):
        """Test user logout."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        with patch.object(auth_manager.session_manager, 'invalidate_session', new_callable=AsyncMock) as mock_invalidate:
            await auth_manager.logout()
            mock_invalidate.assert_called_once()


@pytest.mark.unit 
class TestSessionData:
    """Test the SessionData model."""
    
    def test_session_data_creation(self):
        """Test creating a SessionData instance."""
        now = datetime.now(timezone.utc)
        session = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="test_token",
            expires_at=now + timedelta(hours=1),
            login_timestamp=now,
            last_activity_timestamp=now,
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=now,
            updated_at=now,
            last_validated=now
        )
        
        assert session.user_id == "test_user"
        assert session.access_token == "test_token"
        assert session.login_method == LoginMethod.OAUTH
        
    def test_session_is_expired_false(self):
        """Test is_expired returns False for valid session."""
        now = datetime.now(timezone.utc)
        session = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="test_token",
            expires_at=now + timedelta(hours=1),  # Future expiry
            login_timestamp=now,
            last_activity_timestamp=now,
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=now,
            updated_at=now,
            last_validated=now
        )
        
        assert session.is_expired() is False
        
    def test_session_is_expired_true(self):
        """Test is_expired returns True for expired session."""
        now = datetime.now(timezone.utc)
        session = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="test_token",
            expires_at=now - timedelta(hours=1),  # Past expiry
            login_timestamp=now,
            last_activity_timestamp=now,
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=now,
            updated_at=now,
            last_validated=now
        )
        
        assert session.is_expired() is True
        
    def test_session_to_dict(self):
        """Test converting session to dictionary."""
        now = datetime.now(timezone.utc)
        session = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="test_token",
            expires_at=now + timedelta(hours=1),
            login_timestamp=now,
            last_activity_timestamp=now,
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=now,
            updated_at=now,
            last_validated=now
        )
        
        session_dict = session.model_dump()
        
        assert session_dict["user_id"] == "test_user"
        assert session_dict["access_token"] == "test_token"
        assert session_dict["login_method"] == LoginMethod.OAUTH


@pytest.mark.unit
class TestAuthenticationExceptions:
    """Test authentication exception handling."""
    
    def test_authentication_error(self):
        """Test AuthenticationError exception."""
        error = AuthenticationError("Invalid credentials")
        
        assert str(error) == "Invalid credentials"
        assert isinstance(error, Exception)
        
    def test_session_error(self):
        """Test SessionError exception."""
        error = SessionError("Session expired")
        
        assert str(error) == "Session expired"
        assert isinstance(error, Exception)
        
    def test_authentication_error_with_details(self):
        """Test AuthenticationError with additional details."""
        details = {"error_code": "INVALID_TOKEN", "user_id": "test_user"}
        error = AuthenticationError("Token validation failed", details)
        
        assert str(error) == "Token validation failed"
        assert error.details == details