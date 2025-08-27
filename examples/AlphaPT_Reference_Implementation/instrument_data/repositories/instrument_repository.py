"""
Repository pattern for instrument data database operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, desc, asc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

from core.logging.logger import get_logger

logger = get_logger(__name__)
from ..models.instrument import Instrument, InstrumentRegistry


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
            await self.session.commit()
            await self.session.refresh(instrument)
            
            logger.debug(f"Created instrument: {instrument.instrument_token}")
            return instrument
            
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to create instrument {instrument.instrument_token}: {e}")
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
            logger.error(f"Failed to get instrument by token {instrument_token}: {e}")
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
            logger.error(f"Failed to get instruments by symbol {tradingsymbol}: {e}")
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
            logger.error(f"Failed to get instruments by exchange {exchange}: {e}")
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
            instrument.updated_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(instrument)
            
            logger.debug(f"Updated instrument: {instrument.instrument_token}")
            return instrument
            
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to update instrument {instrument.instrument_token}: {e}")
            raise
    
    async def upsert_instrument(self, instrument_data: Dict[str, Any], source_file: str = None) -> Instrument:
        """
        Insert or update instrument (upsert operation).
        
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
                
                existing.updated_at = datetime.utcnow()
                existing.source_file = source_file
                
                await self.session.commit()
                await self.session.refresh(existing)
                
                logger.debug(f"Updated existing instrument: {instrument_token}")
                return existing
            else:
                # Create new instrument
                new_instrument = Instrument.from_csv_row(instrument_data, source_file)
                return await self.create_instrument(new_instrument)
                
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to upsert instrument {instrument_data.get('instrument_token')}: {e}")
            raise
    
    async def bulk_upsert_instruments(self, instruments_data: List[Dict[str, Any]], 
                                    source_file: str = None, batch_size: int = 1000) -> int:
        """
        Bulk insert or update instruments for efficient loading.
        
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
                
                for instrument_data in batch:
                    try:
                        await self.upsert_instrument(instrument_data, source_file)
                        total_processed += 1
                    except Exception as e:
                        logger.warning(f"Failed to process instrument {instrument_data.get('instrument_token')}: {e}")
                        continue
                
                # Commit batch
                await self.session.commit()
                logger.info(f"Processed batch of {len(batch)} instruments (total: {total_processed})")
            
            logger.info(f"Bulk upsert completed: {total_processed} instruments processed")
            return total_processed
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Bulk upsert failed: {e}")
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
                await self.session.commit()
                logger.debug(f"Deleted instrument: {instrument_token}")
                return True
            return False
            
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to delete instrument {instrument_token}: {e}")
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
            logger.error(f"Failed to get all instruments: {e}")
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
            logger.error(f"Failed to count instruments: {e}")
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
            logger.error(f"Failed to search instruments: {e}")
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
            
            logger.debug(f"Added instrument {instrument_token} to registry")
            return registry_entry
            
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to add instrument {instrument_token} to registry: {e}")
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
            logger.error(f"Failed to get subscribed instruments: {e}")
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
            logger.error(f"Failed to get registry tokens: {e}")
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
                logger.debug(f"Removed instrument {instrument_token} from registry")
                return True
            return False
            
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to remove instrument {instrument_token} from registry: {e}")
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
                logger.debug(f"Updated subscription for {instrument_token}: {is_subscribed}")
                return True
            return False
            
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Failed to update subscription for {instrument_token}: {e}")
            raise