"""Strategy factory for creating and managing strategy instances."""

import importlib
import inspect
from typing import Dict, Any, Type, List, Optional
from pathlib import Path

from .base_strategy import BaseStrategy
from core.logging.logger import get_logger


class StrategyFactory:
    """Factory class for creating and managing strategy instances.
    
    The StrategyFactory handles dynamic loading of strategy classes,
    validation, and instantiation with proper configuration.
    """
    
    def __init__(self):
        self.logger = get_logger("strategy_factory", "strategy")
        self.registered_strategies: Dict[str, Type[BaseStrategy]] = {}
        self.strategy_metadata: Dict[str, Dict[str, Any]] = {}
    
    def register_strategy(
        self, 
        strategy_name: str, 
        strategy_class: Type[BaseStrategy],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Register a strategy class with the factory.
        
        Args:
            strategy_name: Unique name for the strategy
            strategy_class: Strategy class (must inherit from BaseStrategy)
            metadata: Optional metadata about the strategy
        """
        if not issubclass(strategy_class, BaseStrategy):
            raise ValueError(f"Strategy class {strategy_class.__name__} must inherit from BaseStrategy")
        
        self.registered_strategies[strategy_name] = strategy_class
        self.strategy_metadata[strategy_name] = metadata or {}
        
        self.logger.info(f"Registered strategy: {strategy_name} -> {strategy_class.__name__}")
    
    def unregister_strategy(self, strategy_name: str):
        """Unregister a strategy from the factory.
        
        Args:
            strategy_name: Name of strategy to unregister
        """
        if strategy_name in self.registered_strategies:
            del self.registered_strategies[strategy_name]
            if strategy_name in self.strategy_metadata:
                del self.strategy_metadata[strategy_name]
            self.logger.info(f"Unregistered strategy: {strategy_name}")
    
    def create_strategy(
        self, 
        strategy_name: str, 
        strategy_type: str,
        config: Dict[str, Any]
    ) -> BaseStrategy:
        """Create a strategy instance.
        
        Args:
            strategy_name: Unique name for this strategy instance
            strategy_type: Type of strategy to create
            config: Strategy configuration
            
        Returns:
            BaseStrategy: Configured strategy instance
            
        Raises:
            ValueError: If strategy type is not registered
            Exception: If strategy creation fails
        """
        if strategy_type not in self.registered_strategies:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        
        strategy_class = self.registered_strategies[strategy_type]
        
        try:
            # Validate configuration against strategy requirements
            self._validate_config(strategy_class, config)
            
            # Create strategy instance
            strategy = strategy_class(strategy_name, config)
            
            self.logger.info(f"Created strategy instance: {strategy_name} ({strategy_type})")
            return strategy
            
        except Exception as e:
            self.logger.error(f"Failed to create strategy {strategy_name}: {e}")
            raise
    
    def _validate_config(self, strategy_class: Type[BaseStrategy], config: Dict[str, Any]):
        """Validate strategy configuration.
        
        Args:
            strategy_class: Strategy class to validate against
            config: Configuration to validate
        """
        # Check required configuration fields
        required_fields = ['instruments']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required configuration field: {field}")
        
        # Validate instruments
        instruments = config.get('instruments', [])
        if not instruments:
            raise ValueError("Strategy must have at least one instrument configured")
        
        # Additional strategy-specific validation can be added here
        # by checking for strategy class methods or attributes
    
    def discover_strategies(self, strategies_dir: Path) -> int:
        """Discover and register strategies from a directory.
        
        Args:
            strategies_dir: Directory containing strategy modules
            
        Returns:
            int: Number of strategies discovered and registered
        """
        if not strategies_dir.exists() or not strategies_dir.is_dir():
            self.logger.warning(f"Strategies directory not found: {strategies_dir}")
            return 0
        
        discovered_count = 0
        
        # Look for Python files in the strategies directory
        for strategy_file in strategies_dir.glob("*.py"):
            if strategy_file.name.startswith("__"):
                continue
            
            try:
                # Import the module
                module_name = strategy_file.stem
                import importlib.util
                spec = importlib.util.spec_from_file_location(module_name, strategy_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find strategy classes in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseStrategy) and 
                        obj is not BaseStrategy and 
                        obj.__module__ == module_name):
                        
                        strategy_name = module_name
                        self.register_strategy(strategy_name, obj)
                        discovered_count += 1
                        
            except Exception as e:
                self.logger.error(f"Failed to load strategy from {strategy_file}: {e}")
                continue
        
        self.logger.info(f"Discovered and registered {discovered_count} strategies")
        return discovered_count
    
    def get_registered_strategies(self) -> List[str]:
        """Get list of registered strategy types.
        
        Returns:
            List[str]: List of registered strategy type names
        """
        return list(self.registered_strategies.keys())
    
    def get_strategy_metadata(self, strategy_type: str) -> Dict[str, Any]:
        """Get metadata for a strategy type.
        
        Args:
            strategy_type: Strategy type name
            
        Returns:
            Dict[str, Any]: Strategy metadata
        """
        return self.strategy_metadata.get(strategy_type, {})
    
    def get_strategy_info(self, strategy_type: str) -> Dict[str, Any]:
        """Get comprehensive information about a strategy type.
        
        Args:
            strategy_type: Strategy type name
            
        Returns:
            Dict[str, Any]: Strategy information including class details
        """
        if strategy_type not in self.registered_strategies:
            return {}
        
        strategy_class = self.registered_strategies[strategy_type]
        metadata = self.strategy_metadata.get(strategy_type, {})
        
        return {
            'strategy_type': strategy_type,
            'class_name': strategy_class.__name__,
            'module': strategy_class.__module__,
            'docstring': strategy_class.__doc__,
            'metadata': metadata,
            'base_classes': [cls.__name__ for cls in strategy_class.__bases__],
            'methods': [method for method in dir(strategy_class) 
                       if callable(getattr(strategy_class, method)) and not method.startswith('_')]
        }
    
    def validate_strategy_config(self, strategy_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a strategy configuration without creating an instance.
        
        Args:
            strategy_type: Strategy type name
            config: Configuration to validate
            
        Returns:
            Dict[str, Any]: Validation result with status and messages
        """
        result = {
            'valid': False,
            'errors': [],
            'warnings': []
        }
        
        try:
            if strategy_type not in self.registered_strategies:
                result['errors'].append(f"Unknown strategy type: {strategy_type}")
                return result
            
            strategy_class = self.registered_strategies[strategy_type]
            self._validate_config(strategy_class, config)
            
            result['valid'] = True
            result['message'] = "Configuration is valid"
            
        except Exception as e:
            result['errors'].append(str(e))
        
        return result
    
    def clear_registry(self):
        """Clear all registered strategies."""
        self.registered_strategies.clear()
        self.strategy_metadata.clear()
        self.logger.info("Cleared strategy registry")
    
    def reload_strategy(self, strategy_type: str) -> bool:
        """Reload a strategy class from its module.
        
        Args:
            strategy_type: Strategy type to reload
            
        Returns:
            bool: True if reload was successful
        """
        if strategy_type not in self.registered_strategies:
            self.logger.error(f"Cannot reload unknown strategy: {strategy_type}")
            return False
        
        try:
            strategy_class = self.registered_strategies[strategy_type]
            module_name = strategy_class.__module__
            
            # Reload the module
            module = importlib.import_module(module_name)
            importlib.reload(module)
            
            # Find and re-register the strategy class
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, BaseStrategy) and 
                    obj is not BaseStrategy and 
                    obj.__name__ == strategy_class.__name__):
                    
                    # Re-register with same metadata
                    metadata = self.strategy_metadata.get(strategy_type, {})
                    self.register_strategy(strategy_type, obj, metadata)
                    
                    self.logger.info(f"Reloaded strategy: {strategy_type}")
                    return True
            
            self.logger.error(f"Could not find strategy class after reload: {strategy_type}")
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to reload strategy {strategy_type}: {e}")
            return False
    
    def get_factory_stats(self) -> Dict[str, Any]:
        """Get factory statistics and status.
        
        Returns:
            Dict[str, Any]: Factory statistics
        """
        return {
            'registered_strategies': len(self.registered_strategies),
            'strategy_types': list(self.registered_strategies.keys()),
            'strategy_classes': [cls.__name__ for cls in self.registered_strategies.values()],
            'total_metadata_entries': len(self.strategy_metadata)
        }


# Global factory instance
strategy_factory = StrategyFactory()


# Convenience functions for common operations

def register_strategy(strategy_name: str, strategy_class: Type[BaseStrategy], metadata: Dict[str, Any] = None):
    """Register a strategy with the global factory."""
    strategy_factory.register_strategy(strategy_name, strategy_class, metadata)


def create_strategy(strategy_name: str, strategy_type: str, config: Dict[str, Any]) -> BaseStrategy:
    """Create a strategy using the global factory."""
    return strategy_factory.create_strategy(strategy_name, strategy_type, config)


def get_available_strategies() -> List[str]:
    """Get list of available strategy types."""
    return strategy_factory.get_registered_strategies()


def discover_strategies_from_dir(strategies_dir: Path) -> int:
    """Discover strategies from directory using global factory."""
    return strategy_factory.discover_strategies(strategies_dir)