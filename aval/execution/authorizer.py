"""Núcleo del co-signer: decide y, si autoriza, firma la SafeTx con la llave de aval.

Reusa el `Engine` de la feature 001 (decisión + audit). La única capacidad nueva
es firmar el hash de la SafeTx — la pieza que, sumada a la firma del agente,
alcanza el threshold del Safe. Por eso este componente (y la llave de aval) deben
vivir en un proceso separado del agente (FR-3).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from aval.core.engine import Engine
from aval.execution.decode import decode_safe_tx
from aval.execution.models import AuthorizationResponse, ExecutionReport, SafeTxRequest
from aval.execution.safe_tx import compute_safe_tx_hash
from aval.execution.signer import Signer
from aval.models import AuditEntry, Mandate, Verdict

logger = logging.getLogger("aval.cosigner")


class Authorizer:
    """Evalúa una SafeTx contra el mandato y co-firma si el veredicto es ALLOW.

    Firma vía un ``Signer`` custodiado (KMS/keystore): la clave nunca aparece en
    texto plano en este componente.
    """

    def __init__(self, engine: Engine, signer: Signer, freshness_window_s: int = 120) -> None:
        self._engine = engine
        self._signer = signer
        self._address = signer.address
        self._window_s = freshness_window_s
        # safe_tx_hash → instante en que se emitió la co-firma (ventana de frescura, FR-5).
        self._issued: dict[str, datetime] = {}

    @property
    def address(self) -> str:
        """Dirección del co-firmante aval (un owner del Safe)."""
        return self._address

    def authorize(
        self, req: SafeTxRequest, mandate: Mandate, now: datetime | None = None
    ) -> AuthorizationResponse:
        now = now or datetime.now(UTC)

        # Verdad de fondo: recomputar el hash desde los campos (no confiar en el provisto).
        # El hash liga la firma a esta operación y a este nonce: una firma no sirve para
        # otra operación ni para otro nonce (anti-replay / anti-doble-ejecución, FR-5).
        safe_tx_hash = compute_safe_tx_hash(req)

        # Decodificar la operación efectiva y decidir reusando el core (decisión + audit).
        result = decode_safe_tx(self._engine.resolver, req)
        decision = self._engine.evaluate_result(result, mandate, now)

        # Observabilidad: se registran veredicto/código/agente/hash, NUNCA la clave ni secretos.
        logger.info(
            "aval decision verdict=%s code=%s agent=%s safe_tx_hash=%s",
            decision.verdict.value,
            decision.reason_code.value,
            mandate.agent_id,
            safe_tx_hash,
        )

        if decision.is_allow:
            signature = self._signer.sign_hash(safe_tx_hash)
            self._issued[safe_tx_hash] = now  # registrar para la ventana de frescura
            return AuthorizationResponse(decision=decision, aval_signature=signature)
        return AuthorizationResponse(decision=decision, aval_signature=None)

    def record_execution(
        self, report: ExecutionReport, mandate: Mandate, now: datetime | None = None
    ) -> AuditEntry:
        """Registra la 2ª entrada de audit: la ejecución on-chain, ligada por safe_tx_hash."""
        now = now or datetime.now(UTC)
        return self._engine.audit.record(
            timestamp=now,
            agent_id=mandate.agent_id,
            mandate_id=mandate.fingerprint,
            action={"safe_tx_hash": report.safe_tx_hash, "event": "executed"},
            verdict=Verdict.ALLOW,
            reason="SafeTx ejecutada on-chain",
            tx_hash=report.tx_hash,
        )

    def is_fresh(self, safe_tx_hash: str, now: datetime | None = None) -> bool:
        """``True`` si se emitió una co-firma para ese hash dentro de la ventana vigente."""
        now = now or datetime.now(UTC)
        issued = self._issued.get(safe_tx_hash)
        if issued is None:
            return False
        return (now - issued).total_seconds() <= self._window_s
