"""
Repository pattern for instrument data database operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, desc, asc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.logging import get_database_logger_safe

logger = get_database_logger_safe("services.instrument_data.instrument_repository")
from .instrument import Instrument, InstrumentRegistry


class InstrumentRepository:
    """
    Repository for instrument database operations.
    
    Provides async database operations for instrument data management
    with proper error handling and logging.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.
        
        Args:
            session: Async SQLAlchemy session
        """
        self.session = session
    
    async def create_instrument(self, instrument: Instrument) -> Instrument:
        """
        Create a new instrument in the database.
        
        Args:
            instrument: Instrument instance to create
            
        Returns:
            Created instrument with updated timestamps
            
        Raises:
            SQLAlchemyError: If database operation fails
        """
        try:
            self.session.add(instrument)
            # FIXED: Removed commit - service layer will handle transaction boundaries
            await self.session.flush()  # Get ID without committing
            await self.session.refresh(instrument)
            
            logger.debug("Created instrument", instrument_token=instrument.instrument_token)
            return instrument
            
        except SQLAlchemyError as e:
            logger.error("Failed to create instrument", instrument_token=instrument.instrument_token, error=str(e))
            raise
    
    async def get_instrument_by_token(self, instrument_token: int) -> Optional[Instrument]:
        """
        Get instrument by token.
        
        Args:
            instrument_token: Instrument token to search for
            
        Returns:
            Instrument if found, None otherwise
        """
        try:
            stmt = select(Instrument).where(Instrument.instrument_token == instrument_token)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
            
        except SQLAlchemyError as e:
            logger.error("Failed to get instrument by token", instrument_token=instrument_token, error=str(e))
            raise
    
    async def get_instruments_by_symbol(self, tradingsymbol: str, exchange: Optional[str] = None) -> List[Instrument]:
        """
        Get instruments by trading symbol and optionally exchange.
        
        Args:
            tradingsymbol: Trading symbol to search for
            exchange: Optional exchange filter
            
        Returns:
            List of matching instruments
        """
        try:
            conditions = [Instrument.tradingsymbol == tradingsymbol]
            if exchange:
                conditions.append(Instrument.exchange == exchange)
            
            stmt = select(Instrument).where(and_(*conditions))
            result = await self.session.execute(stmt)
            return result.scalars().all()
            
        except SQLAlchemyError as e:
            logger.error("Failed to get instruments by symbol", tradingsymbol=tradingsymbol, error=str(e))
            raise
    
    async def get_instruments_by_exchange(self, exchange: str, limit: Optional[int] = None) -> List[Instrument]:
        """
        Get instruments by exchange.
        
        Args:
            exchange: Exchange name
            limit: Optional limit on number of results
            
        Returns:
            List of instruments from the exchange
        """
        try:
            stmt = select(Instrument).where(Instrument.exchange == exchange)
            
            if limit:
                stmt = stmt.limit(limit)
            
            result = await self.session.execute(stmt)
            return result.scalars().all()
            
        except SQLAlchemyError as e:
            logger.error("Failed to get instruments by exchange", exchange=exchange, error=str(e))
            raise
    
    async def update_instrument(self, instrument: Instrument) -> Instrument:
        """
        Update an existing instrument.
        
        Args:
            instrument: Instrument instance with updated data
            
        Returns:
            Updated instrument
            
        Raises:
            SQLAlchemyError: If database operation fails
        """
        try:
            # FIXED: Removed commit - service layer will handle transaction boundaries
            await self.session.flush()
            await self.session.refresh(instrument)
            
            logger.debug("Updated instrument", instrument_token=instrument.instrument_token)
            return instrument
            
        except SQLAlchemyError as e:
            logger.error("Failed to update instrument", instrument_token=instrument.instrument_token, error=str(e))
            raise
    
    async def upsert_instrument(self, instrument_data: Dict[str, Any], source_file: str = None) -> Instrument:
        """
        Insert or update single instrument (upsert operation).
        NOTE: For bulk operations, use bulk_upsert_instruments() which is much more efficient.
        
        Args:
            instrument_data: Dictionary containing instrument data
            source_file: Source file name for tracking
            
        Returns:
            Created or updated instrument
        """
        try:
            instrument_token = instrument_data['instrument_token']
            
            # Check if instrument exists
            existing = await self.get_instrument_by_token(instrument_token)
            
            if existing:
                # Update existing instrument
                for key, value in instrument_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                
                existing.source_file = source_file
                
                # FIXED: Removed commit - service layer will handle transaction boundaries
                await self.session.flush()
                await self.session.refresh(existing)
                
                logger.debug("Updated existing instrument", instrument_token=instrument_token)
                return existing
            else:
                # Create new instrument
                new_instrument = Instrument.from_csv_row(instrument_data, source_file)
                return await self.create_instrument(new_instrument)
                
        except SQLAlchemyError as e:
            logger.error("Failed to upsert instrument", instrument_token=instrument_data.get('instrument_token'), error=str(e))
            raise
    
    async def bulk_upsert_instruments(self, instruments_data: List[Dict[str, Any]], 
                                    source_file: str = None, batch_size: int = 1000) -> int:
        """
        FIXED: Efficient bulk insert or update using single PostgreSQL upsert per batch.
        
        Args:
            instruments_data: List of instrument data dictionaries
            source_file: Source file name for tracking
            batch_size: Number of instruments to process in each batch
            
        Returns:
            Number of instruments processed
        """
        total_processed = 0
        
        try:
            for i in range(0, len(instruments_data), batch_size):
                batch = instruments_data[i:i + batch_size]
                
                if not batch:
                    continue
                
                # Prepare batch data for insert
                batch_values = []
                for instrument_data in batch:
                    try:
                        # Create instrument instance to validate and format data
                        instrument = Instrument.from_csv_row(instrument_data, source_file)
                        batch_values.append({
                            'instrument_token': instrument.instrument_token,
                            'exchange_token': instrument.exchange_token,
                            'tradingsymbol': instrument.tradingsymbol,
                            'name': instrument.name,
                            'exchange': instrument.exchange,
                            'segment': instrument.segment,
                            'instrument_type': instrument.instrument_type,
                            'last_price': instrument.last_price,
                            'tick_size': instrument.tick_size,
                            'lot_size': instrument.lot_size,
                            'expiry': instrument.expiry,
                            'strike': instrument.strike,
                            'is_active': instrument.is_active,
                            'source_file': instrument.source_file
                        })
                    except Exception as e:
                        logger.warning(
                            "Failed to prepare instrument data",
                            instrument_token=instrument_data.get('instrument_token'),
                            error=str(e),
                        )
                        continue
                
                if not batch_values:
                    continue
                
                # Perform single batch upsert using PostgreSQL INSERT ... ON CONFLICT
                stmt = pg_insert(Instrument).values(batch_values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['instrument_token'],
                    set_={
                        'exchange_token': stmt.excluded.exchange_token,
                        'tradingsymbol': stmt.excluded.tradingsymbol,
                        'name': stmt.excluded.name,
                        'exchange': stmt.excluded.exchange,
                        'segment': stmt.excluded.segment,
                        'instrument_type': stmt.excluded.instrument_type,
                        'last_price': stmt.excluded.last_price,
                        'tick_size': stmt.excluded.tick_size,
                        'lot_size': stmt.excluded.lot_size,
                        'expiry': stmt.excluded.expiry,
                        'strike': stmt.excluded.strike,
                        'is_active': stmt.excluded.is_active,
                        'source_file': stmt.excluded.source_file,
                        'updated_at': func.now()
                    }
                )
                
                result = await self.session.execute(stmt)
                processed_count = len(batch_values)
                total_processed += processed_count
                
                logger.info("Processed batch efficiently", 
                          batch_size=processed_count, 
                          total=total_processed)
            
            logger.info("Bulk upsert completed efficiently", total_processed=total_processed)
            return total_processed
            
        except Exception as e:
            logger.error("Bulk upsert failed", error=str(e))
            raise
    
    async def delete_instrument(self, instrument_token: int) -> bool:
        """
        Delete an instrument by token.
        
        Args:
            instrument_token: Token of instrument to delete
            
        Returns:
            True if deleted, False if not found
        """
        try:
            instrument = await self.get_instrument_by_token(instrument_token)
            if instrument:
                await self.session.delete(instrument)
                # FIXED: Removed commit - service layer will handle transaction boundaries
                logger.debug("Deleted instrument", instrument_token=instrument_token)
                return True
            return False
            
        except SQLAlchemyError as e:
            logger.error("Failed to delete instrument", instrument_token=instrument_token, error=str(e))
            raise
    
    async def get_all_instruments(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Instrument]:
        """
        Get all instruments with optional pagination.
        
        Args:
            limit: Maximum number of instruments to return
            offset: Number of instruments to skip
            
        Returns:
            List of instruments
        """
        try:
            stmt = select(Instrument).order_by(Instrument.tradingsymbol)
            
            if offset:
                stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)
            
            result = await self.session.execute(stmt)
            return result.scalars().all()
            
        except SQLAlchemyError as e:
            logger.error("Failed to get all instruments", error=str(e))
            raise
    
    async def count_instruments(self, exchange: Optional[str] = None) -> int:
        """
        Count total number of instruments.
        
        Args:
            exchange: Optional exchange filter
            
        Returns:
            Total count of instruments
        """
        try:
            stmt = select(func.count(Instrument.instrument_token))
            
            if exchange:
                stmt = stmt.where(Instrument.exchange == exchange)
            
            result = await self.session.execute(stmt)
            return result.scalar()
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to count instruments", error=str(e))
            raise
    
    async def search_instruments(self, search_term: str, limit: int = 50) -> List[Instrument]:
        """
        Search instruments by symbol or name.
        
        Args:
            search_term: Term to search for in symbol or name
            limit: Maximum number of results
            
        Returns:
            List of matching instruments
        """
        try:
            search_pattern = f"%{search_term}%"
            stmt = select(Instrument).where(
                or_(
                    Instrument.tradingsymbol.ilike(search_pattern),
                    Instrument.name.ilike(search_pattern)
                )
            ).limit(limit)
            
            result = await self.session.execute(stmt)
            return result.scalars().all()
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to search instruments", error=str(e))
            raise


class InstrumentRegistryRepository:
    """
    Repository for instrument registry operations.
    
    Manages the active instrument registry for market data subscriptions.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.
        
        Args:
            session: Async SQLAlchemy session
        """
        self.session = session
    
    async def add_to_registry(self, instrument_token: int, tradingsymbol: str, 
                             exchange: str, priority: int = 100, 
                             notes: str = None, added_by: str = 'system') -> InstrumentRegistry:
        """
        Add instrument to registry.
        
        Args:
            instrument_token: Instrument token
            tradingsymbol: Trading symbol
            exchange: Exchange name
            priority: Processing priority (lower = higher priority)
            notes: Optional notes
            added_by: Who added this instrument
            
        Returns:
            Created registry entry
        """
        try:
            registry_entry = InstrumentRegistry(
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                priority=priority,
                notes=notes,
                added_by=added_by
            )
            
            self.session.add(registry_entry)
            await self.session.commit()
            await self.session.refresh(registry_entry)
            
            logger.debug(f"Added instrument to registry", instrument_token=instrument_token)
            return registry_entry
            
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to add instrument to registry", instrument_token=instrument_token, error=str(e))
            raise
    
    async def get_subscribed_instruments(self) -> List[InstrumentRegistry]:
        """
        Get all subscribed instruments from registry.
        
        Returns:
            List of subscribed registry entries
        """
        try:
            stmt = select(InstrumentRegistry).where(
                InstrumentRegistry.is_subscribed == True
            ).order_by(InstrumentRegistry.priority, InstrumentRegistry.tradingsymbol)
            
            result = await self.session.execute(stmt)
            return result.scalars().all()
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to get subscribed instruments", error=str(e))
            raise
    
    async def get_registry_tokens(self) -> List[int]:
        """
        Get list of instrument tokens in registry.
        
        Returns:
            List of instrument tokens
        """
        try:
            stmt = select(InstrumentRegistry.instrument_token).where(
                InstrumentRegistry.is_subscribed == True
            )
            
            result = await self.session.execute(stmt)
            return result.scalars().all()
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to get registry tokens", error=str(e))
            raise
    
    async def remove_from_registry(self, instrument_token: int) -> bool:
        """
        Remove instrument from registry.
        
        Args:
            instrument_token: Token of instrument to remove
            
        Returns:
            True if removed, False if not found
        """
        try:
            stmt = select(InstrumentRegistry).where(
                InstrumentRegistry.instrument_token == instrument_token
            )
            result = await self.session.execute(stmt)
            registry_entry = result.scalar_one_or_none()
            
            if registry_entry:
                await self.session.delete(registry_entry)
                await self.session.commit()
                logger.debug(f"Removed instrument from registry", instrument_token=instrument_token)
                return True
            return False
            
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to remove instrument from registry", instrument_token=instrument_token, error=str(e))
            raise
    
    async def update_subscription_status(self, instrument_token: int, is_subscribed: bool) -> bool:
        """
        Update subscription status for an instrument.
        
        Args:
            instrument_token: Instrument token
            is_subscribed: New subscription status
            
        Returns:
            True if updated, False if not found
        """
        try:
            stmt = select(InstrumentRegistry).where(
                InstrumentRegistry.instrument_token == instrument_token
            )
            result = await self.session.execute(stmt)
            registry_entry = result.scalar_one_or_none()
            
            if registry_entry:
                registry_entry.is_subscribed = is_subscribed
                await self.session.commit()
                logger.debug(f"Updated subscription for instrument", 
                           instrument_token=instrument_token, 
                           is_subscribed=is_subscribed)
                return True
            return False
            
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to update subscription", instrument_token=instrument_token, error=str(e))
            raise
