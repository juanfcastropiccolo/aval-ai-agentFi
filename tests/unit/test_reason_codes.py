"""Tarea 2: cada política y cada borde del Engine setea su reason_code (FR-8)."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from aval.core.engine import Engine
from aval.core.resolver import EVMResolver, TokenInfo
from aval.core.state import InMemoryStateStore, Period
from aval.models import Mandate, ProposedAction, ReasonCode, Verdict
from aval.policies import (
    AllowedMethods,
    AllowedTargets,
    AllowedTokens,
    RateLimit,
    RecipientAllowlist,
    SpendLimit,
    TimeWindow,
)

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
STORE = InMemoryStateStore()
GOOD = "0x" + "a" * 40
BAD = "0x" + "b" * 40


def _action(**kw: object) -> ProposedAction:
    base: dict[str, object] = {
        "chain": "ethereum",
        "token": "USDC",
        "amount": Decimal("100"),
        "recipient": GOOD,
        "target_contract": GOOD,
        "method": "transfer",
    }
    base.update(kw)
    return ProposedAction(**base)  # type: ignore[arg-type]


def _code(policy, action) -> ReasonCode:  # type: ignore[no-untyped-def]
    return policy.evaluate(action, STORE, "agent-1", NOW).reason_code


def test_policy_reason_codes() -> None:
    assert _code(SpendLimit(token="USDC", per_tx=Decimal("50")), _action(amount=Decimal("60"))) is (
        ReasonCode.SPEND_LIMIT_PER_TX
    )
    assert _code(RecipientAllowlist(recipients={GOOD}), _action(recipient=BAD)) is (
        ReasonCode.RECIPIENT_NOT_ALLOWED
    )
    assert _code(AllowedTargets(contracts={GOOD}), _action(target_contract=BAD)) is (
        ReasonCode.TARGET_NOT_ALLOWED
    )
    assert _code(AllowedTokens(tokens={"USDC"}), _action(token="DAI")) is (
        ReasonCode.TOKEN_NOT_ALLOWED
    )
    assert _code(AllowedMethods(methods={"transfer"}), _action(method="approve")) is (
        ReasonCode.METHOD_NOT_ALLOWED
    )
    assert _code(TimeWindow(start=time(9), end=time(17)), _action()) is ReasonCode.OK  # 12:00 ok
    assert _code(TimeWindow(start=time(1), end=time(2)), _action()) is ReasonCode.TIME_WINDOW
    rl = RateLimit(max_actions=0, per=Period.DAY)
    assert _code(rl, _action()) is ReasonCode.RATE_LIMIT


def _engine() -> Engine:
    resolver = EVMResolver.from_tool_names({"send_tx"}, tokens={GOOD: TokenInfo("USDC", 6)})
    return Engine(resolver)


def _mandate(**kw: object) -> Mandate:
    base: dict[str, object] = {
        "agent_id": "a",
        "granted_by": "dev",
        "policies": [AllowedMethods(methods={"transfer"})],
        "token_decimals": {"USDC": 6},
        "expires_at": NOW + timedelta(days=1),
    }
    base.update(kw)
    return Mandate(**base)  # type: ignore[arg-type]


def test_engine_border_codes() -> None:
    eng = _engine()
    # unresolvable: selector desconocido
    from eth_abi import encode

    data = "0x" + "deadbeef" + encode(["uint256"], [1]).hex()
    d = eng.evaluate("send_tx", {"to": GOOD, "data": data}, _mandate(), now=NOW)
    assert d.verdict is Verdict.DENY and d.reason_code is ReasonCode.UNRESOLVABLE

    # mandato expirado
    d2 = eng.evaluate(
        "send_tx",
        {"to": GOOD, "data": "0x" + "a9059cbb" + encode(["address", "uint256"], [GOOD, 1]).hex()},
        _mandate(expires_at=NOW - timedelta(seconds=1)),
        now=NOW,
    )
    assert d2.reason_code is ReasonCode.MANDATE_EXPIRED

    # revocado
    d3 = eng.evaluate(
        "send_tx",
        {"to": GOOD, "data": "0x" + "a9059cbb" + encode(["address", "uint256"], [GOOD, 1]).hex()},
        _mandate(revoked=True),
        now=NOW,
    )
    assert d3.reason_code is ReasonCode.MANDATE_REVOKED
