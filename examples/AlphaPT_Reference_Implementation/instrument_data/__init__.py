"""
Instrument Data Module - Enhanced instrument registry and management with smart features.

This module provides:
- PostgreSQL-based instrument storage and management
- Redis caching layer for high-performance lookups
- Smart download scheduling with market awareness
- Target token management for focused processing
- CSV file loading and parsing utilities
- Instrument registry for market data subscriptions
- Database migrations and schema management
- Repository pattern for data access

Enhanced Usage:
    from instrument_data import get_enhanced_instrument_data_manager
    
    # Get enhanced manager with smart features
    manager = await get_enhanced_instrument_data_manager()
    
    # Smart refresh with scheduling awareness
    result = await manager.perform_smart_refresh()
    
    # Fast Redis-cached lookups
    instrument = await manager.get_instrument_by_token(738561)
    
    # Get comprehensive system status
    status = await manager.get_comprehensive_status()

Basic Usage (backward compatibility):
    from instrument_data import get_instrument_registry_service
    
    # Get basic service
    service = await get_instrument_registry_service()
    
    # Load instruments from CSV
    result = await service.load_instruments_from_csv()
    
    # Search instruments
    instruments = await service.search_instruments("RELIANCE")
    
    # Manage registry
    await service.add_to_registry(738561)  # RELIANCE token
    tokens = await service.get_registry_tokens()
"""

# Basic service (backward compatibility)
from .services import (
    InstrumentRegistryService,
    get_instrument_registry_service,
    cleanup_instrument_registry_service
)

# Enhanced manager with smart features
try:
    from .services.enhanced_manager import (
        EnhancedInstrumentDataManager,
        get_enhanced_instrument_data_manager,
        cleanup_enhanced_manager
    )
    ENHANCED_FEATURES_AVAILABLE = True
except ImportError:
    ENHANCED_FEATURES_AVAILABLE = False

# Configuration
try:
    from .config.settings import (
        InstrumentDataConfig,
        get_instrument_data_config,
        validate_config
    )
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

# Enhanced utilities
try:
    from .utils.target_tokens import TargetTokenManager, create_default_target_tokens_file
    TARGET_TOKENS_AVAILABLE = True
except ImportError:
    TARGET_TOKENS_AVAILABLE = False

# Basic components
from .models import Instrument, InstrumentRegistry, Base
from .utils import InstrumentCSVLoader, load_default_instruments, count_default_instruments
from .database import create_instrument_tables, drop_instrument_tables, migrate_instrument_database

__version__ = "2.0.0"

__all__ = [
    # Basic service interface
    'InstrumentRegistryService',
    'get_instrument_registry_service',
    'cleanup_instrument_registry_service',
    
    # Data models
    'Instrument',
    'InstrumentRegistry',
    'Base',
    
    # CSV utilities
    'InstrumentCSVLoader',
    'load_default_instruments',
    'count_default_instruments',
    
    # Database utilities
    'create_instrument_tables',
    'drop_instrument_tables',
    'migrate_instrument_database',
]

# Add enhanced features if available
if ENHANCED_FEATURES_AVAILABLE:
    __all__.extend([
        'EnhancedInstrumentDataManager',
        'get_enhanced_instrument_data_manager',
        'cleanup_enhanced_manager',
    ])

if CONFIG_AVAILABLE:
    __all__.extend([
        'InstrumentDataConfig',
        'get_instrument_data_config',
        'validate_config',
    ])

if TARGET_TOKENS_AVAILABLE:
    __all__.extend([
        'TargetTokenManager',
        'create_default_target_tokens_file',
    ])