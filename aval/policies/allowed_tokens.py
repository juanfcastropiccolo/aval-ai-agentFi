"""Allowlist de activos (tokens) manejables."""

from __future__ import annotations

from datetime import datetime

from aval.core.state import StateStore
from aval.models.action import ProposedAction
from aval.models.policy_result import PolicyResult
from aval.models.reason_code import ReasonCode
from aval.policies.base import Policy


class AllowedTokens(Policy):
    """Solo permite acciones sobre tokens en la lista blanca (comparación por símbolo).

    Acciones sin token asociado no aplican.
    """

    tokens: set[str]

    def evaluate(
        self, action: ProposedAction, state: StateStore, agent_id: str, now: datetime
    ) -> PolicyResult:
        if action.token is None:
            return PolicyResult.not_applicable(self.name)
        if action.token in self.tokens:
            return PolicyResult.allow(self.name, "token permitido")
        return PolicyResult.deny(
            self.name, f"token no permitido: {action.token}", ReasonCode.TOKEN_NOT_ALLOWED
        )
