"""Tarea 5: StateStore — acumulado de gasto y conteo por ventana, aislamiento por agente."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from aval.core.state import InMemoryStateStore, Period
from aval.models import ProposedAction

DAY = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
NEXT_DAY = DAY + timedelta(days=1)


def _action(amount: str, token: str = "USDC", agent: str = "a") -> ProposedAction:
    return ProposedAction(chain="ethereum", token=token, amount=Decimal(amount))


def test_spend_accumulates_within_same_day() -> None:
    store = InMemoryStateStore()
    store.commit("a", _action("100"), DAY)
    store.commit("a", _action("250"), DAY + timedelta(hours=2))
    assert store.get_spend("a", "USDC", Period.DAY, DAY) == Decimal("350")


def test_spend_resets_in_next_day_bucket() -> None:
    store = InMemoryStateStore()
    store.commit("a", _action("100"), DAY)
    assert store.get_spend("a", "USDC", Period.DAY, NEXT_DAY) == Decimal("0")


def test_action_count_per_day() -> None:
    store = InMemoryStateStore()
    store.commit("a", _action("1"), DAY)
    store.commit("a", _action("1"), DAY)
    store.commit("a", _action("1"), DAY)
    assert store.get_action_count("a", Period.DAY, DAY) == 3


def test_spend_isolated_per_token() -> None:
    store = InMemoryStateStore()
    store.commit("a", _action("100", token="USDC"), DAY)
    store.commit("a", _action("5", token="WETH"), DAY)
    assert store.get_spend("a", "USDC", Period.DAY, DAY) == Decimal("100")
    assert store.get_spend("a", "WETH", Period.DAY, DAY) == Decimal("5")


def test_state_isolated_per_agent() -> None:
    store = InMemoryStateStore()
    store.commit("a", _action("100"), DAY)
    assert store.get_spend("b", "USDC", Period.DAY, DAY) == Decimal("0")
    assert store.get_action_count("b", Period.DAY, DAY) == 0
