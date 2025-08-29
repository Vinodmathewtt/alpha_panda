"""
Strategy factory for creating strategy executors using composition
"""

import importlib
from typing import Dict, Any
from .protocols import StrategyProcessor, StrategyValidator
from .executor import StrategyExecutor  
from .config import StrategyConfig, ExecutionContext


class StrategyFactory:
    """Factory for creating strategy executors using composition"""
    
    def __init__(self):
        # Registry of strategy processors
        self._processors = {
            "momentum": "strategies.implementations.momentum.create_momentum_processor",
            "mean_reversion": "strategies.implementations.mean_reversion.create_mean_reversion_processor",
            "MomentumProcessor": "strategies.implementations.momentum.create_momentum_processor",
            "MeanReversionProcessor": "strategies.implementations.mean_reversion.create_mean_reversion_processor"
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