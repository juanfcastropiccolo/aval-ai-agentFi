"""Adaptador para Google ADK.

Engancha el ``before_tool_callback`` de un agente ADK: antes de que el agente
ejecute cualquier tool, aval evalúa la acción contra el mandato.

- ALLOW  → el callback devuelve ``None`` y el tool se ejecuta normalmente.
- DENY   → el callback devuelve un dict (la respuesta del tool), por lo que ADK
           **no ejecuta el tool real** y la razón legible vuelve al modelo para
           que pueda corregir (FR-9).

El escalamiento a humano se resuelve dentro de ``Engine.evaluate``; cuando el
callback recibe la decisión, ya es ALLOW o DENY.

Es un shim delgado: no toma ninguna decisión, solo traduce veredictos al idioma
de ADK (core agnóstico, adaptadores delgados — principio 3 de la Constitution).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aval.core.engine import Engine
from aval.models import Mandate

if TYPE_CHECKING:
    from google.adk.tools import BaseTool, ToolContext

ADKCallback = Callable[["BaseTool", dict[str, Any], "ToolContext"], dict[str, Any] | None]


def make_before_tool_callback(engine: Engine, mandate: Mandate) -> ADKCallback:
    """Crea un ``before_tool_callback`` de ADK que aplica el enforcement de aval.

    Úsalo así::

        from aval.adapters.adk import make_before_tool_callback

        agent = LlmAgent(
            ...,
            before_tool_callback=make_before_tool_callback(engine, mandate),
        )
    """

    def before_tool_callback(
        tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
    ) -> dict[str, Any] | None:
        decision = engine.evaluate(tool.name, args, mandate)
        if decision.is_allow:
            return None  # deja ejecutar el tool
        # Cortocircuito: el tool NO se ejecuta; la razón vuelve al modelo.
        return {
            "aval_denied": True,
            "verdict": decision.verdict.value,
            "reason": decision.reason,
            "failed_policy": decision.failed_policy,
        }

    return before_tool_callback
