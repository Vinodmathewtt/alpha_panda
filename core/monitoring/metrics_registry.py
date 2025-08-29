"""
Centralized metrics registry preventing key drift between writers and readers
Provides standardized key generation for all monitoring components
"""

from typing import Dict, List


class MetricsRegistry:
    """Centralized registry for all monitoring metric keys"""
    
    BASE_PREFIX = "pipeline"
    
    @classmethod
    def _build_key(cls, stage: str, broker: str, metric_type: str) -> str:
        """Build standardized metric key"""
        return f"{cls.BASE_PREFIX}:{stage}:{broker}:{metric_type}"
    
    # Market Data Stage (shared across all brokers)
    @classmethod  
    def market_ticks_last(cls) -> str:
        """Key for last market tick timestamp"""
        return f"{cls.BASE_PREFIX}:market_ticks:market:last"
    
    @classmethod
    def market_ticks_count(cls) -> str:
        """Key for market tick count"""
        return f"{cls.BASE_PREFIX}:market_ticks:market:count"
    
    # Signal Generation Stage (broker-specific)
    @classmethod
    def signals_last(cls, broker: str) -> str:
        """Key for last signal generation timestamp"""
        return cls._build_key("signals", broker, "last")
    
    @classmethod
    def signals_count(cls, broker: str) -> str:
        """Key for signal generation count"""
        return cls._build_key("signals", broker, "count")
        
    # Risk Validation Stage (broker-specific)
    @classmethod
    def risk_validation_last(cls, broker: str) -> str:
        """Key for last risk validation timestamp"""
        return cls._build_key("risk_validation", broker, "last")
    
    @classmethod
    def risk_validation_count(cls, broker: str) -> str:
        """Key for risk validation count"""
        return cls._build_key("risk_validation", broker, "count")
    
    # Signals Validated Stage (broker-specific)
    @classmethod
    def signals_validated_last(cls, broker: str) -> str:
        """Key for last validated signal timestamp"""
        return cls._build_key("signals_validated", broker, "last")
    
    @classmethod
    def signals_validated_count(cls, broker: str) -> str:
        """Key for validated signals count"""
        return cls._build_key("signals_validated", broker, "count")
        
    # Order Processing Stage (broker-specific)
    @classmethod
    def orders_last(cls, broker: str) -> str:
        """Key for last order processing timestamp"""
        return cls._build_key("orders", broker, "last")
    
    @classmethod
    def orders_count(cls, broker: str) -> str:
        """Key for order processing count"""
        return cls._build_key("orders", broker, "count")
        
    # Portfolio Updates Stage (broker-specific) 
    @classmethod
    def portfolio_updates_last(cls, broker: str) -> str:
        """Key for last portfolio update timestamp"""
        return cls._build_key("portfolio_updates", broker, "last")
    
    @classmethod
    def portfolio_updates_count(cls, broker: str) -> str:
        """Key for portfolio update count"""
        return cls._build_key("portfolio_updates", broker, "count")
    
    # Health Check Keys
    @classmethod
    def health_check_result(cls, component: str, check_name: str) -> str:
        """Key for health check result"""
        return f"health_check:result:{component}:{check_name}"
    
    @classmethod
    def health_check_status(cls, component: str, check_name: str) -> str:
        """Key for health check status"""
        return f"health_check:status:{component}:{check_name}"
    
    @classmethod
    def health_check_history(cls, component: str, check_name: str) -> str:
        """Key for health check history"""
        return f"health_check:history:{component}:{check_name}"
    
    # Utility Methods
    @classmethod
    def get_all_broker_specific_keys(cls, broker: str) -> Dict[str, str]:
        """Get all broker-specific metric keys for a broker"""
        return {
            "signals_last": cls.signals_last(broker),
            "signals_count": cls.signals_count(broker),
            "risk_validation_last": cls.risk_validation_last(broker),
            "risk_validation_count": cls.risk_validation_count(broker),
            "signals_validated_last": cls.signals_validated_last(broker),
            "signals_validated_count": cls.signals_validated_count(broker),
            "orders_last": cls.orders_last(broker),
            "orders_count": cls.orders_count(broker),
            "portfolio_updates_last": cls.portfolio_updates_last(broker),
            "portfolio_updates_count": cls.portfolio_updates_count(broker)
        }
    
    @classmethod
    def get_shared_keys(cls) -> Dict[str, str]:
        """Get all shared (non-broker-specific) metric keys"""
        return {
            "market_ticks_last": cls.market_ticks_last(),
            "market_ticks_count": cls.market_ticks_count()
        }
    
    @classmethod
    def validate_key_consistency(cls, active_brokers: List[str]) -> Dict[str, List[str]]:
        """Validate key consistency across all brokers and components"""
        all_keys = {}
        
        # Add shared keys
        shared_keys = cls.get_shared_keys()
        all_keys.update(shared_keys)
        
        # Add broker-specific keys
        for broker in active_brokers:
            broker_keys = cls.get_all_broker_specific_keys(broker)
            # Prefix keys with broker name to avoid conflicts
            for key_name, key_value in broker_keys.items():
                all_keys[f"{broker}_{key_name}"] = key_value
        
        return {
            "total_keys": len(all_keys),
            "keys": list(all_keys.values()),
            "key_mapping": all_keys
        }