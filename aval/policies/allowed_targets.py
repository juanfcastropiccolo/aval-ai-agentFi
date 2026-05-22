"""Allowlist de contratos/destinos invocables."""

from __future__ import annotations

from datetime import datetime

from pydantic import field_validator

from aval.core.state import StateStore
from aval.models.action import ProposedAction
from aval.models.policy_result import PolicyResult
from aval.policies.base import Policy


class AllowedTargets(Policy):
    """Solo permite acciones cuyo contrato destino esté en la lista blanca.

    Las direcciones se comparan en minúscula (case-insensitive). Si la acción no
    tiene contrato destino, la política no aplica.
    """

    contracts: set[str]

    @field_validator("contracts")
    @classmethod
    def _lower(cls, value: set[str]) -> set[str]:
        return {c.lower() for c in value}

    def evaluate(
        self, action: ProposedAction, state: StateStore, agent_id: str, now: datetime
    ) -> PolicyResult:
        if action.target_contract is None:
            return PolicyResult.not_applicable(self.name)
        if action.target_contract.lower() in self.contracts:
            return PolicyResult.allow(self.name, "contrato destino permitido")
        return PolicyResult.deny(
            self.name, f"contrato destino no permitido: {action.target_contract}"
        )
