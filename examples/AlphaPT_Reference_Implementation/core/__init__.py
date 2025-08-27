"""
AlphaPT - High-performance algorithmic trading application
"""

__version__ = "0.1.0"
__author__ = "AlphaPT Team"
__email__ = "team@alphapt.dev"

from core.config.settings import Settings
from core.utils.exceptions import AlphaPTException

__all__ = ["Settings", "AlphaPTException", "__version__"]
