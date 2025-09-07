"""
Hybrid momentum strategy implementation
Combines rule-based momentum with ML predictions using decision policies
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal
from core.schemas.events import MarketTick as MarketData
from strategies.core.protocols import StrategyProcessor, SignalResult, DecisionPolicy
from .momentum import RulesMomentumProcessor
from .ml_momentum import MLMomentumProcessor
from core.logging import get_trading_logger_safe

logger = get_trading_logger_safe("hybrid_momentum_strategy")


class MajorityVotePolicy:
    """
    Decision policy that combines rules and ML signals using majority voting
    Prefers ML when high confidence, falls back to rules otherwise
    """
    
    def __init__(self, min_ml_confidence: float = 0.6):
        self.min_ml_confidence = min_ml_confidence
        
    def decide(self, rules_signal: Optional[SignalResult], ml_signal: Optional[SignalResult], 
               context: Optional[Dict[str, Any]] = None) -> Optional[SignalResult]:
        """
        Combine rules and ML signals using majority voting logic
        
        Decision Logic:
        1. If both signals agree and are present -> combine with higher confidence
        2. If ML has high confidence (>threshold) -> prefer ML
        3. If only one signal present -> use that signal
        4. If signals conflict with low ML confidence -> prefer rules
        5. If no signals -> return None
        """
        # Case 1: Both signals present and agree
        if rules_signal and ml_signal and rules_signal.signal_type == ml_signal.signal_type:
            # Combine signals when they agree - boost confidence
            combined_confidence = min(1.0, (rules_signal.confidence + ml_signal.confidence) / 2 + 0.1)
            return SignalResult(
                signal_type=rules_signal.signal_type,
                confidence=combined_confidence,
                quantity=max(rules_signal.quantity, ml_signal.quantity),
                price=ml_signal.price,  # Use ML price as it may be more precise
                reasoning=f"Hybrid: Rules + ML agree ({rules_signal.signal_type})"
            )
        
        # Case 2: High confidence ML signal takes precedence
        if ml_signal and ml_signal.confidence >= self.min_ml_confidence:
            return SignalResult(
                signal_type=ml_signal.signal_type,
                confidence=ml_signal.confidence,
                quantity=ml_signal.quantity,
                price=ml_signal.price,
                reasoning=f"Hybrid: High confidence ML ({ml_signal.confidence:.2f})"
            )
        
        # Case 3: Fall back to rules signal (more stable)
        if rules_signal:
            return SignalResult(
                signal_type=rules_signal.signal_type,
                confidence=rules_signal.confidence,
                quantity=rules_signal.quantity,
                price=rules_signal.price,
                reasoning=f"Hybrid: Rules fallback ({rules_signal.reasoning})"
            )
        
        # Case 4: Low confidence ML only
        if ml_signal:
            return SignalResult(
                signal_type=ml_signal.signal_type,
                confidence=ml_signal.confidence * 0.8,  # Reduce confidence for low-conf ML
                quantity=ml_signal.quantity,
                price=ml_signal.price,
                reasoning=f"Hybrid: Low confidence ML ({ml_signal.confidence:.2f})"
            )
        
        # Case 5: No signals
        return None


class ConservativePolicy:
    """
    Conservative decision policy - only acts when both signals agree
    Higher precision, lower recall
    """
    
    def decide(self, rules_signal: Optional[SignalResult], ml_signal: Optional[SignalResult], 
               context: Optional[Dict[str, Any]] = None) -> Optional[SignalResult]:
        """Only generate signals when both rules and ML agree"""
        
        if (rules_signal and ml_signal and 
            rules_signal.signal_type == ml_signal.signal_type):
            # Both agree - combine with high confidence
            return SignalResult(
                signal_type=rules_signal.signal_type,
                confidence=min(1.0, (rules_signal.confidence + ml_signal.confidence) / 2 + 0.2),
                quantity=min(rules_signal.quantity, ml_signal.quantity),  # Conservative sizing
                price=rules_signal.price,
                reasoning=f"Conservative: Both signals agree ({rules_signal.signal_type})"
            )
        
        # No agreement = no signal (conservative approach)
        return None


class HybridMomentumProcessor:
    """
    Hybrid momentum processor that combines rule-based and ML momentum strategies
    Uses configurable decision policies to resolve conflicts
    """
    
    def __init__(self, rules_config: Dict[str, Any], ml_config: Dict[str, Any], 
                 policy_type: str = "majority_vote", min_ml_confidence: float = 0.6):
        """
        Initialize hybrid momentum processor
        
        Args:
            rules_config: Configuration for rule-based momentum
            ml_config: Configuration for ML momentum
            policy_type: Decision policy ("majority_vote" or "conservative")
            min_ml_confidence: Minimum ML confidence for ML preference
        """
        self.rules_processor = RulesMomentumProcessor(**rules_config)
        self.ml_processor = MLMomentumProcessor(**ml_config)
        
        # Initialize decision policy
        if policy_type == "conservative":
            self.policy = ConservativePolicy()
        else:
            self.policy = MajorityVotePolicy(min_ml_confidence=min_ml_confidence)
        
        self.policy_type = policy_type
        
        logger.info(f"Initialized hybrid momentum strategy",
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
                logger.warning(f"ML processor failed, continuing with rules only: {e}")
            
            # Use decision policy to combine signals
            context = {
                "price": tick.last_price,
                "timestamp": tick.timestamp,
                "policy_type": self.policy_type
            }
            
            final_signal = self.policy.decide(rules_signal, ml_signal, context)
            
            if final_signal:
                logger.debug(f"Generated hybrid signal: {final_signal.signal_type} "
                           f"(confidence: {final_signal.confidence:.2f})")
            
            return final_signal
            
        except Exception as e:
            logger.error(f"Error in hybrid momentum processing: {e}")
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
        return "hybrid_momentum"


def create_hybrid_momentum_processor(config: Dict[str, Any]) -> HybridMomentumProcessor:
    """
    Factory function to create hybrid momentum strategy processor
    
    Configuration parameters:
    - rules_config: Configuration dict for rule-based momentum
    - ml_config: Configuration dict for ML momentum  
    - policy_type: Decision policy ("majority_vote" or "conservative", default: "majority_vote")
    - min_ml_confidence: Minimum ML confidence for preference (default: 0.6)
    
    Example config:
    {
        "rules_config": {"lookback_periods": 20, "threshold": 0.01, "position_size": 100},
        "ml_config": {"lookback_periods": 20, "model_path": "models/momentum.joblib"},
        "policy_type": "majority_vote",
        "min_ml_confidence": 0.6
    }
    """
    rules_config = config.get("rules_config", {
        "lookback_periods": 20,
        "threshold": 0.01, 
        "position_size": 100
    })
    
    ml_config = config.get("ml_config", {
        "lookback_periods": 20,
        "model_path": "strategies/models/momentum_model.joblib"
    })
    
    return HybridMomentumProcessor(
        rules_config=rules_config,
        ml_config=ml_config,
        policy_type=config.get("policy_type", "majority_vote"),
        min_ml_confidence=config.get("min_ml_confidence", 0.6)
    )
