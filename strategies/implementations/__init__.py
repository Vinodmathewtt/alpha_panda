"""
ML strategy implementations using composition pattern
"""

from .ml_momentum import create_ml_momentum_processor
from .ml_mean_reversion import create_ml_mean_reversion_processor
from .ml_breakout import create_ml_breakout_processor

__all__ = [
    'create_ml_momentum_processor',
    'create_ml_mean_reversion_processor',
    'create_ml_breakout_processor',
]
