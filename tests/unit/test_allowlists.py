"""Tarea 9: políticas de allowlist — dentro/fuera de lista y no-aplicabilidad."""

from datetime import UTC, datetime
from decimal import Decimal

from aval.core.state import InMemoryStateStore
from aval.models import ProposedAction
from aval.policies.allowed_methods import AllowedMethods
from aval.policies.allowed_targets import AllowedTargets
from aval.policies.allowed_tokens import AllowedTokens
from aval.policies.recipient_allowlist import RecipientAllowlist

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
STORE = InMemoryStateStore()
GOOD = "0x" + "a" * 40
BAD = "0x" + "b" * 40


def _action(**kw: object) -> ProposedAction:
    defaults: dict[str, object] = {
        "chain": "ethereum",
        "token": "USDC",
        "amount": Decimal("1"),
        "recipient": GOOD,
        "target_contract": GOOD,
        "method": "transfer",
    }
    defaults.update(kw)
    return ProposedAction(**defaults)  # type: ignore[arg-type]


def _ev(policy, action):  # type: ignore[no-untyped-def]
    return policy.evaluate(action, STORE, "agent-1", NOW)


# --- AllowedTargets ---


def test_target_in_list_allows_case_insensitive() -> None:
    policy = AllowedTargets(contracts={GOOD.upper()})
    assert _ev(policy, _action(target_contract=GOOD)).passed is True


def test_target_out_of_list_denies() -> None:
    res = _ev(AllowedTargets(contracts={GOOD}), _action(target_contract=BAD))
    assert res.passed is False
    assert "no permitido" in res.reason


def test_target_not_applicable_when_absent() -> None:
    res = _ev(AllowedTargets(contracts={GOOD}), _action(target_contract=None))
    assert res.reason == "not applicable"


# --- RecipientAllowlist ---


def test_recipient_in_list_allows() -> None:
    assert _ev(RecipientAllowlist(recipients={GOOD}), _action(recipient=GOOD)).passed is True


def test_recipient_out_of_list_denies() -> None:
    res = _ev(RecipientAllowlist(recipients={GOOD}), _action(recipient=BAD))
    assert res.passed is False
    assert "destino no permitido" in res.reason


def test_recipient_not_applicable_for_approve() -> None:
    res = _ev(RecipientAllowlist(recipients={GOOD}), _action(recipient=None, method="approve"))
    assert res.reason == "not applicable"


# --- AllowedTokens ---


def test_token_in_list_allows() -> None:
    assert _ev(AllowedTokens(tokens={"USDC"}), _action(token="USDC")).passed is True


def test_token_out_of_list_denies() -> None:
    res = _ev(AllowedTokens(tokens={"USDC"}), _action(token="DAI"))
    assert res.passed is False


# --- AllowedMethods ---


def test_method_in_list_allows() -> None:
    assert _ev(AllowedMethods(methods={"transfer"}), _action(method="transfer")).passed is True


def test_method_out_of_list_denies() -> None:
    res = _ev(AllowedMethods(methods={"transfer"}), _action(method="approve"))
    assert res.passed is False
    assert "método no permitido" in res.reason
