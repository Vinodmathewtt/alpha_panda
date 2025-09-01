# Instrument Data Service

## Overview

The Instrument Data Service manages financial instrument metadata, including instrument definitions, registry management, and market data subscription coordination. It provides centralized instrument data management for all Alpha Panda services.

## Architecture

The service follows a layered architecture with repository pattern:
- **Service Layer**: High-level instrument operations and lifecycle management
- **Registry Layer**: In-memory instrument registry with fast lookups
- **Repository Layer**: Database persistence and data access
- **CSV Loader**: Instrument data loading from external sources

## Components

### `instrument_registry_service.py`
Main service class for instrument data management:

- **InstrumentRegistryService**: Primary service with lifecycle management
- **Registry Operations**: Load, update, and manage instrument registry
- **Database Integration**: Persist and retrieve instrument data
- **Market Data Coordination**: Manage instrument subscriptions
- **Health Monitoring**: Service health checks and status reporting

### `instrument.py`
Core instrument data models and registry:

- **Instrument**: Pydantic model for instrument data
- **InstrumentRegistry**: In-memory registry for fast instrument lookups
- **Instrument Validation**: Data validation and consistency checking
- **Registry Operations**: Add, update, remove instruments from registry

### `instrument_repository.py`
Database persistence layer:

- **InstrumentRepository**: Database operations for instrument data
- **InstrumentRegistryRepository**: Registry metadata persistence
- **Query Operations**: Complex instrument queries and filtering
- **Batch Operations**: Efficient bulk instrument operations

### `csv_loader.py`
CSV data loading and parsing:

- **InstrumentCSVLoader**: Load instruments from CSV files
- **Data Parsing**: Parse and validate CSV instrument data
- **Format Support**: Support for multiple CSV formats (Zerodha, NSE, BSE)
- **Error Handling**: Robust error handling for malformed data

### `__init__.py`
Service exports and initialization utilities.

## Key Features

- **Fast Instrument Lookup**: In-memory registry for O(1) instrument lookups
- **Multiple Data Sources**: Support for CSV files from different exchanges
- **Database Persistence**: Reliable instrument data storage and retrieval
- **Registry Management**: Dynamic instrument registry updates
- **Market Data Integration**: Coordinate instrument subscriptions
- **Validation**: Comprehensive instrument data validation
- **Health Monitoring**: Service health checks and monitoring

## Usage

### Service Initialization
```python
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from core.database.connection import DatabaseManager

# Initialize instrument service
db_manager = DatabaseManager(settings.database.postgres_url)
instrument_service = InstrumentRegistryService(db_manager)

# Start service and load data
await instrument_service.start()
```

### Instrument Registry Operations
```python
# Load instruments from CSV
csv_path = Path("data/instruments.csv")
loaded_count = await instrument_service.load_instruments_from_csv(csv_path)
print(f"Loaded {loaded_count} instruments")

# Get instrument by token
instrument = await instrument_service.get_instrument_by_token(256265)
if instrument:
    print(f"Found: {instrument.tradingsymbol}")

# Search instruments by symbol
instruments = await instrument_service.search_instruments("RELIANCE")
for inst in instruments:
    print(f"{inst.tradingsymbol}: {inst.name}")
```

### Registry Management
```python
from services.instrument_data.instrument import InstrumentRegistry

# Get registry instance
registry = instrument_service.get_registry()

# Fast lookups
instrument = registry.get_by_token(256265)
instruments_by_exchange = registry.get_by_exchange("NSE")

# Registry statistics
stats = registry.get_statistics()
print(f"Total instruments: {stats['total_count']}")
print(f"Exchange breakdown: {stats['by_exchange']}")
```

## Data Models

### Instrument Model
```python
class Instrument(BaseModel):
    instrument_token: int = Field(..., description="Unique instrument identifier")
    exchange_token: int = Field(..., description="Exchange-specific token")
    tradingsymbol: str = Field(..., description="Trading symbol")
    name: str = Field(..., description="Full instrument name")
    last_price: Decimal = Field(default=Decimal('0'), description="Last traded price")
    expiry: Optional[date] = Field(None, description="Expiry date for derivatives")
    strike: Optional[Decimal] = Field(None, description="Strike price for options")
    tick_size: Decimal = Field(default=Decimal('0.05'), description="Minimum price movement")
    lot_size: int = Field(default=1, description="Minimum trading quantity")
    instrument_type: str = Field(..., description="Type (EQ, FUT, CE, PE)")
    segment: str = Field(..., description="Market segment (NSE, BSE, etc.)")
    exchange: str = Field(..., description="Exchange name")
```

### Instrument Registry
```python
# Fast instrument lookups
registry = InstrumentRegistry()

# Add instruments
registry.add_instrument(instrument)

# Lookup methods
instrument = registry.get_by_token(256265)
instruments = registry.get_by_tradingsymbol("RELIANCE")
equity_instruments = registry.get_by_type("EQ")
nse_instruments = registry.get_by_exchange("NSE")
```

## CSV Data Loading

### Supported CSV Formats
- **Zerodha Format**: Standard Zerodha instruments.csv format
- **NSE Format**: NSE instruments CSV with specific columns
- **BSE Format**: BSE instruments data format
- **Custom Format**: Configurable column mapping

### CSV Loading Process
```python
# Load from Zerodha CSV
csv_loader = InstrumentCSVLoader()
instruments = await csv_loader.load_from_csv(
    csv_path="data/instruments.csv",
    format="zerodha"
)

# Load with custom column mapping
column_mapping = {
    "instrument_token": "token",
    "tradingsymbol": "symbol", 
    "name": "company_name"
}
instruments = await csv_loader.load_with_mapping(csv_path, column_mapping)
```

### Data Validation
```python
# Validation during loading
try:
    instruments = await csv_loader.load_from_csv(csv_path)
    print(f"Successfully loaded {len(instruments)} instruments")
except ValidationError as e:
    print(f"Validation failed: {e}")
    # Handle validation errors
```

## Database Operations

### Instrument Persistence
```python
# Save instruments to database
await instrument_service.save_instruments_to_database(instruments)

# Load instruments from database
instruments = await instrument_service.load_instruments_from_database()

# Update specific instrument
await instrument_service.update_instrument(instrument_token, updated_data)
```

### Batch Operations
```python
# Batch insert for performance
instrument_batch = [instrument1, instrument2, instrument3]
await instrument_service.batch_insert_instruments(instrument_batch)

# Batch update
updates = [
    {"instrument_token": 256265, "last_price": Decimal("2500.50")},
    {"instrument_token": 408065, "last_price": Decimal("3200.75")}
]
await instrument_service.batch_update_instruments(updates)
```

## Market Data Integration

### Subscription Management
```python
# Get instruments for strategy
strategy_instruments = await instrument_service.get_instruments_for_strategy("momentum_v1")

# Subscribe to market data
subscription_tokens = [inst.instrument_token for inst in strategy_instruments]
await market_feed_service.subscribe_to_instruments(subscription_tokens)

# Get subscription list
active_subscriptions = await instrument_service.get_active_subscriptions()
```

### Instrument Filtering
```python
# Filter instruments by criteria
equity_instruments = await instrument_service.filter_instruments(
    instrument_type="EQ",
    exchange="NSE",
    min_last_price=100.0
)

# Filter by market cap or volume
liquid_instruments = await instrument_service.get_liquid_instruments(
    min_volume=1000000
)
```

## Health Monitoring

### Service Health Checks
```python
# Service health check
health = await instrument_service.health_check()

# Sample health response
{
    "status": "healthy",
    "registry_size": 50000,
    "last_update": "2024-08-30T12:00:00Z",
    "data_sources": {
        "csv": "loaded",
        "database": "connected"
    },
    "validation_errors": 0
}
```

### Performance Metrics
- **Registry Size**: Number of instruments in registry
- **Lookup Performance**: Instrument lookup response times
- **Update Frequency**: Registry update frequency and success rate
- **Data Quality**: Validation error rates and data completeness

## Configuration

Instrument service configuration:

```python
class InstrumentSettings(BaseModel):
    csv_data_path: str = "data/instruments.csv"
    auto_load_on_startup: bool = True
    update_interval_hours: int = 24
    validation_enabled: bool = True
    registry_cache_size: int = 100000
```

## Error Handling

### Instrument Data Errors
```python
try:
    await instrument_service.load_instruments_from_csv(csv_path)
except FileNotFoundError:
    # Handle missing CSV file
    logger.error("Instrument CSV file not found")
except ValidationError as e:
    # Handle data validation errors
    logger.error(f"Instrument validation failed: {e}")
except DatabaseError as e:
    # Handle database errors
    logger.error(f"Database operation failed: {e}")
```

## Performance Optimization

### Registry Performance
- **In-Memory Storage**: Fast O(1) lookups for instrument data
- **Index Creation**: Multiple indices for different lookup patterns
- **Batch Operations**: Efficient bulk data operations
- **Lazy Loading**: Load instrument data on demand

### Database Performance
- **Connection Pooling**: Efficient database connection management
- **Prepared Statements**: Optimized query execution
- **Batch Inserts**: Bulk data insertion for performance
- **Query Optimization**: Indexed queries for fast retrieval

## Best Practices

1. **Registry Initialization**: Always initialize registry before using services
2. **Data Validation**: Validate instrument data at ingestion time
3. **Regular Updates**: Keep instrument data current with regular updates
4. **Error Handling**: Handle data loading and validation errors gracefully
5. **Performance**: Use batch operations for large data sets
6. **Monitoring**: Monitor registry health and data quality

## Dependencies

- **core.database**: Database persistence and connection management
- **pydantic**: Data validation and model management
- **sqlalchemy**: ORM for database operations
- **pandas**: CSV data processing and manipulation
- **asyncio**: Async service operations