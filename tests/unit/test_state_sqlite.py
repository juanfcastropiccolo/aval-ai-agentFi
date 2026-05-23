"""Tarea 3: SqliteStateStore — mismo contrato que in-memory + persistencia tras reabrir."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from aval.core.state import Period
from aval.core.state_sqlite import SqliteStateStore
from aval.models import ProposedAction

DAY = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)


def _action(amount: str, token: str = "USDC") -> ProposedAction:
    return ProposedAction(chain="ethereum", token=token, amount=Decimal(amount))


def test_spend_accumulates_and_counts(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "s.db")
    store.commit("a", _action("100"), DAY)
    store.commit("a", _action("250"), DAY + timedelta(hours=1))
    assert store.get_spend("a", "USDC", Period.DAY, DAY) == Decimal("350")
    assert store.get_action_count("a", Period.DAY, DAY) == 2


def test_resets_next_day_and_isolated_per_agent_and_token(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "s.db")
    store.commit("a", _action("100", token="USDC"), DAY)
    store.commit("a", _action("5", token="WETH"), DAY)
    assert store.get_spend("a", "USDC", Period.DAY, DAY + timedelta(days=1)) == Decimal("0")
    assert store.get_spend("a", "WETH", Period.DAY, DAY) == Decimal("5")
    assert store.get_spend("b", "USDC", Period.DAY, DAY) == Decimal("0")


def test_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "s.db"
    store = SqliteStateStore(path)
    store.commit("a", _action("18000"), DAY)
    store.close()

    reopened = SqliteStateStore(path)  # simula reinicio del proceso
    assert reopened.get_spend("a", "USDC", Period.DAY, DAY) == Decimal("18000")
    assert reopened.get_action_count("a", Period.DAY, DAY) == 1
