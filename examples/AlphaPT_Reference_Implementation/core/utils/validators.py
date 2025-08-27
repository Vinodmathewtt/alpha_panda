"""Comprehensive input validation utilities for AlphaPT.

This module provides standardized validation functions and decorators
for validating inputs across the entire application, ensuring data
integrity and security.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union

from pydantic import ValidationError, field_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass

from core.utils.exceptions import ValidationError as AlphaPTValidationError


class ValidationType(Enum):
    """Types of validation available."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    EMAIL = "email"
    UUID = "uuid"
    DATE = "date"
    DATETIME = "datetime"
    ENUM = "enum"
    LIST = "list"
    DICT = "dict"
    TRADING_SYMBOL = "trading_symbol"
    INSTRUMENT_TOKEN = "instrument_token"
    PRICE = "price"
    QUANTITY = "quantity"
    ORDER_TYPE = "order_type"
    EXCHANGE = "exchange"


@dataclass
class ValidationRule:
    """Validation rule definition."""

    field_name: str
    validation_type: ValidationType
    required: bool = True
    min_value: Optional[Union[int, float, Decimal]] = None
    max_value: Optional[Union[int, float, Decimal]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    allowed_values: Optional[List[Any]] = None
    custom_validator: Optional[Callable] = None
    error_message: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validation operation."""

    is_valid: bool
    errors: List[str]
    validated_data: Dict[str, Any]
    field_errors: Dict[str, List[str]]


class InputValidator:
    """Comprehensive input validator with built-in rules for trading data."""

    def __init__(self):
        """Initialize validator with trading-specific patterns."""
        # Trading symbol patterns
        self.trading_symbol_pattern = re.compile(r"^[A-Z0-9&\-]{1,20}$")

        # Exchange patterns
        self.valid_exchanges = {"NSE", "BSE", "NFO", "BFO", "CDS", "MCX"}

        # Order type patterns
        self.valid_order_types = {"MARKET", "LIMIT", "SL", "SL-M"}

        # Transaction types
        self.valid_transaction_types = {"BUY", "SELL"}

        # Product types
        self.valid_product_types = {"CNC", "MIS", "NRML", "CO", "BO"}

        # Validity types
        self.valid_validity_types = {"DAY", "IOC", "GTT"}

        # Email pattern
        self.email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

        # UUID pattern
        self.uuid_pattern = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

    def validate_field(self, value: Any, rule: ValidationRule) -> ValidationResult:
        """Validate a single field against a rule.

        Args:
            value: Value to validate
            rule: Validation rule to apply

        Returns:
            ValidationResult: Validation result
        """
        errors = []
        validated_value = value

        # Check if required
        if rule.required and (value is None or value == ""):
            errors.append(f"{rule.field_name} is required")
            return ValidationResult(
                is_valid=False, errors=errors, validated_data={}, field_errors={rule.field_name: errors}
            )

        # Skip validation if value is None and not required
        if value is None and not rule.required:
            return ValidationResult(is_valid=True, errors=[], validated_data={rule.field_name: None}, field_errors={})

        # Type-specific validation
        try:
            if rule.validation_type == ValidationType.STRING:
                validated_value = self._validate_string(value, rule)
            elif rule.validation_type == ValidationType.INTEGER:
                validated_value = self._validate_integer(value, rule)
            elif rule.validation_type == ValidationType.FLOAT:
                validated_value = self._validate_float(value, rule)
            elif rule.validation_type == ValidationType.DECIMAL:
                validated_value = self._validate_decimal(value, rule)
            elif rule.validation_type == ValidationType.BOOLEAN:
                validated_value = self._validate_boolean(value, rule)
            elif rule.validation_type == ValidationType.EMAIL:
                validated_value = self._validate_email(value, rule)
            elif rule.validation_type == ValidationType.UUID:
                validated_value = self._validate_uuid(value, rule)
            elif rule.validation_type == ValidationType.DATE:
                validated_value = self._validate_date(value, rule)
            elif rule.validation_type == ValidationType.DATETIME:
                validated_value = self._validate_datetime(value, rule)
            elif rule.validation_type == ValidationType.ENUM:
                validated_value = self._validate_enum(value, rule)
            elif rule.validation_type == ValidationType.LIST:
                validated_value = self._validate_list(value, rule)
            elif rule.validation_type == ValidationType.DICT:
                validated_value = self._validate_dict(value, rule)
            elif rule.validation_type == ValidationType.TRADING_SYMBOL:
                validated_value = self._validate_trading_symbol(value, rule)
            elif rule.validation_type == ValidationType.INSTRUMENT_TOKEN:
                validated_value = self._validate_instrument_token(value, rule)
            elif rule.validation_type == ValidationType.PRICE:
                validated_value = self._validate_price(value, rule)
            elif rule.validation_type == ValidationType.QUANTITY:
                validated_value = self._validate_quantity(value, rule)
            elif rule.validation_type == ValidationType.ORDER_TYPE:
                validated_value = self._validate_order_type(value, rule)
            elif rule.validation_type == ValidationType.EXCHANGE:
                validated_value = self._validate_exchange(value, rule)
            else:
                errors.append(f"Unknown validation type: {rule.validation_type}")

        except Exception as e:
            error_msg = rule.error_message or str(e)
            errors.append(f"{rule.field_name}: {error_msg}")

        # Custom validator
        if rule.custom_validator and not errors:
            try:
                validated_value = rule.custom_validator(validated_value)
            except Exception as e:
                error_msg = rule.error_message or str(e)
                errors.append(f"{rule.field_name}: {error_msg}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            validated_data={rule.field_name: validated_value} if not errors else {},
            field_errors={rule.field_name: errors} if errors else {},
        )

    def validate_data(self, data: Dict[str, Any], rules: List[ValidationRule]) -> ValidationResult:
        """Validate multiple fields against rules.

        Args:
            data: Data dictionary to validate
            rules: List of validation rules

        Returns:
            ValidationResult: Combined validation result
        """
        all_errors = []
        validated_data = {}
        field_errors = {}

        for rule in rules:
            value = data.get(rule.field_name)
            result = self.validate_field(value, rule)

            if result.is_valid:
                validated_data.update(result.validated_data)
            else:
                all_errors.extend(result.errors)
                field_errors.update(result.field_errors)

        return ValidationResult(
            is_valid=len(all_errors) == 0, errors=all_errors, validated_data=validated_data, field_errors=field_errors
        )

    def _validate_string(self, value: Any, rule: ValidationRule) -> str:
        """Validate string value."""
        if not isinstance(value, str):
            value = str(value)

        # Length validation
        if rule.min_length is not None and len(value) < rule.min_length:
            raise ValueError(f"must be at least {rule.min_length} characters")

        if rule.max_length is not None and len(value) > rule.max_length:
            raise ValueError(f"must be at most {rule.max_length} characters")

        # Pattern validation
        if rule.pattern and not re.match(rule.pattern, value):
            raise ValueError(f"does not match required pattern")

        # Allowed values
        if rule.allowed_values and value not in rule.allowed_values:
            raise ValueError(f"must be one of: {rule.allowed_values}")

        return value

    def _validate_integer(self, value: Any, rule: ValidationRule) -> int:
        """Validate integer value."""
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            raise ValueError("must be a valid integer")

        # Range validation
        if rule.min_value is not None and int_value < rule.min_value:
            raise ValueError(f"must be at least {rule.min_value}")

        if rule.max_value is not None and int_value > rule.max_value:
            raise ValueError(f"must be at most {rule.max_value}")

        return int_value

    def _validate_float(self, value: Any, rule: ValidationRule) -> float:
        """Validate float value."""
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            raise ValueError("must be a valid number")

        # Range validation
        if rule.min_value is not None and float_value < rule.min_value:
            raise ValueError(f"must be at least {rule.min_value}")

        if rule.max_value is not None and float_value > rule.max_value:
            raise ValueError(f"must be at most {rule.max_value}")

        return float_value

    def _validate_decimal(self, value: Any, rule: ValidationRule) -> Decimal:
        """Validate decimal value."""
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("must be a valid decimal number")

        # Range validation
        if rule.min_value is not None and decimal_value < Decimal(str(rule.min_value)):
            raise ValueError(f"must be at least {rule.min_value}")

        if rule.max_value is not None and decimal_value > Decimal(str(rule.max_value)):
            raise ValueError(f"must be at most {rule.max_value}")

        return decimal_value

    def _validate_boolean(self, value: Any, rule: ValidationRule) -> bool:
        """Validate boolean value."""
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            if value.lower() in ("true", "1", "yes", "on"):
                return True
            elif value.lower() in ("false", "0", "no", "off"):
                return False

        if isinstance(value, (int, float)):
            return bool(value)

        raise ValueError("must be a valid boolean value")

    def _validate_email(self, value: Any, rule: ValidationRule) -> str:
        """Validate email address."""
        if not isinstance(value, str):
            raise ValueError("must be a string")

        if not self.email_pattern.match(value):
            raise ValueError("must be a valid email address")

        return value.lower()

    def _validate_uuid(self, value: Any, rule: ValidationRule) -> str:
        """Validate UUID string."""
        if isinstance(value, uuid.UUID):
            return str(value)

        if not isinstance(value, str):
            raise ValueError("must be a string")

        try:
            uuid.UUID(value)
        except ValueError:
            raise ValueError("must be a valid UUID")

        return value

    def _validate_date(self, value: Any, rule: ValidationRule) -> date:
        """Validate date value."""
        if isinstance(value, date):
            return value

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    raise ValueError("must be a valid date (YYYY-MM-DD)")

        raise ValueError("must be a valid date")

    def _validate_datetime(self, value: Any, rule: ValidationRule) -> datetime:
        """Validate datetime value."""
        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    raise ValueError("must be a valid datetime")

        raise ValueError("must be a valid datetime")

    def _validate_enum(self, value: Any, rule: ValidationRule) -> Any:
        """Validate enum value."""
        if rule.allowed_values and value not in rule.allowed_values:
            raise ValueError(f"must be one of: {rule.allowed_values}")
        return value

    def _validate_list(self, value: Any, rule: ValidationRule) -> List[Any]:
        """Validate list value."""
        if not isinstance(value, list):
            raise ValueError("must be a list")

        # Length validation
        if rule.min_length is not None and len(value) < rule.min_length:
            raise ValueError(f"must contain at least {rule.min_length} items")

        if rule.max_length is not None and len(value) > rule.max_length:
            raise ValueError(f"must contain at most {rule.max_length} items")

        return value

    def _validate_dict(self, value: Any, rule: ValidationRule) -> Dict[str, Any]:
        """Validate dictionary value."""
        if not isinstance(value, dict):
            raise ValueError("must be a dictionary")

        return value

    def _validate_trading_symbol(self, value: Any, rule: ValidationRule) -> str:
        """Validate trading symbol."""
        if not isinstance(value, str):
            raise ValueError("must be a string")

        symbol = value.upper().strip()

        if not self.trading_symbol_pattern.match(symbol):
            raise ValueError("must be a valid trading symbol (alphanumeric, &, -, max 20 chars)")

        return symbol

    def _validate_instrument_token(self, value: Any, rule: ValidationRule) -> int:
        """Validate instrument token."""
        try:
            token = int(value)
        except (ValueError, TypeError):
            raise ValueError("must be a valid integer")

        if token <= 0:
            raise ValueError("must be a positive integer")

        # Zerodha instrument tokens are typically 6-9 digits
        if token < 100000 or token > 999999999:
            raise ValueError("must be a valid instrument token")

        return token

    def _validate_price(self, value: Any, rule: ValidationRule) -> Decimal:
        """Validate price value."""
        try:
            price = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("must be a valid price")

        if price < 0:
            raise ValueError("price cannot be negative")

        # Check decimal places (max 2 for most stocks)
        if price.as_tuple().exponent < -2:
            raise ValueError("price can have at most 2 decimal places")

        return price

    def _validate_quantity(self, value: Any, rule: ValidationRule) -> int:
        """Validate quantity value."""
        try:
            quantity = int(value)
        except (ValueError, TypeError):
            raise ValueError("must be a valid integer")

        if quantity <= 0:
            raise ValueError("quantity must be positive")

        # Check reasonable limits
        if quantity > 1000000:
            raise ValueError("quantity is too large")

        return quantity

    def _validate_order_type(self, value: Any, rule: ValidationRule) -> str:
        """Validate order type."""
        if not isinstance(value, str):
            raise ValueError("must be a string")

        order_type = value.upper().strip()

        if order_type not in self.valid_order_types:
            raise ValueError(f"must be one of: {self.valid_order_types}")

        return order_type

    def _validate_exchange(self, value: Any, rule: ValidationRule) -> str:
        """Validate exchange."""
        if not isinstance(value, str):
            raise ValueError("must be a string")

        exchange = value.upper().strip()

        if exchange not in self.valid_exchanges:
            raise ValueError(f"must be one of: {self.valid_exchanges}")

        return exchange


# Global validator instance
validator = InputValidator()


def validate_trading_order(data: Dict[str, Any]) -> ValidationResult:
    """Validate trading order data.

    Args:
        data: Order data to validate

    Returns:
        ValidationResult: Validation result
    """
    rules = [
        ValidationRule(
            field_name="tradingsymbol",
            validation_type=ValidationType.TRADING_SYMBOL,
            required=True,
            error_message="Trading symbol is required and must be valid",
        ),
        ValidationRule(
            field_name="exchange",
            validation_type=ValidationType.EXCHANGE,
            required=True,
            error_message="Exchange is required and must be valid",
        ),
        ValidationRule(
            field_name="transaction_type",
            validation_type=ValidationType.ENUM,
            required=True,
            allowed_values=["BUY", "SELL"],
            error_message="Transaction type must be BUY or SELL",
        ),
        ValidationRule(
            field_name="order_type",
            validation_type=ValidationType.ORDER_TYPE,
            required=True,
            error_message="Order type is required and must be valid",
        ),
        ValidationRule(
            field_name="quantity",
            validation_type=ValidationType.QUANTITY,
            required=True,
            min_value=1,
            max_value=1000000,
            error_message="Quantity must be a positive integer",
        ),
        ValidationRule(
            field_name="price",
            validation_type=ValidationType.PRICE,
            required=False,  # Not required for MARKET orders
            min_value=0,
            error_message="Price must be a positive decimal",
        ),
        ValidationRule(
            field_name="trigger_price",
            validation_type=ValidationType.PRICE,
            required=False,
            min_value=0,
            error_message="Trigger price must be a positive decimal",
        ),
        ValidationRule(
            field_name="product",
            validation_type=ValidationType.ENUM,
            required=False,
            allowed_values=["CNC", "MIS", "NRML", "CO", "BO"],
            error_message="Product must be a valid product type",
        ),
        ValidationRule(
            field_name="validity",
            validation_type=ValidationType.ENUM,
            required=False,
            allowed_values=["DAY", "IOC", "GTT"],
            error_message="Validity must be a valid validity type",
        ),
    ]

    return validator.validate_data(data, rules)


def validate_market_data(data: Dict[str, Any]) -> ValidationResult:
    """Validate market data.

    Args:
        data: Market data to validate

    Returns:
        ValidationResult: Validation result
    """
    rules = [
        ValidationRule(
            field_name="instrument_token",
            validation_type=ValidationType.INSTRUMENT_TOKEN,
            required=True,
            error_message="Instrument token is required and must be valid",
        ),
        ValidationRule(
            field_name="last_price",
            validation_type=ValidationType.PRICE,
            required=True,
            min_value=0,
            error_message="Last price is required and must be positive",
        ),
        ValidationRule(
            field_name="volume",
            validation_type=ValidationType.INTEGER,
            required=False,
            min_value=0,
            error_message="Volume must be non-negative",
        ),
        ValidationRule(
            field_name="timestamp",
            validation_type=ValidationType.DATETIME,
            required=False,
            error_message="Timestamp must be a valid datetime",
        ),
    ]

    return validator.validate_data(data, rules)


def validate_with_rules(rules: List[ValidationRule]):
    """Decorator for validating function arguments with custom rules.

    Args:
        rules: List of validation rules to apply
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            # Combine args and kwargs into data dict
            import inspect

            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            data = dict(bound_args.arguments)

            # Validate data
            result = validator.validate_data(data, rules)

            if not result.is_valid:
                raise AlphaPTValidationError(f"Validation failed: {', '.join(result.errors)}")

            # Update arguments with validated data
            validated_kwargs = {**kwargs, **result.validated_data}

            return func(*args, **validated_kwargs)

        return wrapper

    return decorator
