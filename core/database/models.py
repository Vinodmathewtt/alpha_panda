# Database models for application state
from sqlalchemy import Column, Integer, String, Float, JSON, Boolean, DateTime, Text, UniqueConstraint, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from .connection import Base


class User(Base):
    """User account for managing the application"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TradingSession(Base):
    """Trading session storage for authentication persistence"""
    __tablename__ = "trading_sessions"

    session_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True, unique=True)  # FIXED: Added unique constraint
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True, nullable=False)
    session_data = Column(JSONB)  # FIXED: Changed to JSONB for PostgreSQL optimization
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Add index for performance
    __table_args__ = (
        Index('idx_trading_sessions_updated_at', 'updated_at'),
        Index('idx_trading_sessions_is_active', 'is_active'),
        Index('idx_trading_sessions_active_user', 'user_id', 'is_active'),
    )


class StrategyConfiguration(Base):
    """Master configuration for a single trading strategy"""
    __tablename__ = "strategy_configurations"

    id = Column(String, primary_key=True, index=True)  # e.g., "Momentum_NIFTY_1"
    strategy_type = Column(String, nullable=False)     # e.g., "MomentumProcessor"
    instruments = Column(JSON, nullable=False)         # e.g., [738561, 2714625]
    parameters = Column(JSON, nullable=False)          # e.g., {"lookback_period": 20}
    is_active = Column(Boolean, default=True, nullable=False)
    
    # CRITICAL: Fixed from live_trading_enabled
    zerodha_trading_enabled = Column(Boolean, default=False, nullable=False)  # Enable zerodha trading
    
    # Migration support: Use composition architecture flag
    use_composition = Column(Boolean, default=True, nullable=False)  # NEW: Default to composition
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PortfolioSnapshot(Base):
    """Persistent storage of portfolio states for paper trading continuity"""
    __tablename__ = "portfolio_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(String, nullable=False, index=True, unique=True)  # FIXED: Added unique constraint for upsert
    broker_namespace = Column(String, nullable=False, index=True)  # "paper" or "zerodha"
    strategy_id = Column(String, nullable=False, index=True)
    
    # Portfolio state
    positions = Column(JSONB, nullable=False)  # FIXED: Changed to JSONB for PostgreSQL optimization
    total_realized_pnl = Column(Float, default=0.0, nullable=False)
    total_unrealized_pnl = Column(Float, default=0.0, nullable=False)
    total_pnl = Column(Float, default=0.0, nullable=False)
    cash = Column(Float, default=1_000_000.0, nullable=False)
    
    snapshot_time = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Add indexes for performance
    __table_args__ = (
        Index('idx_portfolio_snapshots_broker_time', 'broker_namespace', 'snapshot_time'),
        Index('idx_portfolio_snapshots_strategy', 'strategy_id'),
        Index('idx_portfolio_snapshots_time_desc', 'snapshot_time', postgresql_ops={'snapshot_time': 'DESC'}),
    )


class TradingEvent(Base):
    """Historical record of all trading events for audit and recovery"""
    __tablename__ = "trading_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, nullable=False, index=True)  # UUID from EventEnvelope
    event_type = Column(String, nullable=False)  # "ORDER_FILLED", "TRADING_SIGNAL", etc.
    broker_namespace = Column(String, nullable=False, index=True)
    strategy_id = Column(String, nullable=False, index=True)
    instrument_token = Column(Integer, nullable=False, index=True)
    
    # Event data
    event_data = Column(JSONB, nullable=False)  # FIXED: Changed to JSONB for PostgreSQL optimization
    correlation_id = Column(String, nullable=True, index=True)  # For tracing
    
    event_timestamp = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Add indexes for performance
    __table_args__ = (
        Index('idx_trading_events_broker_time', 'broker_namespace', 'event_timestamp'),
        Index('idx_trading_events_correlation', 'correlation_id'),
        Index('idx_trading_events_strategy_time', 'strategy_id', 'event_timestamp'),
        Index('idx_trading_events_instrument_time', 'instrument_token', 'event_timestamp'),
    )