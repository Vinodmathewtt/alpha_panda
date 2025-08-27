"""Basic input sanitization utilities for API endpoints."""

import re
from typing import Any, Optional
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException


class InputSanitizer:
    """Basic input sanitization for trading API endpoints."""
    
    # Simple patterns for basic validation
    TRADING_SYMBOL_PATTERN = re.compile(r'^[A-Z0-9&.-]{1,20}$')
    STRATEGY_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,50}$')
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 100) -> str:
        """Sanitize string input with basic validation.
        
        Args:
            value: Input string to sanitize
            max_length: Maximum allowed length
            
        Returns:
            Sanitized string
            
        Raises:
            HTTPException: If input is invalid
        """
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail="Input must be a string")
        
        # Remove potentially dangerous characters and trim whitespace
        sanitized = re.sub(r'[<>"\';\\]', '', value.strip())
        
        if len(sanitized) > max_length:
            raise HTTPException(
                status_code=400, 
                detail=f"Input too long (max {max_length} characters)"
            )
        
        if not sanitized:
            raise HTTPException(status_code=400, detail="Input cannot be empty")
        
        return sanitized
    
    @staticmethod
    def sanitize_trading_symbol(symbol: str) -> str:
        """Sanitize trading symbol input.
        
        Args:
            symbol: Trading symbol to sanitize
            
        Returns:
            Sanitized uppercase trading symbol
            
        Raises:
            HTTPException: If symbol format is invalid
        """
        if not isinstance(symbol, str):
            raise HTTPException(status_code=400, detail="Trading symbol must be a string")
        
        sanitized = symbol.upper().strip()
        
        if not InputSanitizer.TRADING_SYMBOL_PATTERN.match(sanitized):
            raise HTTPException(
                status_code=400, 
                detail="Invalid trading symbol format"
            )
        
        return sanitized
    
    @staticmethod
    def sanitize_strategy_name(name: str) -> str:
        """Sanitize strategy name input.
        
        Args:
            name: Strategy name to sanitize
            
        Returns:
            Sanitized strategy name
            
        Raises:
            HTTPException: If name format is invalid
        """
        if not isinstance(name, str):
            raise HTTPException(status_code=400, detail="Strategy name must be a string")
        
        sanitized = name.strip()
        
        if not InputSanitizer.STRATEGY_NAME_PATTERN.match(sanitized):
            raise HTTPException(
                status_code=400, 
                detail="Invalid strategy name format (alphanumeric, underscore, hyphen only)"
            )
        
        return sanitized
    
    @staticmethod
    def sanitize_positive_number(
        value: Any, 
        field_name: str = "value",
        min_val: Optional[float] = None,
        max_val: Optional[float] = None
    ) -> Decimal:
        """Sanitize positive number input.
        
        Args:
            value: Input value to sanitize
            field_name: Name of the field for error messages
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            
        Returns:
            Sanitized Decimal value
            
        Raises:
            HTTPException: If value is invalid
        """
        try:
            if isinstance(value, str):
                # Remove any non-numeric characters except decimal point
                cleaned = re.sub(r'[^\d.]', '', value)
                if not cleaned:
                    raise ValueError("No numeric content")
                decimal_val = Decimal(cleaned)
            elif isinstance(value, (int, float)):
                decimal_val = Decimal(str(value))
            else:
                raise ValueError("Invalid type")
            
            if decimal_val <= 0:
                raise HTTPException(
                    status_code=400, 
                    detail=f"{field_name} must be positive"
                )
            
            if min_val is not None and decimal_val < Decimal(str(min_val)):
                raise HTTPException(
                    status_code=400, 
                    detail=f"{field_name} must be >= {min_val}"
                )
            
            if max_val is not None and decimal_val > Decimal(str(max_val)):
                raise HTTPException(
                    status_code=400, 
                    detail=f"{field_name} must be <= {max_val}"
                )
            
            return decimal_val
            
        except (ValueError, InvalidOperation):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid {field_name} format"
            )
    
    @staticmethod
    def sanitize_integer(
        value: Any, 
        field_name: str = "value",
        min_val: Optional[int] = None,
        max_val: Optional[int] = None
    ) -> int:
        """Sanitize integer input.
        
        Args:
            value: Input value to sanitize
            field_name: Name of the field for error messages
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            
        Returns:
            Sanitized integer value
            
        Raises:
            HTTPException: If value is invalid
        """
        try:
            if isinstance(value, str):
                # Remove any non-numeric characters
                cleaned = re.sub(r'[^\d]', '', value)
                if not cleaned:
                    raise ValueError("No numeric content")
                int_val = int(cleaned)
            elif isinstance(value, (int, float)):
                int_val = int(value)
            else:
                raise ValueError("Invalid type")
            
            if min_val is not None and int_val < min_val:
                raise HTTPException(
                    status_code=400, 
                    detail=f"{field_name} must be >= {min_val}"
                )
            
            if max_val is not None and int_val > max_val:
                raise HTTPException(
                    status_code=400, 
                    detail=f"{field_name} must be <= {max_val}"
                )
            
            return int_val
            
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid {field_name} format"
            )


def validate_required_fields(data: dict, required_fields: list) -> None:
    """Validate that required fields are present and not empty.
    
    Args:
        data: Dictionary containing the data to validate
        required_fields: List of required field names
        
    Raises:
        HTTPException: If any required fields are missing
    """
    missing_fields = []
    empty_fields = []
    
    for field in required_fields:
        if field not in data:
            missing_fields.append(field)
        elif data[field] is None or (isinstance(data[field], str) and not data[field].strip()):
            empty_fields.append(field)
    
    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required fields: {', '.join(missing_fields)}"
        )
    
    if empty_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Empty required fields: {', '.join(empty_fields)}"
        )