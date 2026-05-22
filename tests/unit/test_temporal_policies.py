"""Tarea 10: TimeWindow (bordes) y RateLimit (conteo por período)."""

from datetime import UTC, datetime, time
from decimal import Decimal

from aval.core.state import InMemoryStateStore, Period
from aval.models import ProposedAction
from aval.policies.rate_limit import RateLimit
from aval.policies.time_window import TimeWindow

STORE = InMemoryStateStore()
AGENT = "agent-1"


def _action() -> ProposedAction:
    return ProposedAction(chain="ethereum", token="USDC", amount=Decimal("1"))


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 22, hour, minute, tzinfo=UTC)


def _ev(policy, now):  # type: ignore[no-untyped-def]
    return policy.evaluate(_action(), STORE, AGENT, now)


# --- TimeWindow ---


def test_inside_window_allows() -> None:
    policy = TimeWindow(start=time(9, 0), end=time(17, 0))
    assert _ev(policy, _at(12)).passed is True


def test_outside_window_denies() -> None:
    policy = TimeWindow(start=time(9, 0), end=time(17, 0))
    assert _ev(policy, _at(20)).passed is False


def test_window_edges_are_inclusive() -> None:
    policy = TimeWindow(start=time(9, 0), end=time(17, 0))
    assert _ev(policy, _at(9, 0)).passed is True  # filo inicial
    assert _ev(policy, _at(17, 0)).passed is True  # filo final


def test_just_outside_edge_denies() -> None:
    policy = TimeWindow(start=time(9, 0), end=time(17, 0))
    assert _ev(policy, _at(8, 59)).passed is False
    assert _ev(policy, _at(17, 1)).passed is False


def test_overnight_window_crossing_midnight() -> None:
    policy = TimeWindow(start=time(22, 0), end=time(6, 0))
    assert _ev(policy, _at(23)).passed is True
    assert _ev(policy, _at(3)).passed is True
    assert _ev(policy, _at(12)).passed is False


# --- RateLimit ---


def test_rate_limit_allows_until_max_then_denies() -> None:
    store = InMemoryStateStore()
    policy = RateLimit(max_actions=3, per=Period.DAY)
    now = _at(10)
    for _ in range(3):
        assert policy.evaluate(_action(), store, AGENT, now).passed is True
        store.commit(AGENT, _action(), now)
    # cuarta acción del día: límite alcanzado
    assert policy.evaluate(_action(), store, AGENT, now).passed is False


def test_rate_limit_resets_next_period() -> None:
    store = InMemoryStateStore()
    policy = RateLimit(max_actions=1, per=Period.DAY)
    store.commit(AGENT, _action(), _at(10))
    assert policy.evaluate(_action(), store, AGENT, _at(10)).passed is False
    next_day = datetime(2026, 5, 23, 10, tzinfo=UTC)
    assert policy.evaluate(_action(), store, AGENT, next_day).passed is True
