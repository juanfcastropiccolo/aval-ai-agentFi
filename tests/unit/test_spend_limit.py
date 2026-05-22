"""Tarea 8: SpendLimit — bordes de límite exacto y acumulado que cruza el umbral."""

from datetime import UTC, datetime
from decimal import Decimal

from aval.core.state import InMemoryStateStore
from aval.models import ProposedAction, Verdict
from aval.policies.spend_limit import SpendLimit

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
AGENT = "agent-1"


def _action(amount: str | None, token: str = "USDC") -> ProposedAction:
    amt = Decimal(amount) if amount is not None else None
    return ProposedAction(chain="ethereum", token=token, amount=amt, recipient="0xc")


def _eval(policy: SpendLimit, action: ProposedAction, store: InMemoryStateStore | None = None):
    return policy.evaluate(action, store or InMemoryStateStore(), AGENT, NOW)


def test_not_applicable_for_other_token() -> None:
    res = _eval(SpendLimit(token="USDC", per_tx=Decimal("5000")), _action("1", token="WETH"))
    assert res.reason == "not applicable"
    assert res.passed is True


def test_under_per_tx_limit_allows() -> None:
    res = _eval(SpendLimit(token="USDC", per_tx=Decimal("5000")), _action("4000"))
    assert res.verdict is Verdict.ALLOW


def test_at_per_tx_limit_allows_inclusive() -> None:
    res = _eval(SpendLimit(token="USDC", per_tx=Decimal("5000")), _action("5000"))
    assert res.passed is True


def test_over_per_tx_limit_denies() -> None:
    res = _eval(SpendLimit(token="USDC", per_tx=Decimal("5000")), _action("6000"))
    assert res.passed is False
    assert "límite por transacción" in res.reason


def test_daily_accumulation_crossing_threshold_denies() -> None:
    store = InMemoryStateStore()
    store.commit(AGENT, _action("18000"), NOW)  # gasto previo del día
    policy = SpendLimit(token="USDC", per_day=Decimal("20000"))
    res = _eval(policy, _action("4000"), store)  # 18k + 4k = 22k > 20k
    assert res.passed is False
    assert "diario" in res.reason


def test_daily_accumulation_within_threshold_allows() -> None:
    store = InMemoryStateStore()
    store.commit(AGENT, _action("15000"), NOW)
    policy = SpendLimit(token="USDC", per_day=Decimal("20000"))
    res = _eval(policy, _action("4000"), store)  # 19k <= 20k
    assert res.passed is True


def test_missing_amount_on_matching_token_fails_closed() -> None:
    res = _eval(SpendLimit(token="USDC", per_tx=Decimal("5000")), _action(None))
    assert res.passed is False
    assert "no resuelto" in res.reason
