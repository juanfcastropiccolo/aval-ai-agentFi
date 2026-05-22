"""Tarea 17 + 18: criterios de aceptación AC-1..AC-9 del spec sobre el Engine real.

Cada test corresponde a un AC del spec y verifica veredicto + razón + rastro en
el audit trail. Usa un mandato realista con varias políticas a la vez.
"""

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
    Policy,
    RecipientAllowlist,
    SpendLimit,
    TokenInfo,
    Verdict,
)
from aval.core.audit import JsonlAuditStore
from aval.models import PolicyResult

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
USDC = "0x" + "a" * 40
GOOD = "0x" + "c" * 40
BAD = "0x" + "d" * 40


def _transfer(recipient: str, usdc: int) -> dict[str, object]:
    data = "0x" + "a9059cbb" + encode(["address", "uint256"], [recipient, usdc * 10**6]).hex()
    return {"to": USDC, "data": data}


def _engine(reviewer: object | None = None, audit: object | None = None) -> Engine:
    resolver = EVMResolver.from_tool_names({"send_tx"}, tokens={USDC: TokenInfo("USDC", 6)})
    return Engine(
        resolver,
        audit_store=audit or InMemoryAuditStore(),  # type: ignore[arg-type]
        human_reviewer=reviewer,  # type: ignore[arg-type]
    )


def _mandate(*policies: object, **overrides: object) -> Mandate:
    base: dict[str, object] = {
        "agent_id": "agent-1",
        "granted_by": "dev@example.com",
        "chains": ["ethereum"],
        "policies": list(policies),
        "token_decimals": {"USDC": 6},
        "expires_at": NOW + timedelta(days=1),
    }
    base.update(overrides)
    return Mandate(**base)  # type: ignore[arg-type]


def _realistic(*extra: object, **overrides: object) -> Mandate:
    return _mandate(
        SpendLimit(token="USDC", per_tx=Decimal("5000")),
        RecipientAllowlist(recipients={GOOD}),
        AllowedMethods(methods={"transfer"}),
        *extra,
        **overrides,
    )


def test_ac1_transfer_within_limit_is_allowed_and_audited() -> None:
    eng = _engine()
    decision = eng.evaluate("send_tx", _transfer(GOOD, 4000), _realistic(), now=NOW)
    assert decision.verdict is Verdict.ALLOW
    entries = eng.audit.entries()
    assert len(entries) == 1
    assert entries[0].verdict is Verdict.ALLOW


def test_ac2_transfer_over_per_tx_limit_denied_with_reason() -> None:
    eng = _engine()
    decision = eng.evaluate("send_tx", _transfer(GOOD, 6000), _realistic(), now=NOW)
    assert decision.verdict is Verdict.DENY
    assert "límite por transacción" in decision.reason
    assert eng.audit.entries()[0].verdict is Verdict.DENY


def test_ac3_recipient_not_in_allowlist_denied() -> None:
    eng = _engine()
    decision = eng.evaluate("send_tx", _transfer(BAD, 1000), _realistic(), now=NOW)
    assert decision.verdict is Verdict.DENY
    assert "destino no permitido" in decision.reason


def test_ac4_daily_limit_exceeded_by_accumulation_denied() -> None:
    eng = _engine()
    m = _mandate(
        SpendLimit(token="USDC", per_day=Decimal("20000")),
        AllowedMethods(methods={"transfer"}),
    )
    eng.evaluate("send_tx", _transfer(GOOD, 18000), m, now=NOW)  # gasto previo
    decision = eng.evaluate("send_tx", _transfer(GOOD, 4000), m, now=NOW)
    assert decision.verdict is Verdict.DENY
    assert "diario" in decision.reason


def test_ac5_sensitive_action_escalates_and_proceeds_only_if_approved() -> None:
    class EscalateOverThreshold(Policy):
        threshold: Decimal

        def evaluate(self, action, state, agent_id, now):  # type: ignore[no-untyped-def]
            if action.amount is not None and action.amount >= self.threshold:
                return PolicyResult.escalate(self.name, "monto sensible sobre umbral")
            return PolicyResult.allow(self.name)

    policies = (
        EscalateOverThreshold(threshold=Decimal("1000")),
        AllowedMethods(methods={"transfer"}),
    )

    approved = _engine(reviewer=AutoApproveReviewer(Verdict.ALLOW))
    d1 = approved.evaluate("send_tx", _transfer(GOOD, 2000), _mandate(*policies), now=NOW)
    assert d1.verdict is Verdict.ALLOW

    rejected = _engine(reviewer=AutoApproveReviewer(Verdict.DENY))
    d2 = rejected.evaluate("send_tx", _transfer(GOOD, 2000), _mandate(*policies), now=NOW)
    assert d2.verdict is Verdict.DENY


def test_ac6_non_money_action_passes_through_untouched() -> None:
    eng = _engine()
    decision = eng.evaluate("get_balance", {"account": GOOD}, _realistic(), now=NOW)
    assert decision.verdict is Verdict.ALLOW
    assert eng.audit.entries() == []  # no interfiere ni audita


def test_ac7_audit_tampering_is_detected(tmp_path: object) -> None:
    import json
    from pathlib import Path

    path = Path(tmp_path) / "audit.jsonl"  # type: ignore[arg-type]
    eng = _engine(audit=JsonlAuditStore(path))
    eng.evaluate("send_tx", _transfer(GOOD, 1000), _realistic(), now=NOW)
    eng.evaluate("send_tx", _transfer(GOOD, 2000), _realistic(), now=NOW)
    eng.evaluate("send_tx", _transfer(GOOD, 3000), _realistic(), now=NOW)
    assert JsonlAuditStore(path).verify() is True

    lines = path.read_text(encoding="utf-8").splitlines()
    mid = json.loads(lines[1])
    mid["reason"] = "ALTERADA"
    lines[1] = json.dumps(mid)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert JsonlAuditStore(path).verify() is False


def test_ac8_unresolvable_action_fails_closed() -> None:
    eng = _engine()
    data = "0x" + "deadbeef" + encode(["uint256"], [1]).hex()
    decision = eng.evaluate("send_tx", {"to": USDC, "data": data}, _realistic(), now=NOW)
    assert decision.verdict is Verdict.DENY
    assert "no resoluble" in decision.reason


def test_ac9_expired_mandate_denies_any_money_action() -> None:
    eng = _engine()
    m = _realistic(expires_at=NOW - timedelta(seconds=1))
    decision = eng.evaluate("send_tx", _transfer(GOOD, 100), m, now=NOW)
    assert decision.verdict is Verdict.DENY
    assert "expirado" in decision.reason
