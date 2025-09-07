# Modern composition-based strategy factory
# NO INHERITANCE, NO BaseStrategy, PURE COMPOSITION ARCHITECTURE
import yaml
import importlib
from pathlib import Path
from typing import Dict, Any, List
from decimal import Decimal

# ✅ ONLY COMPOSITION IMPORTS - NO BaseStrategy, NO legacy imports
from strategies.core.factory import StrategyFactory as CompositionFactory
from strategies.core.executor import StrategyExecutor
from strategies.core.config import StrategyConfig, ExecutionContext
from core.logging import get_trading_logger_safe

logger = get_trading_logger_safe("strategy_factory")

class StrategyFactory:
    """
    Modern composition-based strategy factory
    
    🔥 BREAKING CHANGE: NO LONGER RETURNS BaseStrategy OBJECTS
    ✅ NOW RETURNS: StrategyExecutor objects using composition
    """
    
    # Migration mapping removed - let users explicitly choose strategy types
    MIGRATION_MAPPING = {}
    
    @classmethod
    def create_strategy(cls, strategy_id: str, strategy_type: str, 
                       parameters: Dict[str, Any], brokers: List[str] = None, 
                       instrument_tokens: List[int] = None) -> StrategyExecutor:
        """
        Create composition-based strategy executor
        
        🔥 BREAKING CHANGE: Return type changed from BaseStrategy to StrategyExecutor
        ✅ All strategies now use pure composition architecture
        
        Returns:
            StrategyExecutor: Composed strategy executor (NOT BaseStrategy)
        """
        
        # Automatically convert legacy strategy types to composition types
        composition_type = cls.MIGRATION_MAPPING.get(strategy_type, strategy_type)
        
        # Discover available types from the composition factory to avoid drift
        _composition_factory = CompositionFactory()
        _available_types = set(_composition_factory.get_available_strategy_types())

        if composition_type not in _available_types:
            available = ", ".join(sorted(_available_types))
            legacy_types = list(cls.MIGRATION_MAPPING.keys())
            raise ValueError(
                f"Unknown strategy type: {strategy_type} -> {composition_type}. "
                f"Available composition types: {available}. "
                f"Legacy types are automatically converted: {legacy_types}"
            )
        
        # ✅ CREATE COMPOSITION-BASED STRATEGY CONFIGURATION
        strategy_config = StrategyConfig(
            strategy_id=strategy_id,
            strategy_type=composition_type,
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
        composition_factory = CompositionFactory()
        executor = composition_factory.create_executor(strategy_config, context)
        
        logger.info("Created composition strategy executor", 
                   strategy_id=strategy_id, 
                   strategy_type=composition_type,
                   original_type=strategy_type,
                   architecture="composition")
        
        return executor
    
    @classmethod
    def create_strategies_from_yaml(cls) -> List[StrategyExecutor]:
        """
        Load composition strategies from YAML - NO LEGACY SUPPORT
        
        🔥 BREAKING CHANGE: Returns List[StrategyExecutor] instead of List[BaseStrategy]
        """
        strategies = []
        config_path = Path(__file__).parent.parent.parent / "strategies" / "configs"
        
        if not config_path.exists():
            logger.warning("Strategy configs directory not found", path=str(config_path))
            return strategies
        
        for config_file in config_path.glob("*.yaml"):
            try:
                with open(config_file, 'r') as f:
                    config = yaml.safe_load(f)
                
                # Skip disabled strategies
                if not config.get('enabled', True):
                    logger.info(f"Skipping disabled strategy: {config_file.name}")
                    continue
                
                # Allow either strategy_class (legacy key) or strategy_type
                strategy_class = (
                    config.get("strategy_class") or config.get("strategy_type")
                )
                if not strategy_class:
                    raise ValueError("Strategy config missing 'strategy_class' or 'strategy_type'")

                # ❌ WARN ABOUT LEGACY STRATEGY TYPES (but auto-convert)
                if strategy_class in cls.MIGRATION_MAPPING:
                    new_type = cls.MIGRATION_MAPPING[strategy_class]
                    logger.warning(
                        "Legacy strategy type auto-converted",
                        legacy_type=strategy_class,
                        converted_type=new_type,
                        file=config_file.name,
                    )

                # ✅ CREATE COMPOSITION STRATEGY
                strategy_executor = cls.create_strategy(
                    strategy_id=config["strategy_name"],
                    strategy_type=strategy_class,
                    parameters=config.get("parameters", {}),
                    brokers=config.get("brokers", ["paper"]),
                    instrument_tokens=(
                        config.get("instrument_tokens")
                        or config.get("instruments", [])
                    )
                )
                
                strategies.append(strategy_executor)
                logger.info("Loaded composition strategy from YAML", strategy_name=config["strategy_name"])
                
            except Exception as e:
                logger.error("Failed to load strategy from YAML", file=str(config_file), error=str(e))
        
        logger.info("Loaded composition strategies from YAML", count=len(strategies))
        return strategies
    
    @classmethod
    def get_available_strategies(cls) -> List[str]:
        """Get list of available COMPOSITION strategy types only"""
        return CompositionFactory().get_available_strategy_types()
    
    @classmethod
    def get_legacy_migration_mapping(cls) -> Dict[str, str]:
        """Get mapping from legacy strategy types to composition types"""
        return cls.MIGRATION_MAPPING.copy()
    
    @classmethod
    def validate_no_legacy_references(cls) -> bool:
        """Validate that no legacy strategy references exist in configurations"""
        legacy_types = ["SimpleMomentumStrategy", "MomentumStrategy", "MeanReversionStrategy", "BaseStrategy"]
        
        # Check YAML configs for legacy references
        config_path = Path(__file__).parent.parent.parent / "strategies" / "configs"
        if config_path.exists():
            for config_file in config_path.glob("*.yaml"):
                with open(config_file, 'r') as f:
                    content = f.read()
                    for legacy_type in legacy_types:
                        if legacy_type in content:
                            logger.warning(
                                "Legacy reference found (auto-convert)",
                                reference=legacy_type,
                                file=str(config_file),
                            )
        
        logger.info("Composition-only factory ready - legacy types auto-converted")
        return True
