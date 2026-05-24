"""Servicio co-signer HTTP (FastAPI) — el proceso aislado que tiene la llave de aval.

El mandato es **fuente de verdad del servidor**: el agente NO lo envía (podría
mandar uno permisivo). El servicio mapea cada Safe a su mandato registrado.

Si se configura ``auth_token``, los endpoints exigen ``Authorization: Bearer <token>``
(comparación en tiempo constante). En producción el token es obligatorio (FR-4); se
deja opcional solo para escenarios de desarrollo/test sin auth.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException

from aval.execution.authorizer import Authorizer
from aval.execution.models import AuthorizationResponse, ExecutionReport, SafeTxRequest
from aval.models import Decision, Mandate, ReasonCode


def _make_auth_dependency(auth_token: str | None):
    def check_auth(authorization: str = Header(default="")) -> None:
        if auth_token is None:
            return  # auth deshabilitada (solo dev/test)
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token, auth_token):
            raise HTTPException(status_code=401, detail="no autorizado")

    return check_auth


def create_app(
    authorizer: Authorizer, mandates: dict[str, Mandate], *, auth_token: str | None = None
) -> FastAPI:
    """App FastAPI. ``mandates`` mapea ``safe_address`` (minúscula) → mandato.

    ``auth_token``: si se provee, ``/authorize`` y ``/executed`` exigen ese bearer token.
    """
    registry = {addr.lower(): m for addr, m in mandates.items()}
    auth = _make_auth_dependency(auth_token)
    app = FastAPI(title="aval co-signer")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"aval_address": authorizer.address}

    @app.post("/authorize", response_model=AuthorizationResponse, dependencies=[Depends(auth)])
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

    @app.post("/executed", dependencies=[Depends(auth)])
    def executed(report: ExecutionReport) -> dict[str, str]:
        mandate = registry.get(report.safe_address.lower())
        if mandate is None:
            return {"recorded": "false", "reason": "safe sin mandato registrado"}
        entry = authorizer.record_execution(report, mandate)
        return {"recorded": "true", "entry_hash": entry.entry_hash}

    return app
