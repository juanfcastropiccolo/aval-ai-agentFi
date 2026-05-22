"""Política de franja horaria permitida."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from pydantic import field_validator

from aval.core.state import StateStore
from aval.models.action import ProposedAction
from aval.models.policy_result import PolicyResult
from aval.policies.base import Policy


class TimeWindow(Policy):
    """Solo permite acciones dentro de una franja horaria local (``[start, end]``).

    La ventana es **inclusiva en ambos bordes**: en el filo exacto (``start`` o
    ``end``) la acción se autoriza. Soporta ventanas que cruzan medianoche
    (``start > end``, p. ej. 22:00–06:00). El instante ``now`` se evalúa en la
    zona horaria ``tz``.
    """

    start: time
    end: time
    tz: str = "UTC"

    @field_validator("tz")
    @classmethod
    def _valid_tz(cls, value: str) -> str:
        ZoneInfo(value)  # lanza si la zona no existe
        return value

    def evaluate(
        self, action: ProposedAction, state: StateStore, agent_id: str, now: datetime
    ) -> PolicyResult:
        local = now.astimezone(ZoneInfo(self.tz)).time()
        if self.start <= self.end:
            in_window = self.start <= local <= self.end
        else:  # ventana nocturna que cruza medianoche
            in_window = local >= self.start or local <= self.end

        if in_window:
            return PolicyResult.allow(self.name, f"dentro de la franja {self.start}-{self.end}")
        return PolicyResult.deny(
            self.name, f"fuera de la franja horaria permitida {self.start}-{self.end} ({self.tz})"
        )
