"""
Instrument Registry Service - Main service class for instrument data management.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from sqlalchemy.ext.asyncio import AsyncSession
import logging

import structlog

logger = structlog.get_logger(__name__)
from .instrument import Instrument, InstrumentRegistry
from .instrument_repository import InstrumentRepository, InstrumentRegistryRepository
from .csv_loader import InstrumentCSVLoader


class InstrumentRegistryService:
    """
    Main service class for instrument data management.
    
    Provides high-level operations for:
    - Loading instruments from CSV files
    - Managing instrument registry
    - Database operations
    - Market data subscription management
    """
    
    def __init__(self, session_factory, csv_file_path: Optional[str] = None):
        """Initialize the instrument registry service."""
        self._session_factory = session_factory
        self.csv_file_path = csv_file_path or "services/market_feed/instruments.csv"
        self.logger = logging.getLogger(__name__)
        self._instrument_repo: Optional[InstrumentRepository] = None
        self._registry_repo: Optional[InstrumentRegistryRepository] = None
    
    async def start(self):
        """Initialize instrument registry service"""
        self.logger.info("Starting Instrument Registry Service...")
        try:
            # Ensure database tables exist
            await self._ensure_tables_exist()
            
            # Load instruments from CSV if database is empty
            instrument_count = await self._get_instrument_count()
            if instrument_count == 0:
                self.logger.info("No instruments found in database, loading from CSV...")
                await self.load_instruments_from_csv(self.csv_file_path)
            else:
                self.logger.info(f"Found {instrument_count} instruments in database")
            
            self.logger.info("✅ Instrument Registry Service started successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to start Instrument Registry Service: {e}")
            raise

    async def stop(self):
        """Cleanup instrument registry service"""
        self.logger.info("Stopping Instrument Registry Service...")
        try:
            # Clear any cached data
            if hasattr(self, '_instrument_cache'):
                self._instrument_cache.clear()
            
            # Close any open connections or resources
            # (Currently no persistent connections to close)
            
            self.logger.info("✅ Instrument Registry Service stopped successfully")
        except Exception as e:
            self.logger.error(f"❌ Error stopping Instrument Registry Service: {e}")
            # Don't raise during shutdown - just log

    async def _ensure_tables_exist(self):
        """Ensure required database tables exist"""
        try:
            # This will be handled by the database manager's initialization
            # Just verify we can access the database
            session_context = self._session_factory()
            session = await session_context.__aenter__()
            try:
                # Simple query to verify database connectivity
                result = await session.execute("SELECT 1")
                result.fetchone()
            finally:
                await session_context.__aexit__(None, None, None)
        except Exception as e:
            raise RuntimeError(f"Cannot access database for instrument registry: {e}")

    async def _get_instrument_count(self) -> int:
        """Get total number of instruments in database"""
        try:
            session_context = self._session_factory()
            session = await session_context.__aenter__()
            try:
                result = await session.execute("SELECT COUNT(*) FROM instruments")
                return result.scalar() or 0
            finally:
                await session_context.__aexit__(None, None, None)
        except Exception:
            # Table might not exist yet - return 0
            return 0

    async def _get_repositories(self):
        """Get repository instances with a fresh session."""
        session_context = self._session_factory()
        session = await session_context.__aenter__()
        
        instrument_repo = InstrumentRepository(session)
        registry_repo = InstrumentRegistryRepository(session)
        
        return session, session_context, instrument_repo, registry_repo
    
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
        session = None
        session_context = None
        
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
                logger.warning(f"No instruments found in CSV file", csv_file=csv_file_path)
                return {
                    'status': 'success',
                    'total_loaded': 0,
                    'total_inserted': 0,
                    'total_updated': 0,
                    'registry_updated': False,
                    'source_file': csv_path.name
                }
            
            # Get repositories with session
            session, session_context, instrument_repo, registry_repo = await self._get_repositories()
            
            # CRITICAL FIX: Wrap entire operation in transaction
            try:
                # Bulk upsert instruments
                source_file = csv_path.name
                total_processed = await instrument_repo.bulk_upsert_instruments(
                    instruments_data, source_file
                )
                
                # Update registry if requested
                registry_updated = False
                if update_registry:
                    registry_updated = await self._update_registry_from_csv(
                        instruments_data, registry_repo
                    )
                    
                    # CRITICAL FIX: Check if registry update failed and rollback
                    if not registry_updated:
                        await session.rollback()
                        raise RuntimeError("Failed to update instrument registry - transaction rolled back")
                
                # Commit the transaction only if everything succeeded
                await session.commit()
                
                # Get statistics after successful commit
                total_count = await instrument_repo.count_instruments()
                
                result = {
                    'status': 'success',
                    'total_loaded': len(instruments_data),
                    'total_processed': total_processed,
                    'total_in_database': total_count,
                    'registry_updated': registry_updated,
                    'source_file': source_file,
                    'loaded_at': datetime.utcnow().isoformat()
                }
                
                logger.info(f"Successfully loaded instruments from CSV", 
                           total_processed=total_processed, 
                           source_file=source_file)
                return result
                
            except Exception as tx_error:
                # Rollback transaction on any error
                if session:
                    await session.rollback()
                logger.error(f"Transaction failed, rolled back: {tx_error}")
                raise
            
        except Exception as e:
            logger.error(f"Failed to load instruments from CSV", error=str(e))
            raise
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
    async def _update_registry_from_csv(self, instruments_data: List[Dict[str, Any]], 
                                      registry_repo: InstrumentRegistryRepository) -> bool:
        """
        Update instrument registry based on CSV data.
        
        Args:
            instruments_data: List of instrument data from CSV
            registry_repo: Registry repository instance
            
        Returns:
            True if registry was updated successfully
            
        Raises:
            Exception: Re-raises any exceptions for proper transaction handling
        """
        # CRITICAL FIX: Don't swallow exceptions - let them propagate for transaction rollback
        # Get current registry tokens
        current_tokens = set(await registry_repo.get_registry_tokens())
        
        # Get tokens from CSV data
        csv_tokens = {int(item['instrument_token']) for item in instruments_data}
        
        # Add new instruments to registry
        new_tokens = csv_tokens - current_tokens
        for instrument_data in instruments_data:
            token = int(instrument_data['instrument_token'])
            if token in new_tokens:
                await registry_repo.add_to_registry(
                    instrument_token=token,
                    tradingsymbol=instrument_data['tradingsymbol'],
                    exchange=instrument_data['exchange'],
                    priority=100,
                    notes=f"Added from CSV: {instrument_data.get('name', '')}",
                    added_by='csv_loader'
                )
        
        logger.info(f"Added new instruments to registry", count=len(new_tokens))
        return True
    
    async def get_instrument_by_token(self, instrument_token: int) -> Optional[Dict[str, Any]]:
        """
        Get instrument by token.
        
        Args:
            instrument_token: Instrument token to search for
            
        Returns:
            Instrument data as dictionary or None if not found
        """
        session_context = None
        
        try:
            session, session_context, instrument_repo, _ = await self._get_repositories()
            instrument = await instrument_repo.get_instrument_by_token(instrument_token)
            return instrument.to_dict() if instrument else None
            
        except Exception as e:
            logger.error(f"Failed to get instrument by token", 
                        instrument_token=instrument_token, 
                        error=str(e))
            raise
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
    async def search_instruments(self, search_term: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search instruments by symbol or name.
        
        Args:
            search_term: Term to search for
            limit: Maximum number of results
            
        Returns:
            List of matching instruments as dictionaries
        """
        session_context = None
        
        try:
            session, session_context, instrument_repo, _ = await self._get_repositories()
            instruments = await instrument_repo.search_instruments(search_term, limit)
            return [instrument.to_dict() for instrument in instruments]
            
        except Exception as e:
            logger.error(f"Failed to search instruments", error=str(e))
            raise
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
    async def get_instruments_by_exchange(self, exchange: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get instruments by exchange.
        
        Args:
            exchange: Exchange name
            limit: Optional limit on results
            
        Returns:
            List of instruments from the exchange
        """
        session_context = None
        
        try:
            session, session_context, instrument_repo, _ = await self._get_repositories()
            instruments = await instrument_repo.get_instruments_by_exchange(exchange, limit)
            return [instrument.to_dict() for instrument in instruments]
            
        except Exception as e:
            logger.error(f"Failed to get instruments by exchange", 
                        exchange=exchange, 
                        error=str(e))
            raise
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
    async def get_registry_instruments(self) -> List[Dict[str, Any]]:
        """
        Get all instruments in the registry.
        
        Returns:
            List of registry entries as dictionaries
        """
        session_context = None
        
        try:
            session, session_context, _, registry_repo = await self._get_repositories()
            registry_entries = await registry_repo.get_subscribed_instruments()
            return [entry.to_dict() for entry in registry_entries]
            
        except Exception as e:
            logger.error(f"Failed to get registry instruments", error=str(e))
            raise
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
    async def get_registry_tokens(self) -> List[int]:
        """
        Get list of instrument tokens in registry.
        
        Returns:
            List of instrument tokens
        """
        session_context = None
        
        try:
            session, session_context, _, registry_repo = await self._get_repositories()
            return await registry_repo.get_registry_tokens()
            
        except Exception as e:
            logger.error(f"Failed to get registry tokens", error=str(e))
            raise
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
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
        session_context = None
        
        try:
            session, session_context, instrument_repo, registry_repo = await self._get_repositories()
            
            # Get instrument details
            instrument = await instrument_repo.get_instrument_by_token(instrument_token)
            if not instrument:
                logger.warning(f"Instrument not found in database", instrument_token=instrument_token)
                return False
            
            # Add to registry
            await registry_repo.add_to_registry(
                instrument_token=instrument_token,
                tradingsymbol=instrument.tradingsymbol,
                exchange=instrument.exchange,
                priority=priority,
                notes=notes,
                added_by=added_by
            )
            
            logger.info(f"Added instrument to registry", instrument_token=instrument_token)
            return True
            
        except Exception as e:
            logger.error(f"Failed to add instrument to registry", 
                        instrument_token=instrument_token, 
                        error=str(e))
            return False
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
    async def remove_from_registry(self, instrument_token: int) -> bool:
        """
        Remove instrument from registry.
        
        Args:
            instrument_token: Instrument token to remove
            
        Returns:
            True if removed successfully
        """
        session_context = None
        
        try:
            session, session_context, _, registry_repo = await self._get_repositories()
            success = await registry_repo.remove_from_registry(instrument_token)
            if success:
                logger.info(f"Removed instrument from registry", instrument_token=instrument_token)
            return success
            
        except Exception as e:
            logger.error(f"Failed to remove instrument from registry", 
                        instrument_token=instrument_token, 
                        error=str(e))
            return False
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
    async def update_subscription_status(self, instrument_token: int, is_subscribed: bool) -> bool:
        """
        Update subscription status for an instrument.
        
        Args:
            instrument_token: Instrument token
            is_subscribed: New subscription status
            
        Returns:
            True if updated successfully
        """
        session_context = None
        
        try:
            session, session_context, _, registry_repo = await self._get_repositories()
            success = await registry_repo.update_subscription_status(
                instrument_token, is_subscribed
            )
            if success:
                status = "subscribed" if is_subscribed else "unsubscribed"
                logger.info(f"Updated instrument status", 
                           instrument_token=instrument_token, 
                           status=status)
            return success
            
        except Exception as e:
            logger.error(f"Failed to update subscription status", 
                        instrument_token=instrument_token, 
                        error=str(e))
            return False
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get instrument registry statistics.
        
        Returns:
            Dictionary containing various statistics
        """
        session_context = None
        
        try:
            session, session_context, instrument_repo, registry_repo = await self._get_repositories()
            
            # Get total instrument counts
            total_instruments = await instrument_repo.count_instruments()
            nse_count = await instrument_repo.count_instruments('NSE')
            bse_count = await instrument_repo.count_instruments('BSE')
            
            # Get registry counts
            registry_entries = await registry_repo.get_subscribed_instruments()
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
            logger.error(f"Failed to get statistics", error=str(e))
            raise
        finally:
            if session_context:
                await session_context.__aexit__(None, None, None)
    
    async def refresh_from_default_csv(self) -> Dict[str, Any]:
        """
        Convenience method to refresh from the default CSV file.
        
        Returns:
            Loading results and statistics
        """
        try:
            return await self.load_instruments_from_csv()
            
        except Exception as e:
            logger.error(f"Failed to refresh from default CSV", error=str(e))
            raise