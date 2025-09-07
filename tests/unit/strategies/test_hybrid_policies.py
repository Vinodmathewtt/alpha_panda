from decimal import Decimal

from strategies.core.protocols import SignalResult
from strategies.implementations.hybrid_momentum import MajorityVotePolicy, ConservativePolicy


def _sig(kind: str, conf: float, qty: int = 10) -> SignalResult:
    return SignalResult(
        signal_type=kind,
        confidence=conf,
        quantity=qty,
        price=Decimal("100.0"),
    )


def test_majority_vote_policy_prefers_agreement_and_high_conf_ml():
    p = MajorityVotePolicy(min_ml_confidence=0.6)

    # Agreement boosts confidence
    r = _sig("BUY", 0.5)
    m = _sig("BUY", 0.8)
    out = p.decide(r, m, {})
    assert out is not None and out.signal_type == "BUY"
    expected = min(1.0, (r.confidence + m.confidence) / 2 + 0.1)
    assert abs(out.confidence - expected) < 1e-6

    # High-confidence ML overrides conflicting rules
    r2 = _sig("SELL", 0.4)
    m2 = _sig("BUY", 0.9)
    out2 = p.decide(r2, m2, {})
    assert out2 is not None and out2.signal_type == "BUY"


def test_conservative_policy_requires_agreement():
    p = ConservativePolicy()

    # Conflict -> None
    r = _sig("BUY", 0.7)
    m = _sig("SELL", 0.9)
    out = p.decide(r, m, {})
    assert out is None

    # Agreement -> output with conservative sizing
    r2 = _sig("SELL", 0.6, qty=10)
    m2 = _sig("SELL", 0.7, qty=5)
    out2 = p.decide(r2, m2, {})
    assert out2 is not None and out2.signal_type == "SELL"
    assert out2.quantity == min(r2.quantity, m2.quantity)
