"""
ML-enhanced mean reversion strategy implementation
Uses composition architecture with ML inference
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
import logging

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

from ..core.protocols import MLStrategyProcessor, SignalResult
from ..ml_utils.model_loader import ModelLoader
from core.schemas.events import MarketTick as MarketData


class MLMeanReversionProcessor(MLStrategyProcessor):
    """ML mean reversion strategy"""

    def __init__(self, model_path: str, lookback_periods: int = 20,
                 confidence_threshold: float = 0.6, position_size: int = 100):
        self._logger = logging.getLogger("strategies.ml_mean_reversion")
        self.model_path = model_path
        self.lookback_periods = lookback_periods
        self.confidence_threshold = confidence_threshold
        self.position_size = position_size
        self.model = None
        self._strategy_name = "ml_mean_reversion"

    def load_model(self) -> bool:
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
        # Z-score and volatility features
        if not history:
            return [0.0, float(tick.last_price), 0.0, 0]

        if not HAS_NUMPY:
            prices = [float(h.last_price) for h in history[-self.lookback_periods:]]
            current_price = float(tick.last_price)
            if len(prices) < 2:
                return [0.0, current_price, 0.0, len(history)]
            mean_price = sum(prices) / len(prices)
            var = sum((p - mean_price) ** 2 for p in prices) / max(len(prices) - 1, 1)
            std = var ** 0.5
            z = (current_price - mean_price) / std if std > 0 else 0.0
            returns = [
                (prices[i] - prices[i - 1]) / prices[i - 1]
                for i in range(1, len(prices)) if prices[i - 1] != 0
            ]
            vol = (sum(r * r for r in returns) / max(len(returns), 1)) ** 0.5 if returns else 0.0
            return [z, current_price, vol, len(history)]

        prices = np.array([float(h.last_price) for h in history[-self.lookback_periods:]])
        current_price = float(tick.last_price)
        if prices.size < 2:
            return np.array([0.0, current_price, 0.0, len(history)])
        mean_price = np.mean(prices)
        std = np.std(prices, ddof=1) if prices.size > 1 else 0.0
        z = (current_price - mean_price) / std if std > 0 else 0.0
        returns = np.diff(prices) / prices[:-1]
        vol = float(np.std(returns)) if returns.size > 0 else 0.0
        return np.array([z, current_price, vol, len(history)])

    def predict_signal(self, features) -> Optional[SignalResult]:
        if self.model is None:
            return None
        try:
            # Feature shape validation if model provides expected feature count
            expected = getattr(self.model, 'n_features_in_', None)
            if expected is not None:
                try:
                    flen = (int(features.shape[-1]) if hasattr(features, 'shape') else len(features))
                except Exception:
                    flen = None
                if flen is None or flen != int(expected):
                    self._logger.error(
                        "ML feature length mismatch; skipping inference",
                        extra={
                            "strategy": self._strategy_name,
                            "expected": int(expected),
                            "actual": flen,
                        },
                    )
                    raise ValueError(f"feature_mismatch: expected {expected} got {flen}")
            prediction = self.model.predict([features])[0]
            probabilities = (
                self.model.predict_proba([features])[0]
                if hasattr(self.model, "predict_proba") else [0.5, 0.5]
            )
            max_prob = float(max(probabilities))
            if prediction == 1 and max_prob > self.confidence_threshold:
                return SignalResult(
                    signal_type="BUY",
                    confidence=max_prob,
                    quantity=self.position_size,
                    price=Decimal(str(features[1])),
                    reasoning=f"ML MR BUY (conf: {max_prob:.2f})",
                    metadata={"features": features.tolist() if HAS_NUMPY and hasattr(features, 'tolist') else list(features)}
                )
            elif prediction == 0 and max_prob > self.confidence_threshold:
                return SignalResult(
                    signal_type="SELL",
                    confidence=max_prob,
                    quantity=self.position_size,
                    price=Decimal(str(features[1])),
                    reasoning=f"ML MR SELL (conf: {max_prob:.2f})",
                    metadata={"features": features.tolist() if HAS_NUMPY and hasattr(features, 'tolist') else list(features)}
                )
        except Exception:
            self._logger.exception("ML inference failed", extra={"strategy": self._strategy_name})
        return None

    def get_required_history_length(self) -> int:
        return self.lookback_periods

    def supports_instrument(self, token: int) -> bool:
        return True

    def get_strategy_name(self) -> str:
        return self._strategy_name


def create_ml_mean_reversion_processor(config: Dict[str, Any]) -> MLMeanReversionProcessor:
    processor = MLMeanReversionProcessor(
        model_path=config.get("model_path", "strategies/models/mean_reversion_v1.joblib"),
        lookback_periods=config.get("lookback_periods", 20),
        confidence_threshold=config.get("confidence_threshold", 0.6),
        position_size=config.get("position_size", 100)
    )
    return processor
