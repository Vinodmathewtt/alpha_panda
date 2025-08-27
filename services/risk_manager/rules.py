# Risk management rules
from typing import Dict, Any, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from core.schemas.events import SignalType


class RiskRule:
    """Base class for risk rules"""
    
    def __init__(self, name: str):
        self.name = name
        
    def check(self, signal: Dict[str, Any], risk_state: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if signal passes this risk rule
        
        Returns:
            Tuple[bool, str]: (passes, reason)
        """
        raise NotImplementedError


class MaxPositionSizeRule(RiskRule):
    """Limit maximum position size per instrument"""
    
    def __init__(self, max_position: int = 1000):
        super().__init__("MaxPositionSize")
        self.max_position = max_position
        
    def check(self, signal: Dict[str, Any], risk_state: Dict[str, Any]) -> Tuple[bool, str]:
        instrument_token = signal.get("instrument_token")
        quantity = signal.get("quantity", 0)
        
        current_position = risk_state.get("positions", {}).get(str(instrument_token), 0)
        
        # FIX: Compare with enum value (string) to avoid type mismatch
        if signal.get("signal_type") == SignalType.BUY.value:
            new_position = current_position + quantity
        else:  # SELL
            new_position = current_position - quantity
            
        if abs(new_position) > self.max_position:
            return False, f"Position size {abs(new_position)} exceeds maximum {self.max_position}"
            
        return True, "Position size within limits"


class MaxDailyTradesRule(RiskRule):
    """Limit maximum trades per day per strategy"""
    
    def __init__(self, max_daily_trades: int = 50):
        super().__init__("MaxDailyTrades")
        self.max_daily_trades = max_daily_trades
        
    def check(self, signal: Dict[str, Any], risk_state: Dict[str, Any]) -> Tuple[bool, str]:
        strategy_id = signal.get("strategy_id")
        
        # Count today's trades for this strategy
        today = datetime.now().date()
        daily_trades_key = f"daily_trades_{strategy_id}_{today}"
        
        daily_trades = risk_state.get(daily_trades_key, 0)
        
        if daily_trades >= self.max_daily_trades:
            return False, f"Daily trade limit {self.max_daily_trades} exceeded for strategy {strategy_id}"
            
        return True, "Daily trade limit not exceeded"


class PriceLimitRule(RiskRule):
    """Ensure trading price is within reasonable bounds"""
    
    def __init__(self, max_price_deviation: float = 0.10):  # 10%
        super().__init__("PriceLimit")
        self.max_price_deviation = max_price_deviation
        
    def check(self, signal: Dict[str, Any], risk_state: Dict[str, Any]) -> Tuple[bool, str]:
        signal_price = signal.get("price")
        instrument_token = signal.get("instrument_token")
        
        if not signal_price:
            return True, "No price specified in signal"
            
        # Get recent market price from risk state
        recent_price_key = f"recent_price_{instrument_token}"
        recent_price = risk_state.get(recent_price_key)
        
        if not recent_price:
            return True, "No recent price available for comparison"
            
        signal_price = float(signal_price)
        recent_price = float(recent_price)
        
        if recent_price == 0:
            return True, "Cannot validate against zero price"
            
        price_deviation = abs(signal_price - recent_price) / recent_price
        
        if price_deviation > self.max_price_deviation:
            return False, f"Price deviation {price_deviation:.2%} exceeds limit {self.max_price_deviation:.2%}"
            
        return True, "Price within acceptable deviation"


class RiskRuleEngine:
    """Engine for evaluating all risk rules"""
    
    def __init__(self):
        self.rules = [
            MaxPositionSizeRule(max_position=1000),
            MaxDailyTradesRule(max_daily_trades=50),
            PriceLimitRule(max_price_deviation=0.10)
        ]
        
    def evaluate_signal(self, signal: Dict[str, Any], risk_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate signal against all risk rules
        
        Returns:
            Dict with validation results
        """
        results = {}
        all_passed = True
        rejection_reasons = []
        
        for rule in self.rules:
            passed, reason = rule.check(signal, risk_state)
            results[rule.name] = passed
            
            if not passed:
                all_passed = False
                rejection_reasons.append(f"{rule.name}: {reason}")
                
        return {
            "passed": all_passed,
            "rule_results": results,
            "rejection_reasons": rejection_reasons
        }