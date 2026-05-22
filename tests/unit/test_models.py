"""Tarea 3: modelos base de dominio — validación, helpers y round-trip JSON."""

from decimal import Decimal

from aval.models import Decision, PolicyResult, ProposedAction, Verdict


def _sample_action() -> ProposedAction:
    return ProposedAction(
        chain="ethereum",
        token="USDC",
        amount=Decimal("4000"),
        recipient="0xabc",
        target_contract="0xdef",
        method="transfer",
        selector="a9059cbb",
        raw={"tool": "erc20_transfer"},
    )


def test_proposed_action_json_round_trip() -> None:
    action = _sample_action()
    restored = ProposedAction.model_validate_json(action.model_dump_json())
    assert restored == action
    assert restored.amount == Decimal("4000")


def test_decision_json_round_trip_preserves_verdict_and_timestamp() -> None:
    decision = Decision.deny("límite por transacción excedido", failed_policy="SpendLimit")
    restored = Decision.model_validate_json(decision.model_dump_json())
    assert restored == decision
    assert restored.verdict is Verdict.DENY


def test_decision_verdict_helpers_are_mutually_exclusive() -> None:
    allow = Decision.allow()
    deny = Decision.deny("nope")
    escalate = Decision.escalate("revisar")

    assert (allow.is_allow, allow.is_deny, allow.is_escalate) == (True, False, False)
    assert (deny.is_allow, deny.is_deny, deny.is_escalate) == (False, True, False)
    assert (escalate.is_allow, escalate.is_deny, escalate.is_escalate) == (False, False, True)


def test_decision_with_entry_hash_is_immutable_copy() -> None:
    decision = Decision.allow()
    stamped = decision.with_entry_hash("deadbeef")
    assert decision.entry_hash is None
    assert stamped.entry_hash == "deadbeef"
    assert stamped.verdict is decision.verdict


def test_policy_result_not_applicable_passes_neutrally() -> None:
    result = PolicyResult.not_applicable("SpendLimit")
    assert result.passed is True
    assert result.verdict is Verdict.ALLOW

    denied = PolicyResult.deny("RecipientAllowlist", "destino no permitido")
    assert denied.passed is False
    assert denied.verdict is Verdict.DENY

    escalated = PolicyResult.escalate("SpendLimit", "monto sensible")
    assert escalated.passed is True
    assert escalated.verdict is Verdict.ESCALATE
