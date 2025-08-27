# Enhanced Strategy Factory with YAML configuration support
import yaml
import importlib
from pathlib import Path
from typing import Dict, Any, List
from strategies.base import BaseStrategy
from core.logging import get_logger

logger = get_logger("strategy_factory")


class StrategyFactory:
    """Factory for creating strategy instances with broker-aware configuration"""
    
    # Registry of available strategies
    STRATEGY_REGISTRY = {
        "SimpleMomentumStrategy": "strategies.momentum",
        "MomentumStrategy": "strategies.momentum", 
        "MeanReversionStrategy": "strategies.mean_reversion",
    }
    
    @classmethod
    def create_strategy(cls, strategy_id: str, strategy_type: str, parameters: Dict[str, Any],
                       brokers: List[str] = None, instrument_tokens: List[int] = None) -> BaseStrategy:
        """Create a strategy instance with broker awareness"""
        
        if strategy_type not in cls.STRATEGY_REGISTRY:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        
        # Dynamic import
        module_name = cls.STRATEGY_REGISTRY[strategy_type]
        strategy_module = importlib.import_module(module_name)
        
        # Get the strategy class - handle different naming conventions
        strategy_class = getattr(strategy_module, strategy_type, None)
        if strategy_class is None:
            # Try common variations
            if strategy_type == "SimpleMomentumStrategy":
                strategy_class = getattr(strategy_module, "MomentumStrategy", None)
        
        if strategy_class is None:
            raise ValueError(f"Strategy class {strategy_type} not found in module {module_name}")
            
        return strategy_class(
            strategy_id=strategy_id,
            parameters=parameters,
            brokers=brokers or ["paper"],
            instrument_tokens=instrument_tokens or []
        )
    
    @classmethod
    def create_strategies_from_yaml(cls) -> List[BaseStrategy]:
        """
        Load all strategy configurations from YAML files and create instances.
        This is an alternative to database-driven configuration.
        """
        strategies = []
        config_path = Path(__file__).parent.parent.parent / "strategies" / "configs"
        
        if not config_path.exists():
            logger.warning(f"Strategy configs directory not found: {config_path}")
            return strategies
        
        for config_file in config_path.glob("*.yaml"):
            try:
                with open(config_file, 'r') as f:
                    config = yaml.safe_load(f)
                
                # Skip disabled strategies
                if not config.get('enabled', True):
                    logger.info(f"Skipping disabled strategy: {config_file.name}")
                    continue
                
                # Create strategy using the factory
                strategy_instance = cls.create_strategy(
                    strategy_id=config["strategy_name"],
                    strategy_type=config["strategy_class"],
                    parameters=config.get("parameters", {}),
                    brokers=config.get("brokers", ["paper"]),
                    instrument_tokens=config.get("instrument_tokens", [])
                )
                
                strategies.append(strategy_instance)
                logger.info(f"Loaded strategy from YAML: {config['strategy_name']}")
                
            except Exception as e:
                logger.error(f"Failed to load strategy from {config_file}: {e}")
        
        logger.info(f"Loaded {len(strategies)} strategies from YAML configurations")
        return strategies
    
    @classmethod
    def get_available_strategies(cls) -> list:
        """Get list of available strategy types"""
        return list(cls.STRATEGY_REGISTRY.keys())