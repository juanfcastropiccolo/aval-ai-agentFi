"""Política de límite de cantidad de acciones por período."""

from __future__ import annotations

from datetime import datetime

from aval.core.state import Period, StateStore
from aval.models.action import ProposedAction
from aval.models.policy_result import PolicyResult
from aval.policies.base import Policy


class RateLimit(Policy):
    """Limita cuántas acciones puede ejecutar el agente por ventana temporal.

    Permite hasta ``max_actions`` acciones por bucket de ``per``. La acción en
    curso se autoriza mientras el conteo previo sea menor a ``max_actions``; el
    Engine cuenta la acción (vía ``StateStore.commit``) solo cuando se autoriza.
    """

    max_actions: int
    per: Period = Period.DAY

    def evaluate(
        self, action: ProposedAction, state: StateStore, agent_id: str, now: datetime
    ) -> PolicyResult:
        used = state.get_action_count(agent_id, self.per, now)
        if used < self.max_actions:
            return PolicyResult.allow(
                self.name, f"{used + 1}/{self.max_actions} acciones por {self.per}"
            )
        return PolicyResult.deny(
            self.name,
            f"límite de {self.max_actions} acciones por {self.per} alcanzado (usadas {used})",
        )
