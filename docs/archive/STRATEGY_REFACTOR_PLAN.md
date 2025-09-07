# Strategy Module Refactoring Plan

## Executive Summary

Based on comprehensive analysis of the existing strategy modules (`services/strategy_runner` and `strategies`), the current architecture suffers from **ML-first bias** that prevents true strategy agnosticism. While the codebase has successfully migrated to composition-based patterns, two critical bottlenecks remain:

1. **Hard ML enforcement in core factory** - `strategies/core/factory.py` (lines 38-40) refuses processors without ML methods
2. **ML-only registry in service factory** - `services/strategy_runner/factory.py` (lines 25-44) only registers ML implementations

This plan provides a surgical, risk-minimized approach to achieve true strategy agnosticism while preserving the excellent composition architecture already in place.

---

## Current State Analysis

### ✅ What's Working Well

1. **Composition Architecture**: Successfully implemented protocol-based composition
2. **Event-Driven Pipeline**: Clean separation between strategy execution and signal emission  
3. **ML Infrastructure**: Robust ML model loading with graceful degradation
4. **Performance Optimization**: O(1) instrument-to-strategy routing
5. **Observability**: Comprehensive metrics and tracing

### ❌ Critical Issues Identified

| Component | Issue | Impact | Lines |
|-----------|--------|--------|--------|
| `strategies/core/factory.py` | Hard ML method requirement | Blocks all non-ML strategies | 38-40 |
| `services/strategy_runner/factory.py` | ML-only strategy registry | Only ML strategies can be loaded | 25-44 |
| `services/strategy_runner/service.py` | ML-biased validation logic | Startup failures for non-ML strategies | 140-162 |
| Strategy Implementations | Only ML variants exist | No rule-based alternatives available | N/A |

### 🔍 Architecture Lock-in Details

**strategies/core/factory.py** - Lines 38-40:
```python
for req in ("load_model", "extract_features", "predict_signal"):
    if not hasattr(processor, req):
        raise ValueError(f"Processor is not ML-ready; missing method: {req}")
```
This **hard gate** prevents any non-ML strategy from being created.

**services/strategy_runner/factory.py** - Lines 25-44:
- Registry contains **only ML strategies**
- Migration mapping forces legacy names → ML processors  
- No registration path for pure rule-based strategies

---

## Refactoring Strategy

### Design Principles

1. **Capability-based Architecture**: Use duck typing and protocol mixins instead of inheritance
2. **Backward Compatibility**: All existing ML strategies continue to work unchanged
3. **Minimal Risk**: Surgical changes with clear rollback paths
4. **Strategy Agnosticism**: Runner treats ML, rules, and hybrid strategies identically

### Target Architecture

```
StrategyProcessor (Protocol)
├── process_tick() [REQUIRED]
├── get_required_history_length() [REQUIRED] 
├── supports_instrument() [REQUIRED]
└── get_strategy_name() [REQUIRED]

MLCapable (Protocol Mixin) [OPTIONAL]
├── load_model() 
├── extract_features()
└── predict_signal()

DecisionPolicy (Protocol) [OPTIONAL]
└── decide(rules_signal, ml_signal, context)
```

**Key Insight**: Runner always calls `process_tick()`. ML strategies implement it by delegating to their ML pipeline. Rules strategies implement it with indicator logic. Hybrid strategies combine both approaches.

---

## Implementation Plan

### Phase 1: Core Protocol Enhancement (Low Risk)

**File: `strategies/core/protocols.py`**

Add capability-based protocols without breaking existing contracts:

```python
# Add these protocols alongside existing StrategyProcessor
class MLCapable(Protocol):
    """Optional ML capability mixin"""
    def load_model(self) -> bool: ...
    def extract_features(self, tick: MarketData, history: List[MarketData]) -> Any: ...
    def predict_signal(self, features: Any) -> Optional[SignalResult]: ...

class DecisionPolicy(Protocol):
    """Policy for combining multiple signals"""
    def decide(self, rules_signal: Optional[SignalResult], ml_signal: Optional[SignalResult], 
               context: Dict[str, Any] | None = None) -> Optional[SignalResult]: ...
```

**Risk**: None - purely additive changes

### Phase 2: Remove ML Gates (Medium Risk)

**File: `strategies/core/factory.py`**

Replace hard ML enforcement with optional capability detection:

```python
# REMOVE lines 38-40 (hard ML gate)
# REPLACE with:
if hasattr(processor, "load_model"):
    try:
        loaded = processor.load_model()
        if not loaded:
            logger.warning(f"ML model failed to load for {config.strategy_type}")
    except Exception as e:
        logger.warning(f"ML model loading error: {e}")
```

**File: `services/strategy_runner/factory.py`**

Expand registry to include rule-based strategies:

```python
STRATEGY_REGISTRY = {
    # Keep existing ML strategies
    "ml_momentum": "strategies.implementations.ml_momentum",
    "ml_mean_reversion": "strategies.implementations.ml_mean_reversion", 
    "ml_breakout": "strategies.implementations.ml_breakout",
    
    # Add rules-based strategies
    "momentum": "strategies.implementations.momentum",
    "mean_reversion": "strategies.implementations.mean_reversion",
    "rsi": "strategies.implementations.rsi",
    
    # Add hybrid strategies
    "hybrid_momentum": "strategies.implementations.hybrid_momentum",
}

# REMOVE forced ML migration mapping (lines 37-44)
MIGRATION_MAPPING = {}  # Let users explicitly choose strategy types
```

**Risk**: Medium - Changes strategy loading behavior, but maintains backward compatibility

### Phase 3: Add Rule-Based Implementations (Low Risk)

Create lightweight rule-based strategy implementations:

**File: `strategies/implementations/momentum.py`**
```python
class RulesMomentumProcessor:
    def __init__(self, lookback_periods: int = 20, threshold: float = 0.01, position_size: int = 100):
        self.lookback = lookback_periods
        self.threshold = threshold
        self.qty = position_size

    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        if len(history) < self.lookback:
            return None
        start_price = float(history[-self.lookback].last_price)
        current_price = float(tick.last_price)
        change = (current_price - start_price) / start_price if start_price != 0 else 0
        
        if change > self.threshold:
            return SignalResult("BUY", confidence=min(1.0, abs(change) * 5.0), 
                              quantity=self.qty, price=Decimal(str(current_price)),
                              reasoning=f"Momentum: +{change:.2%}")
        elif change < -self.threshold:
            return SignalResult("SELL", confidence=min(1.0, abs(change) * 5.0),
                              quantity=self.qty, price=Decimal(str(current_price)),
                              reasoning=f"Momentum: {change:.2%}")
        return None

    def get_required_history_length(self) -> int: return self.lookback
    def supports_instrument(self, token: int) -> bool: return True  
    def get_strategy_name(self) -> str: return "momentum"

def create_rules_momentum_processor(config: Dict[str, Any]) -> RulesMomentumProcessor:
    return RulesMomentumProcessor(
        lookback_periods=config.get("lookback_periods", 20),
        threshold=config.get("threshold", 0.01),
        position_size=config.get("position_size", 100)
    )
```

**Risk**: None - purely additive implementations

### Phase 4: Add Hybrid Strategies (Medium Risk)

**File: `strategies/implementations/hybrid_momentum.py`**
```python
class HybridProcessor:
    def __init__(self, rules_proc: StrategyProcessor, ml_proc: StrategyProcessor, policy: DecisionPolicy):
        self.rules = rules_proc
        self.ml = ml_proc  
        self.policy = policy

    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        rules_signal = self.rules.process_tick(tick, history)
        ml_signal = self.ml.process_tick(tick, history)
        return self.policy.decide(rules_signal, ml_signal, {"price": tick.last_price})

class MajorityVotePolicy:
    def decide(self, rules_signal, ml_signal, context=None) -> Optional[SignalResult]:
        if rules_signal and ml_signal and rules_signal.signal_type == ml_signal.signal_type:
            # Combine signals when they agree
            return SignalResult(rules_signal.signal_type, 
                              confidence=(rules_signal.confidence + ml_signal.confidence) / 2,
                              quantity=max(rules_signal.quantity, ml_signal.quantity),
                              price=ml_signal.price, reasoning="rules+ml agree")
        elif ml_signal and ml_signal.confidence >= 0.6:
            return ml_signal  # High-confidence ML takes precedence
        return rules_signal  # Fall back to rules
```

**Risk**: Medium - New composition patterns, but isolated to hybrid strategies

### Phase 5: Update Service Logic (High Risk)

**File: `services/strategy_runner/service.py`**

Make ML validation optional rather than required:

```python
# REPLACE lines 140-162 with capability-aware loading:
async def _load_strategies(self):
    for config in strategy_configs:
        try:
            executor = StrategyFactory.create_strategy(...)
            
            # Optional ML capability validation
            loaded = True
            if self._has_ml_capability(executor):
                loaded = await self._validate_ml_capability(executor, config.id)
                if loaded:
                    ml_models_loaded += 1
                else:
                    ml_models_failed += 1
                    # Continue loading - don't skip non-ML strategies
            
            if loaded:  # Register strategy regardless of ML status
                self.strategy_executors[config.id] = executor
                # ... rest of registration logic
```

**Risk**: High - Changes core service loading behavior

---

## Risk Assessment & Mitigation

### High Risk Changes
- **Service loading logic** modifications in `strategy_runner/service.py`
- **Database schema** changes (if adding strategy type columns)

**Mitigation**: 
- Feature flags for gradual rollout
- Comprehensive integration tests
- Database migration scripts with rollback procedures

### Medium Risk Changes  
- **Factory registry** expansion
- **Hybrid strategy** implementations

**Mitigation**:
- Maintain parallel registries during transition
- Extensive unit testing for new strategy types

### Low Risk Changes
- **Protocol additions** (purely additive)
- **Rule-based implementations** (isolated new code)

**Mitigation**: Standard code review and unit testing

---

## Migration Timeline

### Week 1-2: Foundation
- [ ] Add capability protocols (`MLCapable`, `DecisionPolicy`)  
- [ ] Create rule-based strategy implementations
- [ ] Update core factory to remove ML gates
- [ ] Comprehensive unit testing

### Week 3-4: Integration
- [ ] Expand service factory registry
- [ ] Add hybrid strategy implementations  
- [ ] Update service loading logic
- [ ] Integration testing with test environment

### Week 5: Validation & Deployment
- [ ] Performance testing (ensure <50ms latency targets)
- [ ] End-to-end testing with paper broker
- [ ] Production deployment with feature flags
- [ ] Monitor ML vs rules performance metrics

---

## Success Criteria

### Functional Requirements
- [ ] Rules-based strategies can be loaded and execute without ML dependencies
- [ ] Hybrid strategies correctly combine rules and ML signals  
- [ ] All existing ML strategies continue to work unchanged
- [ ] Performance targets maintained (<50ms end-to-end latency)

### Observability Requirements
- [ ] Strategy type metrics (rules/ML/hybrid) in Prometheus
- [ ] Separate error tracking for different strategy types
- [ ] Performance comparison dashboards

### Operational Requirements  
- [ ] Zero-downtime deployment capability
- [ ] Rollback procedures for each phase
- [ ] Configuration validation for new strategy types

---

## Database Schema Changes

### New Columns for `strategy_configurations` Table
```sql
ALTER TABLE strategy_configurations 
ADD COLUMN active_brokers TEXT[] DEFAULT ARRAY['paper'];

ALTER TABLE strategy_configurations
ADD COLUMN validator_type TEXT DEFAULT 'standard';
```

### New Strategy Configuration Examples
```yaml
# Rules-based momentum
strategy_name: 'NIFTY Rules Momentum'
strategy_type: 'momentum'  # Not 'ml_momentum'
parameters:
  lookback_periods: 20
  threshold: 0.012
  position_size: 100
brokers: ['paper']
instruments: [256265]

# Hybrid strategy  
strategy_name: 'NIFTY Hybrid'
strategy_type: 'hybrid_momentum'
parameters:
  lookback_periods: 20
  threshold: 0.01
  model_path: 'models/momentum.onnx'
  min_ml_confidence: 0.6
```

---

## Testing Strategy

### Unit Tests (Phase 1-3)
- Rule-based strategy signal generation
- Hybrid policy decision logic  
- Factory registration for new strategy types
- Protocol compliance verification

### Integration Tests (Phase 4)  
- End-to-end signal generation for all strategy types
- Multi-broker routing with different strategy types
- ML model failure graceful degradation
- Database loading with new schema

### Performance Tests (Phase 5)
- Latency comparison: rules vs ML vs hybrid
- Memory usage under sustained load
- Throughput testing with mixed strategy types

---

## Monitoring & Alerting

### New Metrics
```python
# Strategy type distribution
strategy_types_total{type="rules|ml|hybrid", broker="paper|zerodha"}

# Performance comparison
strategy_processing_duration_ms{type="rules|ml|hybrid"} 

# Error rates by strategy type
strategy_errors_total{type="rules|ml|hybrid", error_category="processing|ml_inference"}
```

### Alert Conditions
- Rules strategy error rate >5% (should be nearly 0%)
- ML inference failures >20% (degraded but acceptable)
- Hybrid policy decision time >10ms (composition overhead)

---

## Rollback Procedures

### Emergency Rollback (< 5 minutes)
1. Disable new strategy types via feature flag
2. Revert to ML-only registry in service factory
3. Restart services with previous configuration

### Planned Rollback (< 30 minutes)  
1. Database migration rollback scripts
2. Code deployment rollback to previous version
3. Configuration file updates
4. Service restart with health checks

---

## Post-Implementation Validation

### Week 1 Post-Deployment
- [ ] Verify all strategy types loading correctly
- [ ] Compare signal generation rates vs baseline
- [ ] Monitor error rates and performance metrics
- [ ] Validate observability dashboards

### Week 2-4 Monitoring
- [ ] Performance comparison analysis
- [ ] ML vs rules signal effectiveness analysis  
- [ ] System stability under load
- [ ] User acceptance of new strategy configuration options

---

## Conclusion

This refactoring plan transforms the Alpha Panda strategy architecture from ML-first to truly strategy-agnostic while preserving all existing functionality and performance characteristics. The phased approach minimizes risk through surgical changes, comprehensive testing, and robust rollback procedures.

The end result will be a flexible, composable strategy system that supports rules-based, ML-enhanced, and hybrid trading strategies through a unified protocol-based architecture - exactly what the recommendation documents envisioned.

**Estimated Timeline**: 5 weeks  
**Risk Level**: Medium  
**Expected Benefits**: 
- Strategy diversity (rules, ML, hybrid)
- Reduced ML infrastructure dependencies
- Improved testing and development velocity
- Enhanced system flexibility and maintainability