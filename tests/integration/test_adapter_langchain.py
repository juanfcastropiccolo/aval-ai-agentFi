"""Tarea 16: adaptador LangChain — DENY bloquea de verdad, pass-through no interfiere."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from eth_abi import encode

pytest.importorskip("langchain")

from aval import (  # noqa: E402
    AllowedMethods,
    Engine,
    EVMResolver,
    InMemoryAuditStore,
    Mandate,
    RecipientAllowlist,
    TokenInfo,
)
from aval.adapters.langchain import AvalMiddleware  # noqa: E402

NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
USDC = "0x" + "a" * 40
GOOD = "0x" + "c" * 40
BAD = "0x" + "d" * 40


def _transfer(recipient: str, usdc: int) -> dict[str, object]:
    data = "0x" + "a9059cbb" + encode(["address", "uint256"], [recipient, usdc * 10**6]).hex()
    return {"to": USDC, "data": data}


def _middleware() -> AvalMiddleware:
    resolver = EVMResolver.from_tool_names({"send_tx"}, tokens={USDC: TokenInfo("USDC", 6)})
    engine = Engine(resolver, audit_store=InMemoryAuditStore())
    mandate = Mandate(
        agent_id="agent-1",
        granted_by="dev",
        chains=["ethereum"],
        policies=[RecipientAllowlist(recipients={GOOD}), AllowedMethods(methods={"transfer"})],
        token_decimals={"USDC": 6},
        expires_at=NOW + timedelta(days=3650),  # lejano: el middleware usa el reloj real
    )
    return AvalMiddleware(engine, mandate)


def _request(tool: str, args: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        tool_call={"name": tool, "args": args, "id": "call-1"},
        tool=None,
        state=None,
        runtime=None,
    )


def test_allow_invokes_handler() -> None:
    calls: list[object] = []

    def handler(req: object) -> str:
        calls.append(req)
        return "tool-ejecutado"

    result = _middleware().wrap_tool_call(_request("send_tx", _transfer(GOOD, 100)), handler)
    assert result == "tool-ejecutado"
    assert len(calls) == 1  # el tool corrió


def test_deny_does_not_invoke_handler() -> None:
    calls: list[object] = []

    def handler(req: object) -> str:
        calls.append(req)
        return "tool-ejecutado"

    result = _middleware().wrap_tool_call(_request("send_tx", _transfer(BAD, 100)), handler)
    assert calls == []  # el handler NUNCA se llamó → el tool no se ejecutó
    assert result.status == "error"
    assert "aval bloqueó" in result.content
    assert result.artifact["aval_denied"] is True


def test_pass_through_invokes_handler() -> None:
    calls: list[object] = []

    def handler(req: object) -> str:
        calls.append(req)
        return "quote"

    result = _middleware().wrap_tool_call(_request("get_quote", {"pair": "ETH/USDC"}), handler)
    assert result == "quote"
    assert len(calls) == 1


def test_async_deny_does_not_invoke_handler() -> None:
    calls: list[object] = []

    async def handler(req: object) -> str:
        calls.append(req)
        return "tool-ejecutado"

    async def run() -> object:
        return await _middleware().awrap_tool_call(
            _request("send_tx", _transfer(BAD, 100)), handler
        )

    result = asyncio.run(run())
    assert calls == []
    assert result.status == "error"
