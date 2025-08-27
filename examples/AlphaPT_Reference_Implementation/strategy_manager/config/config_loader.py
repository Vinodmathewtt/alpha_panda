"""Configuration loader for strategy module."""

import os
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
from core.logging.logger import get_logger

logger = get_logger(__name__)


class StrategyConfigLoader:
    """Loads strategy configurations from YAML files."""
    
    def __init__(self, config_dir: str = None, strategy_configs_dir: str = None):
        """Initialize configuration loader.
        
        Args:
            config_dir: Directory containing main strategies.yaml file
            strategy_configs_dir: Directory containing individual strategy configs
        """
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(__file__))
        if strategy_configs_dir is None:
            strategy_configs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "strategy_configs")
            
        self.config_dir = Path(config_dir)
        self.strategy_configs_dir = Path(strategy_configs_dir)
        self.main_config_file = self.config_dir / "strategies.yaml"
        
        self._main_config: Optional[Dict[str, Any]] = None
        self._strategy_configs: Dict[str, Dict[str, Any]] = {}
    
    def load_main_config(self) -> Dict[str, Any]:
        """Load main strategy registry configuration."""
        if self._main_config is not None:
            return self._main_config
            
        try:
            if not self.main_config_file.exists():
                logger.warning(f"Main config file not found: {self.main_config_file}")
                return {"strategies": {}, "risk_profiles": {}}
                
            with open(self.main_config_file, 'r') as file:
                self._main_config = yaml.safe_load(file) or {}
                
            logger.info(f"Loaded main strategy config with {len(self._main_config.get('strategies', {}))} strategies")
            return self._main_config
            
        except Exception as e:
            logger.error(f"Failed to load main config: {e}")
            return {"strategies": {}, "risk_profiles": {}}
    
    def load_strategy_config(self, config_file: str) -> Dict[str, Any]:
        """Load individual strategy configuration.
        
        Args:
            config_file: Name of the strategy config file (e.g., 'momentum_strategy.yaml')
            
        Returns:
            Strategy configuration dictionary
        """
        if config_file in self._strategy_configs:
            return self._strategy_configs[config_file]
            
        try:
            config_path = self.strategy_configs_dir / config_file
            
            if not config_path.exists():
                logger.warning(f"Strategy config file not found: {config_path}")
                return {}
                
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file) or {}
                
            # Validate required fields
            self._validate_strategy_config(config, config_file)
            
            self._strategy_configs[config_file] = config
            logger.info(f"Loaded strategy config: {config_file}")
            return config
            
        except Exception as e:
            logger.error(f"Failed to load strategy config {config_file}: {e}")
            return {}
    
    def get_enabled_strategies(self) -> Dict[str, Dict[str, Any]]:
        """Get all enabled strategies with their configurations."""
        main_config = self.load_main_config()
        enabled_strategies = {}
        
        for strategy_name, strategy_info in main_config.get('strategies', {}).items():
            if strategy_info.get('enabled', False):
                config_file = strategy_info.get('config_file')
                if config_file:
                    strategy_config = self.load_strategy_config(config_file)
                    if strategy_config:
                        # Merge main registry info with detailed config
                        full_config = {
                            'registry_info': strategy_info,
                            **strategy_config
                        }
                        enabled_strategies[strategy_name] = full_config
                        
        return enabled_strategies
    
    def get_risk_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Get risk profile configurations."""
        main_config = self.load_main_config()
        return main_config.get('risk_profiles', {})
    
    def get_strategy_instruments(self, strategy_name: str) -> List[int]:
        """Get instrument tokens for a specific strategy."""
        enabled_strategies = self.get_enabled_strategies()
        strategy_config = enabled_strategies.get(strategy_name, {})
        return strategy_config.get('instruments', [])
    
    def get_all_instruments(self) -> List[int]:
        """Get all unique instrument tokens from all enabled strategies."""
        all_instruments = set()
        enabled_strategies = self.get_enabled_strategies()
        
        for strategy_config in enabled_strategies.values():
            instruments = strategy_config.get('instruments', [])
            all_instruments.update(instruments)
            
        return list(all_instruments)
    
    def get_strategy_routing_config(self, strategy_name: str) -> Dict[str, Any]:
        """Get routing configuration for a specific strategy."""
        enabled_strategies = self.get_enabled_strategies()
        strategy_config = enabled_strategies.get(strategy_name, {})
        return strategy_config.get('routing', {})
    
    def _validate_strategy_config(self, config: Dict[str, Any], config_file: str):
        """Validate strategy configuration structure."""
        required_fields = ['strategy_name', 'strategy_type', 'routing']
        
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field '{field}' in {config_file}")
        
        # Validate routing configuration - NEW LOGIC
        # With the new routing system:
        # - Paper trading is always enabled by default (no need to specify)
        # - Only zerodha_trade needs to be specified (defaults to false)
        routing = config.get('routing', {})
        
        # Routing is always valid now since paper trading is default
        # zerodha_trade is optional and defaults to false
        if 'routing' not in config:
            # Add default routing if not specified
            config['routing'] = {'zerodha_trade': False}
        
        # Validate instruments
        instruments = config.get('instruments', [])
        if not isinstance(instruments, list):
            raise ValueError(f"Instruments must be a list in {config_file}")
        
        for instrument in instruments:
            if not isinstance(instrument, int):
                raise ValueError(f"All instruments must be integer tokens in {config_file}")
    
    def reload_configs(self):
        """Reload all configurations from disk."""
        self._main_config = None
        self._strategy_configs.clear()
        logger.info("Configuration cache cleared - will reload on next access")


# Global instance for the strategy manager module
strategy_config_loader = StrategyConfigLoader()