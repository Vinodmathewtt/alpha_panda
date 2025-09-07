"""
Alpha Panda Strategy Framework

Pure composition-based strategy architecture
NO INHERITANCE - NO LEGACY COMPONENTS - COMPOSITION ONLY
"""

# ✅ COMPOSITION FRAMEWORK (ONLY ARCHITECTURE)
from .core import StrategyProcessor, StrategyValidator, SignalResult, StrategyExecutor, StrategyConfig, ExecutionContext, StrategyFactory
from .core.protocols import MLStrategyProcessor

# ✅ STRATEGY IMPLEMENTATIONS (Pure composition processors)
from .implementations.ml_momentum import create_ml_momentum_processor
from .implementations.ml_mean_reversion import create_ml_mean_reversion_processor
from .implementations.ml_breakout import create_ml_breakout_processor

# ✅ VALIDATION COMPONENTS
from .validation import create_standard_validator

__all__ = [
    # ✅ COMPOSITION FRAMEWORK (current system)
    'StrategyProcessor', 'StrategyValidator', 'SignalResult',
    'StrategyConfig', 'ExecutionContext', 'StrategyExecutor', 'StrategyFactory',
    'MLStrategyProcessor',
    # ✅ STRATEGY IMPLEMENTATIONS (catalog)
    'create_ml_momentum_processor',
    'create_ml_mean_reversion_processor',
    'create_ml_breakout_processor',
    # ✅ VALIDATION COMPONENTS
    'create_standard_validator'
]

# ✅ COMPOSITION-ONLY ARCHITECTURE CONFIRMATION
# - NO BaseStrategy inheritance
# - NO Legacy strategy classes
# - Pure Protocol-based contracts
# - Composition over inheritance
# - O(1) instrument routing performance
