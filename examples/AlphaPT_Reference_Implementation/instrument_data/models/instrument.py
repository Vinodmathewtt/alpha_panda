"""
Instrument data models for PostgreSQL storage.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Numeric, Boolean, Index
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Instrument(Base):
    """
    Instrument model representing trading instruments from Zerodha.
    
    This model stores comprehensive instrument information including
    tokens, symbols, pricing details, and trading parameters.
    """
    __tablename__ = 'instruments'
    
    # Primary identification
    instrument_token = Column(Integer, primary_key=True, doc="Unique instrument token from Zerodha")
    exchange_token = Column(Integer, nullable=False, doc="Exchange-specific token")
    
    # Instrument identification
    tradingsymbol = Column(String(50), nullable=False, index=True, doc="Trading symbol (e.g., RELIANCE)")
    name = Column(String(200), nullable=False, doc="Full instrument name")
    exchange = Column(String(10), nullable=False, index=True, doc="Exchange (NSE, BSE, etc.)")
    segment = Column(String(20), nullable=True, doc="Market segment")
    
    # Instrument classification
    instrument_type = Column(String(10), nullable=True, doc="Type: EQ, FUT, CE, PE, etc.")
    
    # Pricing information
    last_price = Column(Numeric(15, 4), nullable=True, doc="Last traded price")
    tick_size = Column(Numeric(10, 4), nullable=True, doc="Minimum price movement")
    lot_size = Column(Integer, nullable=True, doc="Lot size for trading")
    
    # Derivative specific fields
    expiry = Column(DateTime, nullable=True, doc="Expiry date for derivatives")
    strike = Column(Numeric(15, 4), nullable=True, doc="Strike price for options")
    
    # Registry metadata
    is_active = Column(Boolean, default=True, doc="Whether instrument is active for trading")
    created_at = Column(DateTime, default=datetime.utcnow, doc="Record creation timestamp")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, doc="Last update timestamp")
    source_file = Column(String(255), nullable=True, doc="Source CSV file name")
    
    # Database indexes for performance
    __table_args__ = (
        Index('idx_instruments_symbol_exchange', 'tradingsymbol', 'exchange'),
        Index('idx_instruments_exchange_type', 'exchange', 'instrument_type'),
        Index('idx_instruments_expiry', 'expiry'),
        Index('idx_instruments_active', 'is_active'),
        Index('idx_instruments_updated', 'updated_at'),
    )
    
    def __repr__(self) -> str:
        return (f"<Instrument(token={self.instrument_token}, "
                f"symbol={self.tradingsymbol}, exchange={self.exchange})>")
    
    def to_dict(self) -> dict:
        """Convert instrument to dictionary representation."""
        return {
            'instrument_token': self.instrument_token,
            'exchange_token': self.exchange_token,
            'tradingsymbol': self.tradingsymbol,
            'name': self.name,
            'exchange': self.exchange,
            'segment': self.segment,
            'instrument_type': self.instrument_type,
            'last_price': float(self.last_price) if self.last_price else None,
            'tick_size': float(self.tick_size) if self.tick_size else None,
            'lot_size': self.lot_size,
            'expiry': self.expiry.isoformat() if self.expiry else None,
            'strike': float(self.strike) if self.strike else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'source_file': self.source_file
        }
    
    @classmethod
    def from_csv_row(cls, row: dict, source_file: str = None) -> 'Instrument':
        """
        Create Instrument instance from CSV row data.
        
        Args:
            row: Dictionary containing CSV row data
            source_file: Source CSV file name
            
        Returns:
            Instrument instance
        """
        # Parse expiry date if present
        expiry = None
        if row.get('expiry') and row['expiry'].strip():
            try:
                expiry = datetime.strptime(row['expiry'].strip(), '%Y-%m-%d')
            except ValueError:
                expiry = None
        
        # Parse numeric fields safely
        def safe_decimal(value: str) -> Optional[Decimal]:
            if not value or value.strip() == '':
                return None
            try:
                return Decimal(str(value).strip())
            except (ValueError, TypeError):
                return None
        
        def safe_int(value: str) -> Optional[int]:
            if not value or value.strip() == '':
                return None
            try:
                return int(str(value).strip())
            except (ValueError, TypeError):
                return None
        
        return cls(
            instrument_token=int(row['instrument_token']),
            exchange_token=safe_int(row.get('exchange_token')) or 0,
            tradingsymbol=row['tradingsymbol'].strip(),
            name=row['name'].strip(),
            exchange=row['exchange'].strip(),
            segment=row.get('segment', '').strip() or None,
            instrument_type=row.get('instrument_type', '').strip() or None,
            last_price=safe_decimal(row.get('last_price')),
            tick_size=safe_decimal(row.get('tick_size')),
            lot_size=safe_int(row.get('lot_size')),
            expiry=expiry,
            strike=safe_decimal(row.get('strike')),
            source_file=source_file
        )


class InstrumentRegistry(Base):
    """
    Registry table to track active instruments for trading.
    
    This table maintains a curated list of instruments that are
    actively subscribed to for market data and trading.
    """
    __tablename__ = 'instrument_registry'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument_token = Column(Integer, nullable=False, unique=True, doc="Instrument token reference")
    tradingsymbol = Column(String(50), nullable=False, doc="Trading symbol for reference")
    exchange = Column(String(10), nullable=False, doc="Exchange name")
    
    # Registry specific fields
    is_subscribed = Column(Boolean, default=True, doc="Whether subscribed for market data")
    priority = Column(Integer, default=100, doc="Priority for processing (lower = higher priority)")
    added_at = Column(DateTime, default=datetime.utcnow, doc="When added to registry")
    added_by = Column(String(100), default='system', doc="Who/what added this instrument")
    notes = Column(String(500), nullable=True, doc="Additional notes about this instrument")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_registry_subscribed', 'is_subscribed'),
        Index('idx_registry_priority', 'priority'),
        Index('idx_registry_symbol', 'tradingsymbol'),
        Index('idx_registry_added', 'added_at'),
    )
    
    def __repr__(self) -> str:
        return (f"<InstrumentRegistry(token={self.instrument_token}, "
                f"symbol={self.tradingsymbol}, subscribed={self.is_subscribed})>")
    
    def to_dict(self) -> dict:
        """Convert registry entry to dictionary representation."""
        return {
            'id': self.id,
            'instrument_token': self.instrument_token,
            'tradingsymbol': self.tradingsymbol,
            'exchange': self.exchange,
            'is_subscribed': self.is_subscribed,
            'priority': self.priority,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'added_by': self.added_by,
            'notes': self.notes
        }