"""Allowlist de tipos de acción (métodos) permitidos."""

from __future__ import annotations

from datetime import datetime

from aval.core.state import StateStore
from aval.models.action import ProposedAction
from aval.models.policy_result import PolicyResult
from aval.policies.base import Policy


class AllowedMethods(Policy):
    """Solo permite los métodos/tipos de acción declarados (p. ej. ``transfer``, ``approve``).

    Acciones sin método identificado no aplican (no se autoriza a ciegas: el
    Resolver ya habría marcado UNRESOLVABLE un calldata no reconocido).
    """

    methods: set[str]

    def evaluate(
        self, action: ProposedAction, state: StateStore, agent_id: str, now: datetime
    ) -> PolicyResult:
        if action.method is None:
            return PolicyResult.not_applicable(self.name)
        if action.method in self.methods:
            return PolicyResult.allow(self.name, "método permitido")
        return PolicyResult.deny(self.name, f"método no permitido: {action.method}")
