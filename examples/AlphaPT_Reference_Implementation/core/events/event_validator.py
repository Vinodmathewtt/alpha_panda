"""Event validation system with schema support."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, Union

from core.config.settings import Settings
from core.events.event_exceptions import EventValidationError
from core.events.event_types import BaseEvent, EventType

logger = logging.getLogger(__name__)


class EventSchemaValidator:
    """JSON schema validator for events."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.validation_config = settings.event_system.validation
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._initialize_schemas()
    
    def _initialize_schemas(self) -> None:
        """Initialize JSON schemas for different event types."""
        # Base event schema
        self._schemas["base"] = {
            "type": "object",
            "required": ["event_id", "event_type", "timestamp", "source"],
            "properties": {
                "event_id": {"type": "string", "minLength": 1},
                "event_type": {"type": "string", "minLength": 1},
                "timestamp": {"type": "string", "format": "date-time"},
                "source": {"type": "string", "minLength": 1},
                "correlation_id": {"type": ["string", "null"]},
                "metadata": {"type": ["object", "null"]}
            },
            "additionalProperties": True
        }
        
        # Market data event schema
        self._schemas["market_data"] = {
            "type": "object",
            "required": ["event_id", "event_type", "timestamp", "source"],
            "properties": {
                **self._schemas["base"]["properties"],
                "instrument_token": {"type": ["integer", "null"], "minimum": 1},
                "exchange": {"type": ["string", "null"], "minLength": 1},
                "last_price": {"type": ["number", "null"], "minimum": 0},
                "last_quantity": {"type": ["integer", "null"], "minimum": 0},
                "volume": {"type": ["integer", "null"], "minimum": 0},
                "average_price": {"type": ["number", "null"], "minimum": 0},
                "data": {"type": ["object", "null"]},
                "ohlc": {"type": ["object", "null"]},
                "depth": {"type": ["object", "null"]}
            },
            "additionalProperties": True
        }
        
        # Trading event schema
        self._schemas["trading"] = {
            "type": "object",
            "required": ["event_id", "event_type", "timestamp", "source"],
            "properties": {
                **self._schemas["base"]["properties"],
                "strategy_name": {"type": ["string", "null"], "minLength": 1},
                "instrument_token": {"type": ["integer", "null"], "minimum": 1},
                "order_id": {"type": ["string", "null"], "minLength": 1},
                "action": {"type": ["string", "null"], "enum": ["BUY", "SELL", "CANCEL", None]},
                "quantity": {"type": ["integer", "null"], "minimum": 1},
                "price": {"type": ["number", "string", "null"], "minimum": 0},
                "signal_strength": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "data": {"type": ["object", "null"]}
            },
            "additionalProperties": True
        }
        
        # System event schema
        self._schemas["system"] = {
            "type": "object",
            "required": ["event_id", "event_type", "timestamp", "source"],
            "properties": {
                **self._schemas["base"]["properties"],
                "component": {"type": ["string", "null"], "minLength": 1},
                "severity": {"type": ["string", "null"], "enum": ["INFO", "WARNING", "ERROR", "CRITICAL", None]},
                "message": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"], "enum": ["healthy", "degraded", "unhealthy", None]},
                "details": {"type": ["object", "null"]},
                "metrics": {"type": ["object", "null"]}
            },
            "additionalProperties": True
        }
        
        # Risk event schema
        self._schemas["risk"] = {
            "type": "object",
            "required": ["event_id", "event_type", "timestamp", "source"],
            "properties": {
                **self._schemas["base"]["properties"],
                "strategy_name": {"type": ["string", "null"], "minLength": 1},
                "risk_type": {"type": ["string", "null"], "enum": ["position_limit", "loss_limit", "exposure_limit", None]},
                "risk_metric": {"type": ["string", "null"]},
                "current_value": {"type": ["number", "string", "null"]},
                "limit_value": {"type": ["number", "string", "null"]},
                "utilization_pct": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                "breach_level": {"type": ["string", "null"], "enum": ["warning", "breach", "recovery", None]},
                "details": {"type": ["object", "null"]}
            },
            "additionalProperties": True
        }
    
    def get_schema_for_event_type(self, event_type: EventType) -> Dict[str, Any]:
        """Get appropriate schema for event type."""
        event_value = event_type.value
        
        if event_value.startswith("market."):
            return self._schemas["market_data"]
        elif event_value.startswith("trading."):
            return self._schemas["trading"]
        elif event_value.startswith("system.") or event_value.startswith("strategy."):
            return self._schemas["system"]
        elif event_value.startswith("risk."):
            return self._schemas["risk"]
        else:
            return self._schemas["base"]
    
    def validate_event_dict(self, event_data: Dict[str, Any], event_type: EventType = None) -> List[str]:
        """Validate event dictionary against schema."""
        if not self.validation_config.schema_validation:
            return []
        
        errors = []
        
        try:
            # Try to determine event type if not provided
            if not event_type and "event_type" in event_data:
                try:
                    event_type = EventType(event_data["event_type"])
                except ValueError:
                    errors.append(f"Invalid event_type: {event_data['event_type']}")
                    return errors
            
            if not event_type:
                errors.append("Cannot determine event type for schema validation")
                return errors
            
            # Get appropriate schema
            schema = self.get_schema_for_event_type(event_type)
            
            # Basic validation (simplified JSON schema validation)
            errors.extend(self._validate_against_schema(event_data, schema))
            
        except Exception as e:
            errors.append(f"Schema validation error: {str(e)}")
        
        return errors
    
    def _validate_against_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
        """Simplified JSON schema validation."""
        errors = []
        
        # Check required fields
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
            elif data[field] is None:
                errors.append(f"Required field cannot be null: {field}")
        
        # Check field types and constraints
        properties = schema.get("properties", {})
        for field, field_schema in properties.items():
            if field not in data:
                continue
            
            value = data[field]
            if value is None and "null" in field_schema.get("type", []):
                continue
            
            # Type checking
            expected_types = field_schema.get("type", [])
            if isinstance(expected_types, str):
                expected_types = [expected_types]
            
            if not self._check_type(value, expected_types):
                errors.append(f"Field '{field}' has invalid type. Expected: {expected_types}, got: {type(value).__name__}")
                continue
            
            # Additional constraints
            if "enum" in field_schema and value not in field_schema["enum"]:
                errors.append(f"Field '{field}' has invalid value. Must be one of: {field_schema['enum']}")
            
            if "minimum" in field_schema and isinstance(value, (int, float)) and value < field_schema["minimum"]:
                errors.append(f"Field '{field}' is below minimum: {field_schema['minimum']}")
            
            if "maximum" in field_schema and isinstance(value, (int, float)) and value > field_schema["maximum"]:
                errors.append(f"Field '{field}' is above maximum: {field_schema['maximum']}")
            
            if "minLength" in field_schema and isinstance(value, str) and len(value) < field_schema["minLength"]:
                errors.append(f"Field '{field}' is shorter than minimum length: {field_schema['minLength']}")
        
        return errors
    
    def _check_type(self, value: Any, expected_types: List[str]) -> bool:
        """Check if value matches expected types."""
        if "null" in expected_types and value is None:
            return True
        
        type_mapping = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "object": dict,
            "array": list
        }
        
        for expected_type in expected_types:
            if expected_type == "null":
                continue
            
            expected_python_type = type_mapping.get(expected_type)
            if expected_python_type and isinstance(value, expected_python_type):
                return True
        
        return False


class EventValidator:
    """Main event validator with multiple validation strategies."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.validation_config = settings.event_system.validation
        self.schema_validator = EventSchemaValidator(settings)
    
    def validate_event(self, event: BaseEvent) -> None:
        """Validate event using configured validation strategies."""
        if not self.validation_config.enabled:
            return
        
        errors = []
        
        # Basic field validation
        errors.extend(self._validate_basic_fields(event))
        
        # Size validation
        errors.extend(self._validate_event_size(event))
        
        # Schema validation (if enabled)
        if self.validation_config.schema_validation:
            try:
                event_dict = event.to_dict()
                schema_errors = self.schema_validator.validate_event_dict(event_dict, event.event_type)
                errors.extend(schema_errors)
            except Exception as e:
                errors.append(f"Schema validation failed: {str(e)}")
        
        # Raise validation error if any issues found
        if errors:
            raise EventValidationError(f"Event validation failed: {'; '.join(errors)}", validation_errors=errors)
    
    def _validate_basic_fields(self, event: BaseEvent) -> List[str]:
        """Validate basic required fields."""
        errors = []
        
        # Check required fields from config
        required_fields = self.validation_config.required_fields
        for field in required_fields:
            if not hasattr(event, field):
                errors.append(f"Missing required field: {field}")
            else:
                value = getattr(event, field)
                if value is None:
                    errors.append(f"Required field cannot be null: {field}")
                elif isinstance(value, str) and not value.strip():
                    errors.append(f"Required field cannot be empty: {field}")
        
        # Validate timestamp
        if hasattr(event, "timestamp") and event.timestamp:
            if not isinstance(event.timestamp, datetime):
                errors.append("Timestamp must be a datetime object")
            else:
                # Check if timestamp is reasonable (not too far in past/future)
                now = datetime.now(event.timestamp.tzinfo)
                time_diff = abs((now - event.timestamp).total_seconds())
                if time_diff > 3600:  # More than 1 hour difference
                    errors.append(f"Timestamp is suspicious: {time_diff} seconds from current time")
        
        return errors
    
    def _validate_event_size(self, event: BaseEvent) -> List[str]:
        """Validate event size constraints."""
        errors = []
        
        try:
            event_json = event.to_json()
            event_size = len(event_json.encode('utf-8'))
            
            if event_size > self.validation_config.max_event_size_bytes:
                errors.append(f"Event size ({event_size} bytes) exceeds maximum ({self.validation_config.max_event_size_bytes} bytes)")
        
        except Exception as e:
            errors.append(f"Failed to calculate event size: {str(e)}")
        
        return errors


# Global validator instance
_event_validator: Optional[EventValidator] = None


def get_event_validator(settings: Optional[Settings] = None) -> EventValidator:
    """Get global event validator instance."""
    global _event_validator
    if _event_validator is None:
        if settings is None:
            from core.config.settings import Settings
            settings = Settings()
        _event_validator = EventValidator(settings)
    return _event_validator


def validate_event(event: BaseEvent, settings: Optional[Settings] = None) -> None:
    """Convenience function to validate an event."""
    validator = get_event_validator(settings)
    validator.validate_event(event)