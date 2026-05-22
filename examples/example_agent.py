"""Agente de ejemplo envuelto con aval, recorriendo los 4 escenarios del spec.

Demuestra el patrón de integración sin reescribir la lógica del agente: el
"agente" propone tool calls y un wrapper consulta a ``aval`` antes de ejecutar.
Mismo patrón que usan los adaptadores ADK/LangChain, en versión agnóstica.

Ejecutar como demo interactiva (escalamiento por consola)::

    python -m examples.example_agent
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from eth_abi import encode

from aval import (
    AllowedMethods,
    Decision,
    Engine,
    EVMResolver,
    HumanReviewer,
    JsonlAuditStore,
    Mandate,
    Policy,
    RecipientAllowlist,
    SpendLimit,
    TokenInfo,
)
from aval.models import PolicyResult

USDC = "0x" + "a" * 40
ALICE = "0x" + "c" * 40  # destinatario en la allowlist
MALLORY = "0x" + "d" * 40  # destinatario NO permitido


def transfer_call(recipient: str, usdc: int) -> dict[str, Any]:
    """Construye el calldata de un ERC-20 transfer (USDC, 6 decimales)."""
    data = "0x" + "a9059cbb" + encode(["address", "uint256"], [recipient, usdc * 10**6]).hex()
    return {"to": USDC, "data": data}


class EscalateOverThreshold(Policy):
    """Marca como sensibles (escala a humano) las transferencias sobre un umbral."""

    threshold: Decimal

    def evaluate(self, action, state, agent_id, now):  # type: ignore[no-untyped-def]
        if action.amount is not None and action.amount >= self.threshold:
            return PolicyResult.escalate(self.name, f"monto {action.amount} ≥ {self.threshold}")
        return PolicyResult.allow(self.name, "monto por debajo del umbral sensible")


def build_demo(
    audit_path: str | Path,
    reviewer: HumanReviewer | None = None,
) -> tuple[Engine, Mandate]:
    """Arma el Engine y un mandato realista para la demo."""
    resolver = EVMResolver.from_tool_names({"send_tx"}, tokens={USDC: TokenInfo("USDC", 6)})
    engine = Engine(
        resolver,
        audit_store=JsonlAuditStore(audit_path),
        human_reviewer=reviewer,
    )
    mandate = Mandate(
        agent_id="trading-agent",
        granted_by="dev@example.com",
        chains=["ethereum"],
        policies=[
            SpendLimit(token="USDC", per_tx=Decimal("5000"), per_day=Decimal("20000")),
            RecipientAllowlist(recipients={ALICE}),
            AllowedMethods(methods={"transfer"}),
            EscalateOverThreshold(threshold=Decimal("3000")),
        ],
        token_decimals={"USDC": 6},
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    return engine, mandate


def run_scenarios(engine: Engine, mandate: Mandate) -> dict[str, Decision]:
    """Recorre los 4 escenarios del spec y devuelve la decisión de cada uno."""
    now = datetime.now(UTC)
    scenarios: dict[str, Callable[[], Decision]] = {
        # allow: dentro de todos los límites y bajo el umbral sensible
        "allow": lambda: engine.evaluate("send_tx", transfer_call(ALICE, 1000), mandate, now=now),
        # deny por límite por transacción (6000 > 5000)
        "deny_limit": lambda: engine.evaluate(
            "send_tx", transfer_call(ALICE, 6000), mandate, now=now
        ),
        # deny por destino fuera de la allowlist
        "deny_recipient": lambda: engine.evaluate(
            "send_tx", transfer_call(MALLORY, 100), mandate, now=now
        ),
        # escalate: monto sensible (≥3000 pero ≤ límite por tx) → aprobación humana
        "escalate": lambda: engine.evaluate(
            "send_tx", transfer_call(ALICE, 4000), mandate, now=now
        ),
    }
    return {name: run() for name, run in scenarios.items()}


def main() -> None:
    audit_path = Path("demo.aval.jsonl")
    if audit_path.exists():
        audit_path.unlink()
    engine, mandate = build_demo(audit_path)  # reviewer por defecto: ConsoleHumanReviewer
    results = run_scenarios(engine, mandate)
    print("\n=== Resultados aval ===")
    for name, decision in results.items():
        print(f"  {name:16} → {decision.verdict.value.upper():9} {decision.reason}")
    print(
        f"\nAudit trail: {audit_path} ({len(engine.audit.entries())} entradas, "
        f"íntegro={engine.audit.verify()})"
    )


if __name__ == "__main__":
    main()
