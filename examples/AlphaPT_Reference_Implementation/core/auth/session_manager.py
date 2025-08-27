"""Session management for trading sessions following reference implementation."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.exceptions import SessionExpiredError, SessionNotFoundError
from core.auth.models import (
    AuthProvider,
    LoginMethod,
    SessionData,
    SessionInvalidationReason,
    SessionStatus,
    TradingSession,
    User,
)
from core.config.settings import Settings
from core.utils.exceptions import DatabaseError
from core.database.connection import DatabaseManager
from core.database.models import TradingSession as DBTradingSession

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages trading sessions with PostgreSQL database following reference implementation."""

    def __init__(self, settings: Settings, db_manager: DatabaseManager):
        self.settings = settings
        self.db_manager = db_manager
        self._current_session: Optional[SessionData] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        self._session_cache: Dict[str, TradingSession] = {}

    async def start(self) -> None:
        """Start session manager."""
        if self._running:
            return

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
        self._running = True

        logger.info("Session manager started")

    async def stop(self) -> None:
        """Stop session manager."""
        if not self._running:
            return

        # Stop cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        self._current_session = None
        self._running = False

        logger.info("Session manager stopped")

    async def save_session(self, session_data: SessionData) -> bool:
        """Save session data to PostgreSQL database."""
        try:
            async with self.db_manager.get_postgres_session() as db_session:
                # Update timestamps
                session_data.updated_at = datetime.now(timezone.utc)
                session_data.last_validated = datetime.now(timezone.utc)

                # Check if session exists
                result = await db_session.execute(
                    select(DBTradingSession).where(DBTradingSession.user_id == session_data.user_id)
                )
                existing = result.scalar_one_or_none()

                # Prepare session data
                session_dict = {
                    "access_token": session_data.access_token,
                    "user_name": session_data.user_name,
                    "user_shortname": session_data.user_shortname,
                    "broker": session_data.broker,
                    "email": session_data.email,
                    "login_method": session_data.login_method.value,
                    "ip_address": session_data.ip_address,
                    "user_agent": session_data.user_agent,
                }

                if existing:
                    # Update existing session
                    existing.session_data = session_dict
                    existing.end_time = session_data.expires_at
                    existing.is_active = True
                    existing.updated_at = session_data.updated_at

                    logger.info(f"Updated existing session for user: {session_data.user_id}")
                else:
                    # Create new session
                    db_session_obj = DBTradingSession(
                        session_id=session_data.session_id or str(uuid.uuid4()),
                        user_id=session_data.user_id,
                        end_time=session_data.expires_at,
                        is_active=True,
                        session_data=session_dict,
                    )
                    db_session.add(db_session_obj)

                    logger.info(f"Created new session for user: {session_data.user_id}")

                await db_session.commit()
                self._current_session = session_data
                return True

        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            raise DatabaseError(f"Failed to save session: {e}")

    async def load_session(self, mock_mode: bool = None, user_id: Optional[str] = None) -> Optional[SessionData]:
        """Load valid session data from PostgreSQL database.
        
        Args:
            mock_mode: If True, only load mock sessions. If False, only load real sessions.
                      If None, load any session (backward compatibility).
            user_id: If provided, filter sessions by user_id. If None, load most recent session (single-user assumption).
        """
        try:
            async with self.db_manager.get_postgres_session() as db_session:
                # Build base query for active, non-expired sessions
                conditions = [
                    DBTradingSession.is_active == True, 
                    DBTradingSession.end_time > datetime.now(timezone.utc)
                ]
                
                # Add user filtering if specified
                if user_id:
                    conditions.append(DBTradingSession.user_id == user_id)
                    
                query = select(DBTradingSession).where(
                    and_(*conditions)
                ).order_by(DBTradingSession.updated_at.desc())
                
                result = await db_session.execute(query)
                
                # If mock_mode is specified, filter sessions by login method
                sessions = result.fetchall()
                if not sessions:
                    logger.debug(f"No valid session found in database (user_id={user_id}, mock_mode={mock_mode})")
                    return None
                
                db_session_obj = None
                if mock_mode is not None:
                    # Filter sessions based on mock_mode preference
                    for session_row in sessions:
                        session_obj = session_row[0]
                        session_dict = session_obj.session_data or {}
                        login_method = session_dict.get("login_method", "oauth")
                        
                        if mock_mode and login_method == "mock":
                            db_session_obj = session_obj
                            break
                        elif not mock_mode and login_method != "mock":
                            db_session_obj = session_obj
                            break
                    
                    if not db_session_obj:
                        logger.debug(f"No valid session found for mock_mode={mock_mode}")
                        return None
                else:
                    # Backward compatibility - take the most recent session
                    db_session_obj = sessions[0][0]

                # db_session_obj is already extracted above
                session_dict = db_session_obj.session_data or {}

                # Convert to SessionData with defensive null handling
                now = datetime.now(timezone.utc)
                session_data = SessionData(
                    user_id=db_session_obj.user_id,
                    access_token=session_dict.get("access_token", ""),
                    expires_at=db_session_obj.end_time or now,
                    login_timestamp=db_session_obj.start_time or now,
                    last_activity_timestamp=db_session_obj.updated_at or now,
                    login_method=LoginMethod(session_dict.get("login_method", "oauth")),
                    user_name=session_dict.get("user_name"),
                    user_shortname=session_dict.get("user_shortname"),
                    broker=session_dict.get("broker"),
                    email=session_dict.get("email"),
                    ip_address=session_dict.get("ip_address"),
                    user_agent=session_dict.get("user_agent"),
                    session_id=db_session_obj.session_id,
                    created_at=db_session_obj.start_time or now,
                    updated_at=db_session_obj.updated_at or now,
                    last_validated=db_session_obj.updated_at or now,
                )

                # Update activity timestamp
                session_data.update_activity()
                self._current_session = session_data

                # Update last activity in database
                db_session_obj.updated_at = session_data.last_activity_timestamp
                await db_session.commit()

                logger.info(f"Loaded session for user: {session_data.user_id}")
                return session_data

        except Exception as e:
            logger.warning(f"Failed to load session [{type(e).__name__}]: {e}")
            return None

    def get_current_session(self) -> Optional[SessionData]:
        """Get the current session data."""
        if self._current_session and not self._current_session.is_expired():
            return self._current_session
        return None

    def is_session_valid(self) -> bool:
        """Check if current session is valid."""
        session = self.get_current_session()
        return session is not None and not session.is_expired()

    async def clear_sessions_by_type(self, mock_sessions: bool = True) -> int:
        """Clear sessions by type (mock vs real).
        
        Args:
            mock_sessions: If True, clear mock sessions. If False, clear real sessions.
            
        Returns:
            Number of sessions cleared.
        """
        try:
            cleared_count = 0
            async with self.db_manager.get_postgres_session() as db_session:
                # Get all active sessions
                result = await db_session.execute(
                    select(DBTradingSession).where(DBTradingSession.is_active == True)
                )
                sessions = result.fetchall()
                
                for session_row in sessions:
                    session_obj = session_row[0]
                    session_dict = session_obj.session_data or {}
                    login_method = session_dict.get("login_method", "oauth")
                    
                    should_clear = False
                    if mock_sessions and login_method == "mock":
                        should_clear = True
                    elif not mock_sessions and login_method != "mock":
                        should_clear = True
                    
                    if should_clear:
                        session_obj.is_active = False
                        session_obj.updated_at = datetime.now(timezone.utc)
                        cleared_count += 1
                        logger.debug(f"Cleared {'mock' if mock_sessions else 'real'} session for user: {session_obj.user_id}")
                
                await db_session.commit()
                
            if cleared_count > 0:
                logger.info(f"Cleared {cleared_count} {'mock' if mock_sessions else 'real'} session(s)")
                
            return cleared_count
        except Exception as e:
            logger.error(f"Failed to clear sessions: {e}")
            return 0

    async def invalidate_session(
        self,
        reason: SessionInvalidationReason = SessionInvalidationReason.MANUAL_INVALIDATION,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """Invalidate the current session in database."""
        try:
            async with self.db_manager.get_postgres_session() as db_session:
                if self._current_session:
                    user_id = self._current_session.user_id
                    logger.info(f"Invalidating session for user: {user_id}, reason: {reason.value}")

                    # Update database
                    result = await db_session.execute(
                        update(DBTradingSession)
                        .where(DBTradingSession.user_id == user_id)
                        .values(is_active=False, updated_at=datetime.now(timezone.utc))
                    )

                    await db_session.commit()
                else:
                    # Invalidate all active sessions if no specific session
                    result = await db_session.execute(
                        update(DBTradingSession)
                        .where(DBTradingSession.is_active == True)
                        .values(is_active=False, updated_at=datetime.now(timezone.utc))
                    )

                    await db_session.commit()
                    logger.info("Invalidated all active sessions")

                # Clear in-memory session
                self._current_session = None
                return True

        except Exception as e:
            logger.error(f"Failed to invalidate session: {e}")
            return False

    async def create_session_from_kite_response(
        self, kite_response: Dict[str, Any], login_method: LoginMethod = LoginMethod.OAUTH
    ) -> SessionData:
        """Create session data from KiteConnect API response."""
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(hours=24)  # Zerodha tokens expire daily

        session_data = SessionData(
            user_id=kite_response.get("user_id", ""),
            user_name=kite_response.get("user_name"),
            user_shortname=kite_response.get("user_shortname"),
            broker=kite_response.get("broker"),
            email=kite_response.get("email"),
            access_token=kite_response.get("access_token", ""),
            expires_at=expiry,
            login_timestamp=now,
            last_activity_timestamp=now,
            login_method=login_method,
            created_at=now,
            updated_at=now,
            last_validated=now,
        )

        return session_data

    async def create_session(
        self,
        user: User,
        provider: AuthProvider = AuthProvider.MOCK,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        request_token: Optional[str] = None,
        public_token: Optional[str] = None,
        expires_in: Optional[int] = None,  # seconds
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TradingSession:
        """Create a new trading session."""
        try:
            # Calculate expiry time
            expires_at = None
            if expires_in:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            elif provider == AuthProvider.ZERODHA:
                # Zerodha tokens expire daily
                expires_at = datetime.now(timezone.utc) + timedelta(days=1)
            else:
                # Default session timeout
                expires_at = datetime.now(timezone.utc) + timedelta(hours=8)

            # Create session
            session = TradingSession(
                user_id=user.user_id,
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                api_key=api_key,
                api_secret=api_secret,
                request_token=request_token,
                public_token=public_token,
                expires_at=expires_at,
                metadata=metadata or {},
            )

            # Save to database
            await self._save_session_to_db(session)

            # Cache session
            self._session_cache[session.session_id] = session


            logger.info(f"Created session {session.session_id} for user {user.user_id}")
            return session

        except Exception as e:
            logger.error(f"Failed to create session for user {user.user_id}: {e}")
            raise DatabaseError(f"Session creation failed: {e}")

    async def get_session(self, session_id: str) -> TradingSession:
        """Get trading session by ID."""
        # Check local cache first
        if session_id in self._session_cache:
            session = self._session_cache[session_id]
            if session.is_active():
                session.update_activity()
                return session
            else:
                # Remove expired session from cache
                del self._session_cache[session_id]


        # Load from database
        session = await self._load_session_from_db(session_id)
        if session:
            if session.is_active():
                self._session_cache[session_id] = session
                session.update_activity()
                return session
            else:
                raise SessionExpiredError(f"Session {session_id} has expired")

        raise SessionNotFoundError(f"Session {session_id} not found")

    async def get_user_sessions(self, user_id: str) -> List[TradingSession]:
        """Get all active sessions for a user."""
        try:
            async with self.db_manager.get_postgres_session() as db_session:
                result = await db_session.execute(
                    select(DBTradingSession).where(
                        DBTradingSession.user_id == user_id, DBTradingSession.is_active == True
                    )
                )
                db_sessions = result.scalars().all()

                sessions = []
                for db_session_data in db_sessions:
                    session = self._db_session_to_model(db_session_data)
                    if session.is_active():
                        sessions.append(session)

                return sessions

        except Exception as e:
            logger.error(f"Failed to get sessions for user {user_id}: {e}")
            raise DatabaseError(f"Session retrieval failed: {e}")

    async def update_session(
        self,
        session_id: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TradingSession:
        """Update session data."""
        session = await self.get_session(session_id)

        # Update fields
        if access_token is not None:
            session.access_token = access_token
        if refresh_token is not None:
            session.refresh_token = refresh_token
        if expires_at is not None:
            session.expires_at = expires_at
        if metadata is not None:
            session.metadata.update(metadata)

        session.update_activity()

        # Save to database
        await self._save_session_to_db(session)

        # Update cache
        self._session_cache[session_id] = session


        logger.info(f"Updated session {session_id}")
        return session

    async def terminate_session(self, session_id: str) -> bool:
        """Terminate a session."""
        try:
            # Update status to terminated
            async with self.db_manager.get_postgres_session() as db_session:
                result = await db_session.execute(
                    update(DBTradingSession)
                    .where(DBTradingSession.session_id == session_id)
                    .values(is_active=False, end_time=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
                )

                success = result.rowcount > 0
                if success:
                    await db_session.commit()

                    # Remove from caches
                    self._session_cache.pop(session_id, None)


                    logger.info(f"Terminated session {session_id}")

                return success

        except Exception as e:
            logger.error(f"Failed to terminate session {session_id}: {e}")
            raise DatabaseError(f"Session termination failed: {e}")

    async def terminate_user_sessions(self, user_id: str) -> int:
        """Terminate all sessions for a user."""
        try:
            async with self.db_manager.get_postgres_session() as db_session:
                result = await db_session.execute(
                    update(DBTradingSession)
                    .where(DBTradingSession.user_id == user_id, DBTradingSession.is_active == True)
                    .values(is_active=False, end_time=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
                )

                terminated_count = result.rowcount
                await db_session.commit()

                # Remove from local cache
                to_remove = [sid for sid, session in self._session_cache.items() if session.user_id == user_id]
                for sid in to_remove:
                    del self._session_cache[sid]


                logger.info(f"Terminated {terminated_count} sessions for user {user_id}")
                return terminated_count

        except Exception as e:
            logger.error(f"Failed to terminate sessions for user {user_id}: {e}")
            raise DatabaseError(f"Session termination failed: {e}")

    async def _save_session_to_db(self, session: TradingSession) -> None:
        """Save session to database."""
        try:
            async with self.db_manager.get_postgres_session() as db_session:
                # Check if session exists
                result = await db_session.execute(
                    select(DBTradingSession).where(DBTradingSession.session_id == session.session_id)
                )
                db_session_obj = result.scalar_one_or_none()

                session_data = {
                    "access_token": session.access_token,
                    "refresh_token": session.refresh_token,
                    "api_key": session.api_key,
                    "api_secret": session.api_secret,
                    "request_token": session.request_token,
                    "public_token": session.public_token,
                    **session.metadata,
                }

                if db_session_obj:
                    # Update existing
                    db_session_obj.end_time = session.expires_at
                    db_session_obj.is_active = session.is_active()
                    db_session_obj.session_data = session_data
                    db_session_obj.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new
                    db_session_obj = DBTradingSession(
                        session_id=session.session_id,
                        user_id=session.user_id,
                        end_time=session.expires_at,
                        is_active=session.is_active(),
                        session_data=session_data,
                    )
                    db_session.add(db_session_obj)

                await db_session.commit()

        except Exception as e:
            logger.error(f"Failed to save session to database: {e}")
            raise

    async def _load_session_from_db(self, session_id: str) -> Optional[TradingSession]:
        """Load session from database."""
        try:
            async with self.db_manager.get_postgres_session() as db_session:
                result = await db_session.execute(
                    select(DBTradingSession).where(DBTradingSession.session_id == session_id)
                )
                db_session_obj = result.scalar_one_or_none()

                if db_session_obj:
                    return self._db_session_to_model(db_session_obj)

                return None

        except Exception as e:
            logger.error(f"Failed to load session from database: {e}")
            raise

    def _db_session_to_model(self, db_session: DBTradingSession) -> TradingSession:
        """Convert database session to model."""
        session_data = db_session.session_data or {}

        return TradingSession(
            session_id=db_session.session_id,
            user_id=db_session.user_id,
            provider=AuthProvider.ZERODHA,  # Default for now
            access_token=session_data.get("access_token"),
            refresh_token=session_data.get("refresh_token"),
            api_key=session_data.get("api_key"),
            api_secret=session_data.get("api_secret"),
            request_token=session_data.get("request_token"),
            public_token=session_data.get("public_token"),
            status=SessionStatus.ACTIVE if db_session.is_active else SessionStatus.TERMINATED,
            created_at=db_session.start_time,
            expires_at=db_session.end_time,
            last_activity=db_session.updated_at,
            metadata={
                k: v
                for k, v in session_data.items()
                if k not in ["access_token", "refresh_token", "api_key", "api_secret", "request_token", "public_token"]
            },
        )


    async def _cleanup_expired_sessions(self) -> None:
        """Background task to cleanup expired sessions."""
        logger.info("Session cleanup task started")

        while self._running:
            try:
                # Cleanup every 5 minutes
                await asyncio.sleep(300)

                # Remove expired sessions from database
                async with self.db_manager.get_postgres_session() as db_session:
                    result = await db_session.execute(
                        update(DBTradingSession)
                        .where(
                            DBTradingSession.is_active == True, DBTradingSession.end_time < datetime.now(timezone.utc)
                        )
                        .values(is_active=False, updated_at=datetime.now(timezone.utc))
                    )

                    expired_count = result.rowcount
                    if expired_count > 0:
                        await db_session.commit()
                        logger.info(f"Cleaned up {expired_count} expired sessions")

                # Remove expired sessions from local cache
                expired_sessions = [sid for sid, session in self._session_cache.items() if session.is_expired()]
                for sid in expired_sessions:
                    del self._session_cache[sid]

                if expired_sessions:
                    logger.info(f"Removed {len(expired_sessions)} expired sessions from cache")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")

        logger.info("Session cleanup task stopped")

    async def health_check(self) -> Dict[str, Any]:
        """Get session manager health status."""
        try:
            health_status = {
                "running": self._running,
                "cached_sessions": len(self._session_cache),
                "database_available": True,
                "error": None,
            }

            # Test database connection
            try:
                async with self.db_manager.get_postgres_session() as db_session:
                    result = await db_session.execute(select(DBTradingSession).limit(1))
                    result.scalar_one_or_none()
            except Exception as e:
                health_status["database_available"] = False
                health_status["error"] = f"Database error: {e}"


            return health_status

        except Exception as e:
            return {"running": self._running, "error": str(e)}
