"""El mandato: el conjunto de reglas bajo las que un agente puede mover dinero."""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aval.models.policy import Policy


class Mandate(BaseModel):
    """Autoridad acotada otorgada a un agente.

    Asocia un ``agent_id`` a una lista de políticas, con quién la otorga
    (``granted_by``), las redes habilitadas, el registro de decimales de los
    tokens manejables, y una expiración. Una acción de dinero se autoriza solo
    si respeta *todas* las políticas aplicables y el mandato está activo.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_id: str
    granted_by: str
    chains: list[str] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    token_decimals: dict[str, int] = Field(default_factory=dict)
    expires_at: datetime
    revocable: bool = True
    revoked: bool = False

    @model_validator(mode="after")
    def _validate_token_decimals(self) -> Mandate:
        for token, decimals in self.token_decimals.items():
            if decimals < 0:
                raise ValueError(f"decimales inválidos para {token}: {decimals} (< 0)")
        return self

    def is_active(self, now: datetime) -> bool:
        """``True`` si el mandato no fue revocado y no expiró a ``now``.

        La expiración se evalúa al momento de cada acción, no al inicio (un
        mandato puede expirar mientras el agente opera).
        """
        if self.revoked:
            return False
        return now < self.expires_at

    def decimals_for(self, token: str) -> int | None:
        """Decimales declarados para ``token``; ``None`` si no está en el registro."""
        return self.token_decimals.get(token)

    @property
    def fingerprint(self) -> str:
        """Identificador estable del mandato para el audit trail (``mandate_id``)."""
        raw = f"{self.agent_id}|{self.granted_by}|{self.expires_at.isoformat()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
