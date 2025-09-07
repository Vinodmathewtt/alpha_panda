"""
Centralized model loading with caching
"""

import os
from pathlib import Path
from typing import Optional, Any, Dict
import logging

# Conditional import for ML dependencies
try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    joblib = None
    HAS_JOBLIB = False


class ModelLoader:
    """Centralized model loading with caching"""
    
    _model_cache: Dict[str, Any] = {}
    
    @classmethod
    def load_model(cls, model_path: str) -> Optional[Any]:
        """Load model with caching"""
        
        # Check if joblib is available
        if not HAS_JOBLIB:
            logging.getLogger("strategies.ml_utils.model_loader").warning(
                "joblib not available - cannot load model", extra={"model_path": model_path}
            )
            return None
        
        # Resolve path relative to strategies directory, normalize optional 'strategies/' prefix
        if not os.path.isabs(model_path):
            strategies_dir = Path(__file__).parent.parent
            p = Path(model_path)
            # Drop leading 'strategies' to avoid double prefix when callers pass 'strategies/models/...'
            if len(p.parts) > 0 and p.parts[0] == 'strategies':
                p = Path(*p.parts[1:])
            model_path = str((strategies_dir / p))
        
        # Check cache first
        if model_path in cls._model_cache:
            logging.getLogger("strategies.ml_utils.model_loader").debug(
                "Returning model from cache", extra={"model_path": model_path}
            )
            return cls._model_cache[model_path]
        
        # Load model
        try:
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model file not found: {model_path}")
                
            model = joblib.load(model_path)
            cls._model_cache[model_path] = model
            # Enrich logs with basic metadata where available
            try:
                meta = {
                    "model_path": model_path,
                    "model_class": type(model).__name__,
                }
                nfi = getattr(model, 'n_features_in_', None)
                if nfi is not None:
                    meta["n_features_in"] = int(nfi)
                version = getattr(model, 'version', None)
                if version is not None:
                    meta["model_version"] = str(version)
                logging.getLogger("strategies.ml_utils.model_loader").info(
                    "Model loaded", extra=meta
                )
            except Exception:
                logging.getLogger("strategies.ml_utils.model_loader").info(
                    "Model loaded", extra={"model_path": model_path}
                )
            return model
            
        except Exception as e:
            logging.getLogger("strategies.ml_utils.model_loader").exception(
                "Failed to load model", extra={"model_path": model_path}
            )
            return None
    
    @classmethod
    def clear_cache(cls):
        """Clear model cache - useful for testing"""
        cls._model_cache.clear()

    @staticmethod
    def get_model_metadata(model: Any) -> Dict[str, Any]:
        """Return lightweight model metadata for diagnostics."""
        try:
            meta: Dict[str, Any] = {"model_class": type(model).__name__}
            nfi = getattr(model, 'n_features_in_', None)
            if nfi is not None:
                meta["n_features_in"] = int(nfi)
            version = getattr(model, 'version', None)
            if version is not None:
                meta["model_version"] = str(version)
            return meta
        except Exception:
            return {"model_class": type(model).__name__}
