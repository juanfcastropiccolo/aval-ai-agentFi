"""Tarea 15: adaptador ADK — DENY impide ejecutar el tool y la razón llega al agente."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from eth_abi import encode

pytest.importorskip("google.adk")

from aval import (  # noqa: E402
    AllowedMethods,
    Engine,
    EVMResolver,
    InMemoryAuditStore,
    Mandate,
    RecipientAllowlist,
    TokenInfo,
)
from aval.adapters.adk import make_before_tool_callback  # noqa: E402

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
USDC = "0x" + "a" * 40
GOOD = "0x" + "c" * 40
BAD = "0x" + "d" * 40


def _transfer(recipient: str, usdc: int) -> dict[str, object]:
    data = "0x" + "a9059cbb" + encode(["address", "uint256"], [recipient, usdc * 10**6]).hex()
    return {"to": USDC, "data": data}


def _engine() -> Engine:
    resolver = EVMResolver.from_tool_names({"send_tx"}, tokens={USDC: TokenInfo("USDC", 6)})
    return Engine(resolver, audit_store=InMemoryAuditStore())


def _mandate() -> Mandate:
    return Mandate(
        agent_id="agent-1",
        granted_by="dev",
        chains=["ethereum"],
        policies=[RecipientAllowlist(recipients={GOOD}), AllowedMethods(methods={"transfer"})],
        token_decimals={"USDC": 6},
        expires_at=NOW + timedelta(days=3650),  # lejano: el callback usa el reloj real
    )


def _tool(name: str) -> object:
    return SimpleNamespace(name=name)  # el callback solo lee tool.name


def test_allow_returns_none_so_tool_runs() -> None:
    cb = make_before_tool_callback(_engine(), _mandate())
    result = cb(_tool("send_tx"), _transfer(GOOD, 100), None)  # type: ignore[arg-type]
    assert result is None  # None ⇒ ADK ejecuta el tool


def test_deny_short_circuits_with_reason() -> None:
    cb = make_before_tool_callback(_engine(), _mandate())
    result = cb(_tool("send_tx"), _transfer(BAD, 100), None)  # type: ignore[arg-type]
    assert result is not None  # dict ⇒ ADK NO ejecuta el tool real
    assert result["aval_denied"] is True
    assert result["verdict"] == "deny"
    assert "no permitido" in result["reason"]
    assert result["failed_policy"] == "RecipientAllowlist"


def test_non_financial_tool_passes_through() -> None:
    cb = make_before_tool_callback(_engine(), _mandate())
    result = cb(_tool("get_quote"), {"pair": "ETH/USDC"}, None)  # type: ignore[arg-type]
    assert result is None
