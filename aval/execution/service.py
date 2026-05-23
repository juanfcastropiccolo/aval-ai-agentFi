"""Servicio co-signer HTTP (FastAPI) — el proceso aislado que tiene la llave de aval.

El mandato es **fuente de verdad del servidor**: el agente NO lo envía (podría
mandar uno permisivo). El servicio mapea cada Safe a su mandato registrado.
"""

from __future__ import annotations

from fastapi import FastAPI

from aval.execution.authorizer import Authorizer
from aval.execution.models import AuthorizationResponse, ExecutionReport, SafeTxRequest
from aval.models import Decision, Mandate, ReasonCode


def create_app(authorizer: Authorizer, mandates: dict[str, Mandate]) -> FastAPI:
    """App FastAPI. ``mandates`` mapea ``safe_address`` (minúscula) → mandato."""
    registry = {addr.lower(): m for addr, m in mandates.items()}
    app = FastAPI(title="aval co-signer")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"aval_address": authorizer.address}

    @app.post("/authorize", response_model=AuthorizationResponse)
    def authorize(req: SafeTxRequest) -> AuthorizationResponse:
        mandate = registry.get(req.safe_address.lower())
        if mandate is None:
            return AuthorizationResponse(
                decision=Decision.deny(
                    f"Safe {req.safe_address} sin mandato registrado en el co-signer",
                    reason_code=ReasonCode.DEFAULT_DENY,
                ),
                aval_signature=None,
            )
        return authorizer.authorize(req, mandate)

    @app.post("/executed")
    def executed(report: ExecutionReport) -> dict[str, str]:
        mandate = registry.get(report.safe_address.lower())
        if mandate is None:
            return {"recorded": "false", "reason": "safe sin mandato registrado"}
        entry = authorizer.record_execution(report, mandate)
        return {"recorded": "true", "entry_hash": entry.entry_hash}

    return app
