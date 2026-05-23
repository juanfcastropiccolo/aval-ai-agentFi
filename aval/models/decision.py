"""Veredicto final del engine sobre una acción del agente."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from aval.models.action import ProposedAction
from aval.models.reason_code import ReasonCode
from aval.models.verdict import Verdict


def _now() -> datetime:
    return datetime.now(UTC)


class Decision(BaseModel):
    """Resultado de ``Engine.evaluate``: el veredicto que el adaptador aplica.

    Incluye la razón legible y la política que lo determinó (``failed_policy``),
    de modo que en una denegación el agente reciba feedback accionable.
    ``entry_hash`` referencia la entrada de audit que dejó rastro del veredicto.
    """

    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    reason: str
    failed_policy: str | None = None
    action: ProposedAction | None = None
    entry_hash: str | None = None
    reason_code: ReasonCode = ReasonCode.OK
    timestamp: datetime = Field(default_factory=_now)

    @property
    def is_allow(self) -> bool:
        return self.verdict is Verdict.ALLOW

    @property
    def is_deny(self) -> bool:
        return self.verdict is Verdict.DENY

    @property
    def is_escalate(self) -> bool:
        return self.verdict is Verdict.ESCALATE

    @classmethod
    def allow(
        cls,
        reason: str = "ok",
        action: ProposedAction | None = None,
    ) -> Decision:
        return cls(verdict=Verdict.ALLOW, reason=reason, action=action)

    @classmethod
    def deny(
        cls,
        reason: str,
        failed_policy: str | None = None,
        action: ProposedAction | None = None,
        reason_code: ReasonCode = ReasonCode.DEFAULT_DENY,
    ) -> Decision:
        return cls(
            verdict=Verdict.DENY,
            reason=reason,
            failed_policy=failed_policy,
            action=action,
            reason_code=reason_code,
        )

    @classmethod
    def escalate(
        cls,
        reason: str,
        failed_policy: str | None = None,
        action: ProposedAction | None = None,
    ) -> Decision:
        return cls(
            verdict=Verdict.ESCALATE,
            reason=reason,
            failed_policy=failed_policy,
            action=action,
        )

    def with_entry_hash(self, entry_hash: str) -> Decision:
        """Devuelve una copia con el hash de la entrada de audit adjunta."""
        return self.model_copy(update={"entry_hash": entry_hash})
