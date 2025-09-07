"""
Strategy factory for creating strategy executors using composition
"""

import importlib
from typing import Dict, Any
from .protocols import StrategyProcessor, StrategyValidator
from .executor import StrategyExecutor  
from .config import StrategyConfig, ExecutionContext
from core.logging import get_trading_logger_safe

logger = get_trading_logger_safe("strategy_factory")


class StrategyFactory:
    """Factory for creating strategy executors using composition"""
    
    def __init__(self):
        # Strategy processors registry - supports all types: rules, ML, and hybrid
        self._processors = {
            # ML strategies (existing)
            "ml_momentum": "strategies.implementations.ml_momentum.create_ml_momentum_processor",
            "MLMomentumProcessor": "strategies.implementations.ml_momentum.create_ml_momentum_processor",
            "ml_mean_reversion": "strategies.implementations.ml_mean_reversion.create_ml_mean_reversion_processor",
            "MLMeanReversionProcessor": "strategies.implementations.ml_mean_reversion.create_ml_mean_reversion_processor",
            "ml_breakout": "strategies.implementations.ml_breakout.create_ml_breakout_processor",
            "MLBreakoutProcessor": "strategies.implementations.ml_breakout.create_ml_breakout_processor",
            
            # Rule-based strategies (new)
            "momentum": "strategies.implementations.momentum.create_momentum_processor",
            "mean_reversion": "strategies.implementations.mean_reversion.create_mean_reversion_processor",
            "rsi": "strategies.implementations.rsi.create_rsi_processor",
            
            # Hybrid strategies (new)
            "hybrid_momentum": "strategies.implementations.hybrid_momentum.create_hybrid_momentum_processor",
            "hybrid_mean_reversion": "strategies.implementations.hybrid_mean_reversion.create_hybrid_mean_reversion_processor",
            
            # Demo/validation strategies (low-frequency signals)
            "low_frequency_demo": "strategies.implementations.low_frequency_demo.create_low_frequency_demo_processor",
        }
        
        # Registry of validators
        self._validators = {
            "standard": "strategies.validation.standard_validator.create_standard_validator"
        }
    
    def create_executor(self, config: StrategyConfig, context: ExecutionContext) -> StrategyExecutor:
        """Create strategy executor using composition"""
        # Create processor using factory function
        processor_factory = self._load_factory(self._processors[config.strategy_type])
        processor = processor_factory(config.parameters)

        # Optional ML capability detection - no hard enforcement
        if hasattr(processor, "load_model"):
            try:
                loaded = processor.load_model()
                if not loaded:
                    logger.warning("ML model failed to load", strategy_type=config.strategy_type)
            except Exception as e:
                logger.warning("ML model loading error", strategy_type=config.strategy_type, error=str(e))
        
        # Create validator
        validator_type = config.parameters.get("validator", "standard")
        validator_factory = self._load_factory(self._validators[validator_type]) 
        validator = validator_factory(config.parameters)
        
        # Compose executor
        return StrategyExecutor(
            processor=processor,
            validator=validator,
            config=config,
            context=context
        )
    
    def register_processor(self, strategy_type: str, factory_path: str):
        """Register new strategy processor"""
        self._processors[strategy_type] = factory_path
    
    def register_validator(self, validator_type: str, factory_path: str):
        """Register new validator"""
        self._validators[validator_type] = factory_path

    def _load_factory(self, factory_path: str):
        """Dynamically load factory function"""
        module_path, function_name = factory_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, function_name)

    def get_available_strategy_types(self) -> list[str]:
        """Return list of registered strategy processor types."""
        return list(self._processors.keys())

    def get_available_validator_types(self) -> list[str]:
        """Return list of registered validator types."""
        return list(self._validators.keys())
