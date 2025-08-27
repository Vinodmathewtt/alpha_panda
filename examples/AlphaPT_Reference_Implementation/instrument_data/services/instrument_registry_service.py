"""
Instrument Registry Service - Main service class for instrument data management.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging.logger import get_logger

logger = get_logger(__name__)
from core.database.connection import get_database_manager
from ..models.instrument import Instrument, InstrumentRegistry
from ..repositories.instrument_repository import InstrumentRepository, InstrumentRegistryRepository
from ..utils.csv_loader import InstrumentCSVLoader


class InstrumentRegistryService:
    """
    Main service class for instrument data management.
    
    Provides high-level operations for:
    - Loading instruments from CSV files
    - Managing instrument registry
    - Database operations
    - Market data subscription management
    """
    
    def __init__(self):
        """Initialize the instrument registry service."""
        self._instrument_repo: Optional[InstrumentRepository] = None
        self._registry_repo: Optional[InstrumentRegistryRepository] = None
        self._session: Optional[AsyncSession] = None
    
    async def initialize(self) -> None:
        """Initialize the service with database connection."""
        try:
            db_manager = get_database_manager()
            if not db_manager:
                raise RuntimeError("Database manager not initialized")
            
            self._session = db_manager.get_session()
            self._instrument_repo = InstrumentRepository(self._session)
            self._registry_repo = InstrumentRegistryRepository(self._session)
            
            logger.info("Instrument registry service initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize instrument registry service: {e}")
            raise
    
    async def load_instruments_from_csv(self, csv_file_path: str = None, 
                                      update_registry: bool = True) -> Dict[str, Any]:
        """
        Load instruments from CSV file and optionally update registry.
        
        Args:
            csv_file_path: Path to CSV file (uses default if None)
            update_registry: Whether to update the instrument registry
            
        Returns:
            Dictionary with loading results and statistics
        """
        try:
            # Use default CSV path if not provided
            if csv_file_path is None:
                csv_file_path = InstrumentCSVLoader.get_default_csv_path()
            
            # Validate file exists
            csv_path = Path(csv_file_path)
            if not csv_path.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_file_path}")
            
            # Load instruments from CSV
            loader = InstrumentCSVLoader(csv_file_path)
            instruments_data = loader.load_instruments()
            
            if not instruments_data:
                logger.warning(f"No instruments found in CSV file: {csv_file_path}")
                return {
                    'status': 'success',
                    'total_loaded': 0,
                    'total_inserted': 0,
                    'total_updated': 0,
                    'registry_updated': False,
                    'source_file': csv_path.name
                }
            
            # Bulk upsert instruments
            source_file = csv_path.name
            total_processed = await self._instrument_repo.bulk_upsert_instruments(
                instruments_data, source_file
            )
            
            # Update registry if requested
            registry_updated = False
            if update_registry:
                registry_updated = await self._update_registry_from_csv(instruments_data)
            
            # Get statistics
            total_count = await self._instrument_repo.count_instruments()
            
            result = {
                'status': 'success',
                'total_loaded': len(instruments_data),
                'total_processed': total_processed,
                'total_in_database': total_count,
                'registry_updated': registry_updated,
                'source_file': source_file,
                'loaded_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Successfully loaded {total_processed} instruments from {source_file}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to load instruments from CSV: {e}")
            raise
    
    async def _update_registry_from_csv(self, instruments_data: List[Dict[str, Any]]) -> bool:
        """
        Update instrument registry based on CSV data.
        
        Args:
            instruments_data: List of instrument data from CSV
            
        Returns:
            True if registry was updated successfully
        """
        try:
            # Get current registry tokens
            current_tokens = set(await self._registry_repo.get_registry_tokens())
            
            # Get tokens from CSV data
            csv_tokens = {int(item['instrument_token']) for item in instruments_data}
            
            # Add new instruments to registry
            new_tokens = csv_tokens - current_tokens
            for instrument_data in instruments_data:
                token = int(instrument_data['instrument_token'])
                if token in new_tokens:
                    await self._registry_repo.add_to_registry(
                        instrument_token=token,
                        tradingsymbol=instrument_data['tradingsymbol'],
                        exchange=instrument_data['exchange'],
                        priority=100,
                        notes=f"Added from CSV: {instrument_data.get('name', '')}",
                        added_by='csv_loader'
                    )
            
            logger.info(f"Added {len(new_tokens)} new instruments to registry")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update registry from CSV: {e}")
            return False
    
    async def get_instrument_by_token(self, instrument_token: int) -> Optional[Dict[str, Any]]:
        """
        Get instrument by token.
        
        Args:
            instrument_token: Instrument token to search for
            
        Returns:
            Instrument data as dictionary or None if not found
        """
        try:
            instrument = await self._instrument_repo.get_instrument_by_token(instrument_token)
            return instrument.to_dict() if instrument else None
            
        except Exception as e:
            logger.error(f"Failed to get instrument by token {instrument_token}: {e}")
            raise
    
    async def search_instruments(self, search_term: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search instruments by symbol or name.
        
        Args:
            search_term: Term to search for
            limit: Maximum number of results
            
        Returns:
            List of matching instruments as dictionaries
        """
        try:
            instruments = await self._instrument_repo.search_instruments(search_term, limit)
            return [instrument.to_dict() for instrument in instruments]
            
        except Exception as e:
            logger.error(f"Failed to search instruments: {e}")
            raise
    
    async def get_instruments_by_exchange(self, exchange: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get instruments by exchange.
        
        Args:
            exchange: Exchange name
            limit: Optional limit on results
            
        Returns:
            List of instruments from the exchange
        """
        try:
            instruments = await self._instrument_repo.get_instruments_by_exchange(exchange, limit)
            return [instrument.to_dict() for instrument in instruments]
            
        except Exception as e:
            logger.error(f"Failed to get instruments by exchange {exchange}: {e}")
            raise
    
    async def get_registry_instruments(self) -> List[Dict[str, Any]]:
        """
        Get all instruments in the registry.
        
        Returns:
            List of registry entries as dictionaries
        """
        try:
            registry_entries = await self._registry_repo.get_subscribed_instruments()
            return [entry.to_dict() for entry in registry_entries]
            
        except Exception as e:
            logger.error(f"Failed to get registry instruments: {e}")
            raise
    
    async def get_registry_tokens(self) -> List[int]:
        """
        Get list of instrument tokens in registry.
        
        Returns:
            List of instrument tokens
        """
        try:
            return await self._registry_repo.get_registry_tokens()
            
        except Exception as e:
            logger.error(f"Failed to get registry tokens: {e}")
            raise
    
    async def add_to_registry(self, instrument_token: int, priority: int = 100, 
                             notes: str = None, added_by: str = 'api') -> bool:
        """
        Add instrument to registry.
        
        Args:
            instrument_token: Instrument token to add
            priority: Processing priority
            notes: Optional notes
            added_by: Who added this instrument
            
        Returns:
            True if added successfully
        """
        try:
            # Get instrument details
            instrument = await self._instrument_repo.get_instrument_by_token(instrument_token)
            if not instrument:
                logger.warning(f"Instrument {instrument_token} not found in database")
                return False
            
            # Add to registry
            await self._registry_repo.add_to_registry(
                instrument_token=instrument_token,
                tradingsymbol=instrument.tradingsymbol,
                exchange=instrument.exchange,
                priority=priority,
                notes=notes,
                added_by=added_by
            )
            
            logger.info(f"Added instrument {instrument_token} to registry")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add instrument {instrument_token} to registry: {e}")
            return False
    
    async def remove_from_registry(self, instrument_token: int) -> bool:
        """
        Remove instrument from registry.
        
        Args:
            instrument_token: Instrument token to remove
            
        Returns:
            True if removed successfully
        """
        try:
            success = await self._registry_repo.remove_from_registry(instrument_token)
            if success:
                logger.info(f"Removed instrument {instrument_token} from registry")
            return success
            
        except Exception as e:
            logger.error(f"Failed to remove instrument {instrument_token} from registry: {e}")
            return False
    
    async def update_subscription_status(self, instrument_token: int, is_subscribed: bool) -> bool:
        """
        Update subscription status for an instrument.
        
        Args:
            instrument_token: Instrument token
            is_subscribed: New subscription status
            
        Returns:
            True if updated successfully
        """
        try:
            success = await self._registry_repo.update_subscription_status(
                instrument_token, is_subscribed
            )
            if success:
                status = "subscribed" if is_subscribed else "unsubscribed"
                logger.info(f"Updated instrument {instrument_token} status to {status}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to update subscription status for {instrument_token}: {e}")
            return False
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get instrument registry statistics.
        
        Returns:
            Dictionary containing various statistics
        """
        try:
            # Get total instrument counts
            total_instruments = await self._instrument_repo.count_instruments()
            nse_count = await self._instrument_repo.count_instruments('NSE')
            bse_count = await self._instrument_repo.count_instruments('BSE')
            
            # Get registry counts
            registry_entries = await self._registry_repo.get_subscribed_instruments()
            registry_count = len(registry_entries)
            
            # Get exchange breakdown for registry
            registry_exchanges = {}
            for entry in registry_entries:
                exchange = entry.exchange
                registry_exchanges[exchange] = registry_exchanges.get(exchange, 0) + 1
            
            return {
                'total_instruments': total_instruments,
                'nse_instruments': nse_count,
                'bse_instruments': bse_count,
                'registry_instruments': registry_count,
                'registry_by_exchange': registry_exchanges,
                'updated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            raise
    
    async def refresh_from_default_csv(self) -> Dict[str, Any]:
        """
        Convenience method to refresh from the default CSV file.
        
        Returns:
            Loading results and statistics
        """
        try:
            return await self.load_instruments_from_csv()
            
        except Exception as e:
            logger.error(f"Failed to refresh from default CSV: {e}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        try:
            if self._session:
                await self._session.close()
                
            logger.info("Instrument registry service cleaned up")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Global service instance
_instrument_registry_service: Optional[InstrumentRegistryService] = None


async def get_instrument_registry_service() -> InstrumentRegistryService:
    """
    Get the global instrument registry service instance.
    
    Returns:
        Initialized InstrumentRegistryService instance
    """
    global _instrument_registry_service
    
    if _instrument_registry_service is None:
        _instrument_registry_service = InstrumentRegistryService()
        await _instrument_registry_service.initialize()
    
    return _instrument_registry_service


async def cleanup_instrument_registry_service() -> None:
    """Clean up the global instrument registry service."""
    global _instrument_registry_service
    
    if _instrument_registry_service:
        await _instrument_registry_service.cleanup()
        _instrument_registry_service = None