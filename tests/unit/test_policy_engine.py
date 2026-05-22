"""Tarea 11: PolicyEngine — conjunción default-deny, precedencia DENY > ESCALATE > ALLOW."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from aval.core.policy_engine import PolicyEngine
from aval.core.state import InMemoryStateStore
from aval.models import Mandate, ProposedAction, Verdict
from aval.policies.allowed_methods import AllowedMethods
from aval.policies.recipient_allowlist import RecipientAllowlist
from aval.policies.spend_limit import SpendLimit

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
GOOD = "0x" + "c" * 40
BAD = "0x" + "d" * 40


def _mandate(*policies: object) -> Mandate:
    return Mandate(
        agent_id="agent-1",
        granted_by="dev",
        chains=["ethereum"],
        policies=list(policies),  # type: ignore[arg-type]
        token_decimals={"USDC": 6},
        expires_at=NOW + timedelta(days=1),
    )


def _action(amount: str = "100", recipient: str = GOOD, method: str = "transfer") -> ProposedAction:
    return ProposedAction(
        chain="ethereum",
        token="USDC",
        amount=Decimal(amount),
        recipient=recipient,
        target_contract=GOOD,
        method=method,
    )


def _eval(mandate: Mandate, action: ProposedAction):
    return PolicyEngine().evaluate(action, mandate, InMemoryStateStore(), NOW)


def test_all_policies_pass_allows() -> None:
    m = _mandate(
        SpendLimit(token="USDC", per_tx=Decimal("5000")),
        RecipientAllowlist(recipients={GOOD}),
        AllowedMethods(methods={"transfer"}),
    )
    assert _eval(m, _action()).verdict is Verdict.ALLOW


def test_one_failing_policy_denies_with_failed_policy() -> None:
    m = _mandate(
        SpendLimit(token="USDC", per_tx=Decimal("5000")),
        RecipientAllowlist(recipients={GOOD}),
    )
    decision = _eval(m, _action(recipient=BAD))
    assert decision.verdict is Verdict.DENY
    assert decision.failed_policy == "RecipientAllowlist"


def test_deny_takes_precedence_over_escalate() -> None:
    class AlwaysEscalate(SpendLimit):
        def evaluate(self, action, state, agent_id, now):  # type: ignore[no-untyped-def]
            from aval.models import PolicyResult

            return PolicyResult.escalate(self.name, "sensible")

    m = _mandate(
        AlwaysEscalate(token="USDC"),
        RecipientAllowlist(recipients={GOOD}),
    )
    # recipient malo → DENY debe ganar sobre el ESCALATE
    decision = _eval(m, _action(recipient=BAD))
    assert decision.verdict is Verdict.DENY


def test_escalate_when_no_deny() -> None:
    class AlwaysEscalate(SpendLimit):
        def evaluate(self, action, state, agent_id, now):  # type: ignore[no-untyped-def]
            from aval.models import PolicyResult

            return PolicyResult.escalate(self.name, "monto sensible")

    m = _mandate(AlwaysEscalate(token="USDC"), RecipientAllowlist(recipients={GOOD}))
    decision = _eval(m, _action())
    assert decision.verdict is Verdict.ESCALATE
    assert "sensible" in decision.reason


def test_default_deny_when_no_policy_applies() -> None:
    # Mandato solo con RecipientAllowlist; acción sin recipient (approve) → nada autoriza.
    m = _mandate(RecipientAllowlist(recipients={GOOD}))
    action = ProposedAction(chain="ethereum", token="USDC", method="approve")
    decision = _eval(m, action)
    assert decision.verdict is Verdict.DENY
    assert "default-deny" in decision.reason
