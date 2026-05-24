"""Cliente del servicio co-signer (lado agente).

Si el co-signer está inalcanzable, lanza ``CosignerUnavailable`` — el tool del
agente lo traduce a fail-closed (no ejecuta nada, FR-10).
"""

from __future__ import annotations

import contextlib

import httpx

from aval.execution.models import AuthorizationResponse, ExecutionReport, SafeTxRequest


class CosignerUnavailable(Exception):
    """El servicio co-signer no respondió: el agente debe tratar esto como fail-closed."""


class CosignerClient:
    """Pide la co-firma de aval para una SafeTx."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        client: httpx.Client | None = None,
        auth_token: str | None = None,
    ) -> None:
        self._client = client or httpx.Client(base_url=base_url, timeout=10.0)
        self._headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}

    def authorize(self, req: SafeTxRequest) -> AuthorizationResponse:
        try:
            resp = self._client.post("/authorize", json=req.model_dump(), headers=self._headers)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise CosignerUnavailable(str(exc)) from exc
        return AuthorizationResponse.model_validate(resp.json())

    def report_execution(self, report: ExecutionReport) -> None:
        """Avisa al co-signer que una SafeTx autorizada se ejecutó (best-effort)."""
        # La tx ya se ejecutó; el reporte de audit es best-effort.
        with contextlib.suppress(httpx.HTTPError):
            self._client.post("/executed", json=report.model_dump(), headers=self._headers)
