"""
EXAMPLE: Final Composition-Only Factory (Phase 5 Result)
This is what the factory would look like after complete legacy removal
"""
import yaml
import importlib
from pathlib import Path
from typing import Dict, Any, List
from decimal import Decimal
from core.logging import get_logger

logger = get_logger("strategy_factory")


class StrategyFactory:
    """
    Modern composition-based strategy factory
    
    🔥 BREAKING CHANGE: NO LONGER RETURNS BaseStrategy OBJECTS
    ✅ NOW RETURNS: StrategyExecutor objects using composition
    """
    
    # ✅ ONLY COMPOSITION STRATEGY REGISTRY - NO LEGACY ENTRIES
    STRATEGY_REGISTRY = {
        "MomentumProcessor": "strategies.implementations.momentum",
        "MeanReversionProcessor": "strategies.implementations.mean_reversion",
    }
    
    @classmethod
    def create_strategy(cls, strategy_id: str, strategy_type: str, 
                       parameters: Dict[str, Any], brokers: List[str] = None, 
                       instrument_tokens: List[int] = None):
        """
        Create composition-based strategy executor
        
        🔥 BREAKING CHANGE: Return type changed from BaseStrategy to StrategyExecutor
        ✅ All strategies now use pure composition architecture
        
        Returns:
            StrategyExecutor: Composed strategy executor (NOT BaseStrategy)
        """
        
        if strategy_type not in cls.STRATEGY_REGISTRY:
            available = ", ".join(cls.STRATEGY_REGISTRY.keys())
            raise ValueError(
                f"Unknown strategy type: {strategy_type}. "
                f"Available: {available}. "
                f"Legacy strategies (SimpleMomentumStrategy, etc.) are no longer supported."
            )
        
        # ✅ CREATE COMPOSITION-BASED STRATEGY CONFIGURATION
        from strategies.core.config import StrategyConfig, ExecutionContext
        
        strategy_config = StrategyConfig(
            strategy_id=strategy_id,
            strategy_type=strategy_type,
            parameters=parameters,
            active_brokers=brokers or ["paper"],
            instrument_tokens=instrument_tokens or [],
            max_position_size=Decimal(str(parameters.get("max_position_size", "10000.0"))),
            risk_multiplier=Decimal(str(parameters.get("risk_multiplier", "1.0"))),
            enabled=True
        )
        
        # ✅ CREATE EXECUTION CONTEXT
        context = ExecutionContext(
            broker=brokers[0] if brokers else "paper",
            portfolio_state={},
            market_session="regular",
            risk_limits={"max_position": Decimal(str(parameters.get("max_position_size", "10000.0")))}
        )
        
        # ✅ USE COMPOSITION FACTORY TO CREATE EXECUTOR
        from strategies.core.factory import StrategyFactory as CompositionFactory
        composition_factory = CompositionFactory()
        executor = composition_factory.create_executor(strategy_config, context)
        
        logger.info(f"Created composition strategy executor", 
                   strategy_id=strategy_id, 
                   strategy_type=strategy_type,
                   architecture="composition")
        
        return executor
    
    @classmethod
    def create_strategies_from_yaml(cls):
        """
        Load composition strategies from YAML - NO LEGACY SUPPORT
        
        🔥 BREAKING CHANGE: Returns List[StrategyExecutor] instead of List[BaseStrategy]
        """
        strategies = []
        config_path = Path(__file__).parent.parent / "strategies" / "configs"
        
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
                
                # ❌ REJECT LEGACY STRATEGY TYPES
                strategy_class = config["strategy_class"]
                if strategy_class in ["SimpleMomentumStrategy", "MomentumStrategy", "MeanReversionStrategy"]:
                    logger.error(
                        f"Legacy strategy type '{strategy_class}' in {config_file.name} is no longer supported. "
                        f"Please update to use composition types: MomentumProcessor, MeanReversionProcessor"
                    )
                    continue
                
                # ✅ CREATE COMPOSITION STRATEGY
                strategy_executor = cls.create_strategy(
                    strategy_id=config["strategy_name"],
                    strategy_type=config["strategy_class"],
                    parameters=config.get("parameters", {}),
                    brokers=config.get("brokers", ["paper"]),
                    instrument_tokens=config.get("instrument_tokens", [])
                )
                
                strategies.append(strategy_executor)
                logger.info(f"Loaded composition strategy from YAML: {config['strategy_name']}")
                
            except Exception as e:
                logger.error(f"Failed to load strategy from {config_file}: {e}")
        
        logger.info(f"Loaded {len(strategies)} composition strategies from YAML")
        return strategies
    
    @classmethod
    def get_available_strategies(cls) -> List[str]:
        """Get list of available COMPOSITION strategy types only"""
        return list(cls.STRATEGY_REGISTRY.keys())
    
    @classmethod
    def validate_no_legacy_references(cls) -> bool:
        """Validate that no legacy strategy references exist in configurations"""
        legacy_types = ["SimpleMomentumStrategy", "MomentumStrategy", "MeanReversionStrategy", "BaseStrategy"]
        
        # Check YAML configs for legacy references
        config_path = Path(__file__).parent.parent / "strategies" / "configs"
        if config_path.exists():
            for config_file in config_path.glob("*.yaml"):
                with open(config_file, 'r') as f:
                    content = f.read()
                    for legacy_type in legacy_types:
                        if legacy_type in content:
                            logger.error(f"Legacy reference '{legacy_type}' found in {config_file}")
                            return False
        
        logger.info("✅ No legacy strategy references found in configurations")
        return True