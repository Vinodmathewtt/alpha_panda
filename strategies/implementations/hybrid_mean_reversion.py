"""
Hybrid mean reversion strategy implementation
Combines rule-based mean reversion with ML predictions
"""

from typing import List, Dict, Any, Optional
from core.schemas.events import MarketTick as MarketData
from strategies.core.protocols import StrategyProcessor, SignalResult
from .mean_reversion import RulesMeanReversionProcessor
from .ml_mean_reversion import MLMeanReversionProcessor
from .hybrid_momentum import MajorityVotePolicy, ConservativePolicy  # Reuse decision policies
from core.logging import get_trading_logger_safe

logger = get_trading_logger_safe("hybrid_mean_reversion_strategy")


class HybridMeanReversionProcessor:
    """
    Hybrid mean reversion processor that combines rule-based and ML strategies
    Uses the same decision policies as hybrid momentum for consistency
    """
    
    def __init__(self, rules_config: Dict[str, Any], ml_config: Dict[str, Any], 
                 policy_type: str = "majority_vote", min_ml_confidence: float = 0.6):
        """
        Initialize hybrid mean reversion processor
        
        Args:
            rules_config: Configuration for rule-based mean reversion
            ml_config: Configuration for ML mean reversion
            policy_type: Decision policy ("majority_vote" or "conservative")
            min_ml_confidence: Minimum ML confidence for ML preference
        """
        self.rules_processor = RulesMeanReversionProcessor(**rules_config)
        self.ml_processor = MLMeanReversionProcessor(**ml_config)
        
        # Initialize decision policy (same as hybrid momentum)
        if policy_type == "conservative":
            self.policy = ConservativePolicy()
        else:
            self.policy = MajorityVotePolicy(min_ml_confidence=min_ml_confidence)
        
        self.policy_type = policy_type
        
        logger.info("Initialized hybrid mean reversion strategy",
                   policy=policy_type, min_ml_confidence=min_ml_confidence,
                   rules_config=rules_config, ml_config=ml_config)
    
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """
        Process tick through both rule-based and ML strategies, then combine results
        """
        try:
            # Get signals from both strategies
            rules_signal = self.rules_processor.process_tick(tick, history)
            ml_signal = None
            
            # Try ML signal with graceful degradation
            try:
                ml_signal = self.ml_processor.process_tick(tick, history)
            except Exception as e:
                logger.warning("ML processor failed, continuing with rules only", error=str(e))
            
            # Use decision policy to combine signals
            context = {
                "price": tick.last_price,
                "timestamp": tick.timestamp,
                "policy_type": self.policy_type
            }
            
            final_signal = self.policy.decide(rules_signal, ml_signal, context)
            
            if final_signal:
                logger.debug(
                    "Generated hybrid mean reversion signal",
                    signal_type=final_signal.signal_type,
                    confidence=final_signal.confidence,
                )
            
            return final_signal
            
        except Exception as e:
            logger.error("Error in hybrid mean reversion processing", error=str(e))
            return None
    
    def get_required_history_length(self) -> int:
        """Return maximum history length required by either strategy"""
        return max(
            self.rules_processor.get_required_history_length(),
            self.ml_processor.get_required_history_length()
        )
    
    def supports_instrument(self, token: int) -> bool:
        """Hybrid supports instrument if either strategy supports it"""
        return (self.rules_processor.supports_instrument(token) or 
                self.ml_processor.supports_instrument(token))
    
    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        return "hybrid_mean_reversion"


def create_hybrid_mean_reversion_processor(config: Dict[str, Any]) -> HybridMeanReversionProcessor:
    """
    Factory function to create hybrid mean reversion strategy processor
    
    Configuration parameters:
    - rules_config: Configuration dict for rule-based mean reversion
    - ml_config: Configuration dict for ML mean reversion  
    - policy_type: Decision policy ("majority_vote" or "conservative", default: "majority_vote")
    - min_ml_confidence: Minimum ML confidence for preference (default: 0.6)
    
    Example config:
    {
        "rules_config": {
            "lookback_periods": 20,
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "position_size": 100
        },
        "ml_config": {
            "lookback_periods": 20,
            "model_path": "models/mean_reversion.joblib"
        },
        "policy_type": "conservative",
        "min_ml_confidence": 0.7
    }
    """
    rules_config = config.get("rules_config", {
        "lookback_periods": 20,
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "position_size": 100
    })
    
    ml_config = config.get("ml_config", {
        "lookback_periods": 20,
        "model_path": "strategies/models/mean_reversion_model.joblib"
    })
    
    return HybridMeanReversionProcessor(
        rules_config=rules_config,
        ml_config=ml_config,
        policy_type=config.get("policy_type", "majority_vote"),
        min_ml_confidence=config.get("min_ml_confidence", 0.6)
    )
