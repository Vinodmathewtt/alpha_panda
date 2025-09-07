"""
ML-enhanced momentum strategy implementation
Uses composition architecture with ML inference
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
import logging

# Conditional numpy import for ML functionality
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False
from ..core.protocols import MLStrategyProcessor, SignalResult
from ..ml_utils.model_loader import ModelLoader
from core.schemas.events import MarketTick as MarketData


class MLMomentumProcessor:
    """ML-enhanced momentum strategy - uses existing architecture"""
    
    def __init__(self, model_path: str, lookback_periods: int = 20, 
                 confidence_threshold: float = 0.6, position_size: int = 100):
        self._logger = logging.getLogger("strategies.ml_momentum")
        self.model_path = model_path
        self.lookback_periods = lookback_periods  
        self.confidence_threshold = confidence_threshold
        self.position_size = position_size
        self.model = None
        self._strategy_name = "ml_momentum"
        
    def load_model(self) -> bool:
        """Load model once at startup"""
        self.model = ModelLoader.load_model(self.model_path)
        if self.model is None:
            self._logger.warning("ML model not loaded; strategy disabled (will not register)", extra={
                "model_path": self.model_path,
                "strategy": self._strategy_name
            })
        else:
            self._logger.info("ML model loaded", extra={
                "model_path": self.model_path,
                "strategy": self._strategy_name
            })
        return self.model is not None
    
    def extract_features(self, tick: MarketData, history: List[MarketData]):
        """Convert to features for ML model"""
        if not HAS_NUMPY:
            # Fallback to basic features without numpy
            if len(history) < self.lookback_periods:
                return [0.0, 0.0, 0.0, float(tick.last_price), len(history)]
            
            # Basic feature extraction without numpy
            prices = [float(h.last_price) for h in history[-self.lookback_periods:]]
            current_price = float(tick.last_price)
            
            # Simple calculations
            total_return = (current_price - prices[0]) / prices[0] if prices[0] != 0 else 0
            momentum_5 = (current_price - prices[-5]) / prices[-5] if len(prices) >= 5 and prices[-5] != 0 else 0
            
            # Basic volatility calculation
            if len(prices) > 1:
                returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices)) if prices[i-1] != 0]
                volatility = (sum(r*r for r in returns) / len(returns))**0.5 if returns else 0
            else:
                volatility = 0
                
            return [total_return, momentum_5, volatility, current_price, len(history)]
        
        # Use numpy if available
        if len(history) < self.lookback_periods:
            return np.zeros(5)  # Return default features
            
        # Extract price history
        prices = np.array([float(h.last_price) for h in history[-self.lookback_periods:]])
        current_price = float(tick.last_price)
        
        # Calculate features
        returns = np.diff(prices) / prices[:-1]
        features = np.array([
            (current_price - prices[0]) / prices[0],  # Total return
            (current_price - prices[-5]) / prices[-5] if len(prices) >= 5 else 0,  # 5-period momentum
            np.std(returns) if len(returns) > 0 else 0,  # Volatility
            current_price,  # Current price  
            len(history)  # History length
        ])
        
        return features
    
    def predict_signal(self, features) -> Optional[SignalResult]:
        """ML inference using loaded model"""
        if self.model is None:
            return None
            
        try:
            # Feature shape validation against model expectation, if available
            expected = getattr(self.model, 'n_features_in_', None)
            if expected is not None:
                try:
                    flen = (int(features.shape[-1]) if hasattr(features, 'shape') else len(features))
                except Exception:
                    flen = None
                if flen is None or flen != int(expected):
                    # Explicit, safe handling: skip signal and surface clear error for observability
                    self._logger.error(
                        "ML feature length mismatch; skipping inference",
                        extra={
                            "strategy": self._strategy_name,
                            "expected": int(expected),
                            "actual": flen,
                        },
                    )
                    # Raise to allow upstream classification/metrics increment
                    raise ValueError(f"feature_mismatch: expected {expected} got {flen}")

            # Get prediction and probability
            prediction = self.model.predict([features])[0]
            probabilities = self.model.predict_proba([features])[0] if hasattr(self.model, 'predict_proba') else [0.5, 0.5]
            
            max_prob = max(probabilities)
            
            # Convert to trading signal with confidence in 0.0–1.0
            if prediction == 1 and max_prob > self.confidence_threshold:  # Buy
                return SignalResult(
                    signal_type="BUY",
                    confidence=float(max_prob),
                    quantity=self.position_size, 
                    price=Decimal(str(features[3])),  # Current price
                    reasoning=f"ML BUY prediction (confidence: {max_prob:.2f})",
                    metadata={
                        "ml_prediction": int(prediction),
                        "ml_confidence": float(max_prob),
                        "features": features.tolist() if HAS_NUMPY and hasattr(features, 'tolist') else list(features)
                    }
                )
            elif prediction == 0 and max_prob > self.confidence_threshold:  # Sell  
                return SignalResult(
                    signal_type="SELL",
                    confidence=float(max_prob),
                    quantity=self.position_size,
                    price=Decimal(str(features[3])),
                    reasoning=f"ML SELL prediction (confidence: {max_prob:.2f})",
                    metadata={
                        "ml_prediction": int(prediction),
                        "ml_confidence": float(max_prob),
                        "features": features.tolist() if HAS_NUMPY and hasattr(features, 'tolist') else list(features)
                    }
                )
        except Exception as e:
            # ML failed - return None (no signal)
            self._logger.error("ML prediction failed", exc_info=True, extra={
                "strategy": self._strategy_name
            })
        
        return None
    
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """Default implementation delegates to ML pipeline"""
        features = self.extract_features(tick, history) 
        return self.predict_signal(features)
    
    # IMPLEMENT REQUIRED StrategyProcessor METHODS
    def get_required_history_length(self) -> int:
        return self.lookback_periods
        
    def supports_instrument(self, token: int) -> bool:
        return True
        
    def get_strategy_name(self) -> str:
        return self._strategy_name


def create_ml_momentum_processor(config: Dict[str, Any]) -> MLMomentumProcessor:
    """Factory function compatible with existing strategy factory"""
    processor = MLMomentumProcessor(
        model_path=config.get("model_path", "strategies/models/momentum_v1.joblib"),
        lookback_periods=config.get("lookback_periods", 20),
        confidence_threshold=config.get("confidence_threshold", 0.6),
        position_size=config.get("position_size", 100)
    )

    return processor
