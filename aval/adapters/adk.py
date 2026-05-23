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
            "reason_code": decision.reason_code.value,
            "failed_policy": decision.failed_policy,
        }

    return before_tool_callback


def make_transfer_tool(executor: SafeTransferExecutor) -> Callable[..., dict[str, Any]]:
    """Crea el tool ADK ``transfer_funds`` gateado por el co-signer de aval.

    El enforcement no-evitable lo da el Safe 2-de-2 (no este tool): aunque el
    agente llame al tool, sin la co-firma de aval la transacción no alcanza el
    threshold y no se ejecuta. Registralo en el agente::

        agent = LlmAgent(..., tools=[make_transfer_tool(executor)])
    """

    def transfer_funds(recipient: str, amount: float, token: str) -> dict[str, Any]:
        """Transfiere fondos desde el Safe a ``recipient``, sujeto a la co-autorización de aval.

        Args:
            recipient: dirección destino (0x...).
            amount: monto en unidades humanas del token (p. ej. 10 = 10 USDC).
            token: símbolo del token (p. ej. "USDC" o "ETH").

        Returns:
            dict con ``executed`` (bool), ``verdict``, ``reason``, ``reason_code``,
            ``tx_hash`` (si se ejecutó) y ``safe_tx_hash``.
        """
        return executor.transfer(recipient, amount, token)

    return transfer_funds


if TYPE_CHECKING:
    from aval.execution.transfer_executor import SafeTransferExecutor
