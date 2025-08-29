"""
Modern strategy implementations using composition pattern
"""

from .momentum import create_momentum_processor
from .mean_reversion import create_mean_reversion_processor

__all__ = ['create_momentum_processor', 'create_mean_reversion_processor']