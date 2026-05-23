"""Allowlist de destinatarios de fondos."""

from __future__ import annotations

from datetime import datetime

from pydantic import field_validator

from aval.core.state import StateStore
from aval.models.action import ProposedAction
from aval.models.policy_result import PolicyResult
from aval.models.reason_code import ReasonCode
from aval.policies.base import Policy


class RecipientAllowlist(Policy):
    """Solo permite enviar fondos a destinatarios en la lista blanca.

    Direcciones comparadas en minúscula. Acciones sin destinatario (p. ej. un
    ``approve``) no entregan fondos: la política no aplica.
    """

    recipients: set[str]

    @field_validator("recipients")
    @classmethod
    def _lower(cls, value: set[str]) -> set[str]:
        return {r.lower() for r in value}

    def evaluate(
        self, action: ProposedAction, state: StateStore, agent_id: str, now: datetime
    ) -> PolicyResult:
        if action.recipient is None:
            return PolicyResult.not_applicable(self.name)
        if action.recipient.lower() in self.recipients:
            return PolicyResult.allow(self.name, "destinatario permitido")
        return PolicyResult.deny(
            self.name,
            f"destino no permitido: {action.recipient}",
            ReasonCode.RECIPIENT_NOT_ALLOWED,
        )
