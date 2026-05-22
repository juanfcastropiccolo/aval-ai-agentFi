"""Tarea 4: Mandate — is_active (activo / expirado / revocado) y validación de decimales."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from aval.models import Mandate

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _mandate(**overrides: object) -> Mandate:
    base: dict[str, object] = {
        "agent_id": "agent-1",
        "granted_by": "dev@example.com",
        "chains": ["ethereum"],
        "token_decimals": {"USDC": 6, "WETH": 18},
        "expires_at": NOW + timedelta(days=1),
    }
    base.update(overrides)
    return Mandate(**base)  # type: ignore[arg-type]


def test_active_mandate_before_expiry() -> None:
    assert _mandate().is_active(NOW) is True


def test_expired_mandate_is_inactive() -> None:
    m = _mandate(expires_at=NOW - timedelta(seconds=1))
    assert m.is_active(NOW) is False


def test_expiry_is_evaluated_at_action_time() -> None:
    m = _mandate(expires_at=NOW + timedelta(hours=1))
    assert m.is_active(NOW) is True
    assert m.is_active(NOW + timedelta(hours=2)) is False


def test_revoked_mandate_is_inactive_even_before_expiry() -> None:
    m = _mandate(revoked=True)
    assert m.is_active(NOW) is False


def test_negative_token_decimals_rejected() -> None:
    with pytest.raises(ValidationError):
        _mandate(token_decimals={"USDC": -1})


def test_decimals_for_lookup() -> None:
    m = _mandate()
    assert m.decimals_for("USDC") == 6
    assert m.decimals_for("UNKNOWN") is None
