"""Session management with PostgreSQL persistence following Alpha Panda patterns."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.database.models import TradingSession as DBTradingSession
from .models import (
    LoginMethod,
    SessionData,
    SessionInvalidationReason,
    SessionStatus,
    TradingSession,
)
from .exceptions import SessionExpiredError, SessionNotFoundError

logger = logging.getLogger(__name__)


class SessionManager:
    """Enhanced session manager with PostgreSQL persistence."""

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
        """FIXED: Save session data using upsert to prevent concurrent session duplication."""
        try:
            async with self.db_manager.get_session() as db_session:
                # Update timestamps
                session_data.updated_at = datetime.now(timezone.utc)
                session_data.last_validated = datetime.now(timezone.utc)

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

                # FIXED: Use PostgreSQL upsert to handle concurrent sessions safely
                stmt = pg_insert(DBTradingSession).values(
                    session_id=session_data.session_id or str(uuid.uuid4()),
                    user_id=session_data.user_id,
                    end_time=session_data.expires_at,
                    is_active=True,
                    session_data=session_dict,
                    updated_at=session_data.updated_at
                )
                
                stmt = stmt.on_conflict_do_update(
                    index_elements=['user_id'],  # Uses the unique constraint we added
                    set_={
                        'session_data': stmt.excluded.session_data,
                        'end_time': stmt.excluded.end_time,
                        'is_active': stmt.excluded.is_active,
                        'updated_at': stmt.excluded.updated_at
                    }
                )
                
                await db_session.execute(stmt)
                await db_session.commit()  # Service layer handles this transaction
                
                self._current_session = session_data
                logger.info(f"Successfully saved/updated session for user: {session_data.user_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            raise Exception(f"Failed to save session: {e}")

    async def load_session(
        self, mock_mode: bool = None, user_id: Optional[str] = None
    ) -> Optional[SessionData]:
        """Load valid session data from PostgreSQL database."""
        try:
            async with self.db_manager.get_session() as db_session:
                # Build base query for active, non-expired sessions
                conditions = [
                    DBTradingSession.is_active == True,
                    DBTradingSession.end_time > datetime.now(timezone.utc),
                ]

                # Add user filtering if specified
                if user_id:
                    conditions.append(DBTradingSession.user_id == user_id)

                query = (
                    select(DBTradingSession)
                    .where(and_(*conditions))
                    .order_by(DBTradingSession.updated_at.desc())
                )

                result = await db_session.execute(query)

                # If mock_mode is specified, filter sessions by login method
                sessions = result.fetchall()
                if not sessions:
                    logger.debug(
                        f"No valid session found in database (user_id={user_id}, mock_mode={mock_mode})"
                    )
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

                # Extract session data
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

    async def invalidate_session(
        self,
        reason: SessionInvalidationReason = SessionInvalidationReason.MANUAL_INVALIDATION,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """Invalidate the current session in database."""
        try:
            async with self.db_manager.get_session() as db_session:
                if self._current_session:
                    user_id = self._current_session.user_id
                    logger.info(
                        f"Invalidating session for user: {user_id}, reason: {reason.value}"
                    )

                    # Update database
                    result = await db_session.execute(
                        update(DBTradingSession)
                        .where(DBTradingSession.user_id == user_id)
                        .values(
                            is_active=False, updated_at=datetime.now(timezone.utc)
                        )
                    )
                    await db_session.commit()
                else:
                    # Invalidate all active sessions if no specific session
                    result = await db_session.execute(
                        update(DBTradingSession)
                        .where(DBTradingSession.is_active == True)
                        .values(
                            is_active=False, updated_at=datetime.now(timezone.utc)
                        )
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

    async def _cleanup_expired_sessions(self) -> None:
        """Background task to cleanup expired sessions."""
        logger.info("Session cleanup task started")

        while self._running:
            try:
                # Cleanup every 5 minutes
                await asyncio.sleep(300)

                # Remove expired sessions from database
                async with self.db_manager.get_session() as db_session:
                    result = await db_session.execute(
                        update(DBTradingSession)
                        .where(
                            DBTradingSession.is_active == True,
                            DBTradingSession.end_time < datetime.now(timezone.utc),
                        )
                        .values(
                            is_active=False, updated_at=datetime.now(timezone.utc)
                        )
                    )

                    expired_count = result.rowcount
                    if expired_count > 0:
                        await db_session.commit()
                        logger.info(f"Cleaned up {expired_count} expired sessions")

                # Remove expired sessions from local cache
                expired_sessions = [
                    sid
                    for sid, session in self._session_cache.items()
                    if session.is_expired()
                ]
                for sid in expired_sessions:
                    del self._session_cache[sid]

                if expired_sessions:
                    logger.info(
                        f"Removed {len(expired_sessions)} expired sessions from cache"
                    )

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
                async with self.db_manager.get_session() as db_session:
                    result = await db_session.execute(
                        select(DBTradingSession).limit(1)
                    )
                    result.scalar_one_or_none()
            except Exception as e:
                health_status["database_available"] = False
                health_status["error"] = f"Database error: {e}"

            return health_status

        except Exception as e:
            return {"running": self._running, "error": str(e)}