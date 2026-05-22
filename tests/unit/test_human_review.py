"""Tarea 12: HumanReviewer — ConsoleHumanReviewer con stdin mockeado."""

from decimal import Decimal

import pytest

from aval.core.human_review import AutoApproveReviewer, ConsoleHumanReviewer
from aval.models import Decision, ProposedAction, Verdict


def _decision() -> Decision:
    action = ProposedAction(
        chain="ethereum",
        token="USDC",
        amount=Decimal("10000"),
        recipient="0xabc",
        method="transfer",
    )
    return Decision.escalate("monto sensible", action=action)


def test_console_approves_on_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert ConsoleHumanReviewer().review(_decision()) is Verdict.ALLOW


def test_console_approves_on_localized_si(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "sí")
    assert ConsoleHumanReviewer().review(_decision()) is Verdict.ALLOW


def test_console_denies_on_no(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert ConsoleHumanReviewer().review(_decision()) is Verdict.DENY


def test_console_denies_on_empty_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert ConsoleHumanReviewer().review(_decision()) is Verdict.DENY


def test_auto_approve_reviewer() -> None:
    assert AutoApproveReviewer(Verdict.ALLOW).review(_decision()) is Verdict.ALLOW
    assert AutoApproveReviewer(Verdict.DENY).review(_decision()) is Verdict.DENY
