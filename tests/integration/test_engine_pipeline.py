"""Tarea 14: Engine.evaluate end-to-end — los 5 caminos dejan la entrada de audit esperada."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from eth_abi import encode

from aval import (
    AllowedMethods,
    AutoApproveReviewer,
    Engine,
    EVMResolver,
    InMemoryAuditStore,
    Mandate,
    RecipientAllowlist,
    SpendLimit,
    TokenInfo,
    Verdict,
)
from aval.models import PolicyResult
from aval.policies import Policy

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
USDC = "0x" + "a" * 40
GOOD = "0x" + "c" * 40
BAD = "0x" + "d" * 40
TOKENS = {USDC: TokenInfo("USDC", 6)}


def _transfer_call(recipient: str, amount_usdc: int) -> dict[str, object]:
    raw = amount_usdc * 10**6  # USDC tiene 6 decimales
    data = "0x" + "a9059cbb" + encode(["address", "uint256"], [recipient, raw]).hex()
    return {"to": USDC, "data": data}


def _mandate(*policies: object, **overrides: object) -> Mandate:
    base: dict[str, object] = {
        "agent_id": "agent-1",
        "granted_by": "dev",
        "chains": ["ethereum"],
        "policies": list(policies),
        "token_decimals": {"USDC": 6},
        "expires_at": NOW + timedelta(days=1),
    }
    base.update(overrides)
    return Mandate(**base)  # type: ignore[arg-type]


def _engine(reviewer: object | None = None) -> Engine:
    resolver = EVMResolver.from_tool_names({"send_tx"}, tokens=TOKENS)
    return Engine(
        resolver,
        audit_store=InMemoryAuditStore(),
        human_reviewer=reviewer,  # type: ignore[arg-type]
    )


def test_allow_path_records_allow_entry() -> None:
    eng = _engine()
    m = _mandate(
        SpendLimit(token="USDC", per_tx=Decimal("5000")),
        RecipientAllowlist(recipients={GOOD}),
        AllowedMethods(methods={"transfer"}),
    )
    decision = eng.evaluate("send_tx", _transfer_call(GOOD, 4000), m, now=NOW)
    assert decision.verdict is Verdict.ALLOW
    assert decision.entry_hash is not None
    entries = eng.audit.entries()
    assert len(entries) == 1 and entries[0].verdict is Verdict.ALLOW


def test_deny_by_limit_records_and_does_not_commit() -> None:
    eng = _engine()
    m = _mandate(
        SpendLimit(token="USDC", per_tx=Decimal("5000")),
        AllowedMethods(methods={"transfer"}),
    )
    decision = eng.evaluate("send_tx", _transfer_call(GOOD, 6000), m, now=NOW)
    assert decision.verdict is Verdict.DENY
    assert "límite por transacción" in decision.reason
    assert eng.audit.entries()[0].verdict is Verdict.DENY


def test_deny_by_recipient() -> None:
    eng = _engine()
    m = _mandate(RecipientAllowlist(recipients={GOOD}), AllowedMethods(methods={"transfer"}))
    decision = eng.evaluate("send_tx", _transfer_call(BAD, 1000), m, now=NOW)
    assert decision.verdict is Verdict.DENY
    assert decision.failed_policy == "RecipientAllowlist"


def test_escalate_then_human_approves() -> None:
    class EscalateBig(Policy):
        threshold: Decimal

        def evaluate(self, action, state, agent_id, now):  # type: ignore[no-untyped-def]
            if action.amount is not None and action.amount >= self.threshold:
                return PolicyResult.escalate(self.name, "monto sensible")
            return PolicyResult.allow(self.name)

    eng = _engine(reviewer=AutoApproveReviewer(Verdict.ALLOW))
    m = _mandate(EscalateBig(threshold=Decimal("1000")), AllowedMethods(methods={"transfer"}))
    decision = eng.evaluate("send_tx", _transfer_call(GOOD, 5000), m, now=NOW)
    assert decision.verdict is Verdict.ALLOW
    assert "aprobado por humano" in decision.reason


def test_escalate_then_human_rejects() -> None:
    class AlwaysEscalate(Policy):
        def evaluate(self, action, state, agent_id, now):  # type: ignore[no-untyped-def]
            return PolicyResult.escalate(self.name, "revisar")

    eng = _engine(reviewer=AutoApproveReviewer(Verdict.DENY))
    m = _mandate(AlwaysEscalate())
    decision = eng.evaluate("send_tx", _transfer_call(GOOD, 1000), m, now=NOW)
    assert decision.verdict is Verdict.DENY
    assert "rechazado por humano" in decision.reason


def test_pass_through_for_non_financial_tool_is_not_audited() -> None:
    eng = _engine()
    m = _mandate(AllowedMethods(methods={"transfer"}))
    decision = eng.evaluate("get_quote", {"pair": "ETH/USDC"}, m, now=NOW)
    assert decision.verdict is Verdict.ALLOW
    assert eng.audit.entries() == []  # pass-through no deja entrada


def test_unresolvable_fails_closed_and_is_audited() -> None:
    eng = _engine()
    m = _mandate(AllowedMethods(methods={"transfer"}))
    data = "0x" + "deadbeef" + encode(["uint256"], [1]).hex()
    decision = eng.evaluate("send_tx", {"to": USDC, "data": data}, m, now=NOW)
    assert decision.verdict is Verdict.DENY
    assert "no resoluble" in decision.reason
    assert eng.audit.entries()[0].verdict is Verdict.DENY


def test_expired_mandate_denies() -> None:
    eng = _engine()
    m = _mandate(AllowedMethods(methods={"transfer"}), expires_at=NOW - timedelta(seconds=1))
    decision = eng.evaluate("send_tx", _transfer_call(GOOD, 1000), m, now=NOW)
    assert decision.verdict is Verdict.DENY
    assert "expirado" in decision.reason


def test_daily_accumulation_across_calls_denies_second() -> None:
    eng = _engine()
    m = _mandate(
        SpendLimit(token="USDC", per_day=Decimal("20000")),
        AllowedMethods(methods={"transfer"}),
    )
    first = eng.evaluate("send_tx", _transfer_call(GOOD, 18000), m, now=NOW)
    assert first.verdict is Verdict.ALLOW
    second = eng.evaluate("send_tx", _transfer_call(GOOD, 4000), m, now=NOW)
    assert second.verdict is Verdict.DENY  # 18k + 4k > 20k
    assert "diario" in second.reason


def test_audit_chain_is_valid_after_run() -> None:
    eng = _engine()
    m = _mandate(
        SpendLimit(token="USDC", per_tx=Decimal("5000")),
        AllowedMethods(methods={"transfer"}),
    )
    eng.evaluate("send_tx", _transfer_call(GOOD, 1000), m, now=NOW)
    eng.evaluate("send_tx", _transfer_call(GOOD, 9000), m, now=NOW)
    assert eng.audit.verify() is True
