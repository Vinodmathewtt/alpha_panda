# API Schemas

## Overview

The API schemas module defines Pydantic models for request and response validation in the Alpha Panda REST API. These schemas ensure type safety, automatic validation, and consistent API documentation generation.

## Components

### `responses.py`
Standard response models and data transfer objects:

- **BaseResponse**: Base response model with common fields (success, message, timestamp)
- **DataResponse**: Response model for data-containing responses
- **ErrorResponse**: Standardized error response model
- **Portfolio Models**: Portfolio summary and position response models
- **Monitoring Models**: Health check and metrics response models
- **Authentication Models**: Login, user, and token response models

## Schema Categories

### Base Response Models
```python
class BaseResponse(BaseModel):
    success: bool
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)

class DataResponse(BaseResponse, Generic[T]):
    data: T

class ErrorResponse(BaseResponse):
    error: ErrorDetail
    success: bool = False
```

### Authentication Schemas
```python
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user_info: UserInfo

class UserInfo(BaseModel):
    id: str
    username: str
    roles: List[str]
```

### Portfolio Schemas
```python
class PortfolioSummary(BaseModel):
    broker: str
    total_value: Decimal
    cash_balance: Decimal
    positions_count: int
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    last_updated: datetime

class Position(BaseModel):
    instrument_token: int
    symbol: str
    quantity: int
    average_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    side: str
```

### Monitoring Schemas
```python
class HealthStatus(BaseModel):
    service: str
    status: str  # healthy, degraded, unhealthy
    uptime: int
    last_check: datetime
    details: Dict[str, Any]

class SystemMetrics(BaseModel):
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    active_connections: int
    message_throughput: int
    error_rate: float
```

### System Configuration Schemas
```python
class BrokerConfig(BaseModel):
    name: str
    enabled: bool
    connection_status: str
    last_heartbeat: datetime

class SystemInfo(BaseModel):
    version: str
    uptime: int
    active_brokers: List[str]
    services_status: Dict[str, str]
    configuration_hash: str
```

## Usage

### Request Validation
```python
from api.schemas.responses import LoginRequest
from fastapi import HTTPException

@router.post("/login")
async def login(request: LoginRequest):
    # FastAPI automatically validates request against schema
    if not request.username or not request.password:
        # This validation happens automatically
        pass
    
    return await auth_service.authenticate(request.username, request.password)
```

### Response Serialization
```python
from api.schemas.responses import DataResponse, PortfolioSummary

@router.get("/portfolios/{broker}/summary", response_model=DataResponse[PortfolioSummary])
async def get_portfolio_summary(broker: str) -> DataResponse[PortfolioSummary]:
    portfolio = await portfolio_service.get_summary(broker)
    
    return DataResponse(
        success=True,
        message="Portfolio summary retrieved",
        data=portfolio
    )
```

### Error Handling with Schemas
```python
from api.schemas.responses import ErrorResponse
from fastapi import HTTPException

@router.get("/data")
async def get_data():
    try:
        data = await service.get_data()
        return DataResponse(success=True, data=data)
    except ServiceError as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                success=False,
                message="Service error occurred",
                error={"code": "SERVICE_ERROR", "details": str(e)}
            ).dict()
        )
```

## Validation Features

### Field Validation
```python
class TradeRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: int = Field(..., gt=0, le=10000)
    price: Decimal = Field(..., gt=0, decimal_places=2)
    broker: str = Field(..., regex="^(paper|zerodha)$")
    
    @validator('symbol')
    def symbol_must_be_uppercase(cls, v):
        return v.upper()
```

### Custom Validators
```python
from pydantic import validator, root_validator

class OrderRequest(BaseModel):
    instrument_token: int
    quantity: int
    price: Optional[Decimal] = None
    order_type: str  # market, limit
    
    @root_validator
    def validate_price_for_limit_orders(cls, values):
        if values.get('order_type') == 'limit' and not values.get('price'):
            raise ValueError('Price is required for limit orders')
        return values
```

## Architecture Patterns

- **Type Safety**: Full type validation for all API inputs and outputs
- **Generic Responses**: Reusable response models with generics
- **Consistent Structure**: Standardized response format across all endpoints
- **Automatic Documentation**: Schemas automatically generate OpenAPI documentation
- **Error Standardization**: Consistent error response format
- **Validation Rules**: Business rule validation at schema level

## Configuration

Schema configuration through settings:

```python
class APISchemaSettings(BaseModel):
    max_string_length: int = 1000
    max_array_length: int = 100
    decimal_places: int = 8
    date_format: str = "%Y-%m-%dT%H:%M:%S.%fZ"
```

## Best Practices

1. **Explicit Field Definitions**: Always specify field types and constraints
2. **Meaningful Names**: Use clear, descriptive field names
3. **Documentation**: Include field descriptions and examples
4. **Validation**: Implement appropriate validation rules
5. **Consistency**: Use consistent naming and structure patterns
6. **Versioning**: Plan for schema evolution and versioning

## Dependencies

- **Pydantic**: Data validation and serialization framework
- **FastAPI**: Integration with FastAPI for automatic validation
- **typing**: Type hints and generic types
- **decimal**: High-precision decimal handling for financial data
- **datetime**: Date and time handling with timezone support