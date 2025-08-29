"""
Alpha Panda Strategy Framework

Pure composition-based strategy architecture
NO INHERITANCE - NO LEGACY COMPONENTS - COMPOSITION ONLY
"""

# ✅ COMPOSITION FRAMEWORK (ONLY ARCHITECTURE)
from .core import StrategyProcessor, StrategyValidator, SignalResult, StrategyExecutor, StrategyConfig, ExecutionContext, StrategyFactory

# ✅ STRATEGY IMPLEMENTATIONS (Pure composition processors)
from .implementations import create_momentum_processor, create_mean_reversion_processor

# ✅ VALIDATION COMPONENTS
from .validation import create_standard_validator

__all__ = [
    # ✅ COMPOSITION FRAMEWORK (current system)
    'StrategyProcessor', 'StrategyValidator', 'SignalResult',
    'StrategyConfig', 'ExecutionContext', 'StrategyExecutor', 'StrategyFactory',
    # ✅ STRATEGY IMPLEMENTATIONS
    'create_momentum_processor', 'create_mean_reversion_processor',
    # ✅ VALIDATION COMPONENTS
    'create_standard_validator'
]

# ✅ COMPOSITION-ONLY ARCHITECTURE CONFIRMATION
# - NO BaseStrategy inheritance
# - NO Legacy strategy classes
# - Pure Protocol-based contracts
# - Composition over inheritance
# - O(1) instrument routing performance