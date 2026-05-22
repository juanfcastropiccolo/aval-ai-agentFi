"""Adaptador para LangChain / LangGraph (agent middleware ``wrap_tool_call``).

Intercepta la ejecución de cada tool de un agente LangChain:

- ALLOW → llama al ``handler`` y el tool se ejecuta normalmente.
- DENY  → **no** llama al ``handler`` (el tool no corre) y devuelve un
          ``ToolMessage`` de error con la razón legible, que vuelve al modelo (FR-9).

El core es síncrono (la decisión es CPU-bound, sin I/O); el middleware expone
tanto ``wrap_tool_call`` (sync) como ``awrap_tool_call`` (async), donde la
evaluación es la misma llamada síncrona y solo el ``handler`` se awaitea.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from aval.core.engine import Engine
from aval.models import Decision, Mandate

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langchain.agents.middleware.types import ToolCallRequest


class AvalMiddleware(AgentMiddleware):
    """Middleware de LangChain que aplica el enforcement de aval antes de cada tool.

    Úsalo así::

        from aval.adapters.langchain import AvalMiddleware

        agent = create_agent(model, tools=[...], middleware=[AvalMiddleware(engine, mandate)])
    """

    def __init__(self, engine: Engine, mandate: Mandate) -> None:
        super().__init__()
        self._engine = engine
        self._mandate = mandate

    def _decide(self, request: ToolCallRequest) -> Decision:
        call = request.tool_call
        return self._engine.evaluate(call["name"], call.get("args", {}), self._mandate)

    def _deny_message(self, request: ToolCallRequest, decision: Decision) -> ToolMessage:
        return ToolMessage(
            content=f"aval bloqueó esta acción: {decision.reason}",
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
            status="error",
            artifact={
                "aval_denied": True,
                "verdict": decision.verdict.value,
                "failed_policy": decision.failed_policy,
            },
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        decision = self._decide(request)
        if decision.is_allow:
            return handler(request)
        return self._deny_message(request, decision)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        decision = self._decide(request)  # síncrono, sin I/O
        if decision.is_allow:
            return await handler(request)
        return self._deny_message(request, decision)
