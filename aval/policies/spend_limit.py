"""Política de límite de gasto: por transacción y/o por día, por token."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from aval.core.state import Period, StateStore
from aval.models.action import ProposedAction
from aval.models.policy_result import PolicyResult
from aval.models.reason_code import ReasonCode
from aval.policies.base import Policy


class SpendLimit(Policy):
    """Limita el monto de un token, por transacción y por día.

    Los límites son **inclusivos**: un monto igual al límite se autoriza; uno
    estrictamente mayor se deniega. El límite diario considera el gasto previo
    del agente en la ventana (acumulado que cruza el umbral → denegado).

    Solo aplica a acciones cuyo ``token`` coincide; para otros tokens devuelve
    ``not_applicable``. Si la acción es de este token pero su monto no se pudo
    resolver, se deniega (fail-closed).
    """

    token: str
    per_tx: Decimal | None = None
    per_day: Decimal | None = None

    def evaluate(
        self,
        action: ProposedAction,
        state: StateStore,
        agent_id: str,
        now: datetime,
    ) -> PolicyResult:
        if action.token != self.token:
            return PolicyResult.not_applicable(self.name)

        if action.amount is None:
            return PolicyResult.deny(
                self.name,
                f"monto no resuelto para {self.token} con límite de gasto",
                ReasonCode.UNRESOLVABLE,
            )

        amount = action.amount

        if self.per_tx is not None and amount > self.per_tx:
            return PolicyResult.deny(
                self.name,
                f"monto {amount} {self.token} excede el límite por transacción {self.per_tx}",
                ReasonCode.SPEND_LIMIT_PER_TX,
            )

        if self.per_day is not None:
            prior = state.get_spend(agent_id, self.token, Period.DAY, now)
            if prior + amount > self.per_day:
                return PolicyResult.deny(
                    self.name,
                    f"gasto diario {prior + amount} {self.token} excede el límite "
                    f"{self.per_day} (previo {prior})",
                    ReasonCode.SPEND_LIMIT_DAILY,
                )

        return PolicyResult.allow(self.name, f"dentro de los límites de {self.token}")
