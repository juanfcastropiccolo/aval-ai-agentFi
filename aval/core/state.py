"""Estado con memoria para límites por período: gasto acumulado y conteo de acciones.

El ``StateStore`` es una interfaz pluggable. El MVP usa ``InMemoryStateStore``
(buckets en un dict). Una implementación persistente (Redis/DB) puede sustituirla
sin tocar el Policy Engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from aval.models.action import ProposedAction


class Period(StrEnum):
    """Granularidad de un bucket temporal para acumulados."""

    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


def bucket_key(period: Period, now: datetime) -> str:
    """Clave del bucket en que cae ``now`` para la granularidad dada.

    Trunca el instante al inicio del período en UTC. Dos instantes del mismo
    día (resp. hora / minuto) comparten clave y por ende acumulan juntos.
    """
    match period:
        case Period.DAY:
            return now.strftime("%Y-%m-%d")
        case Period.HOUR:
            return now.strftime("%Y-%m-%dT%H")
        case Period.MINUTE:
            return now.strftime("%Y-%m-%dT%H:%M")


class StateStore(ABC):
    """Acumula gasto y conteo de acciones por agente y por ventana temporal."""

    @abstractmethod
    def get_spend(self, agent_id: str, token: str, period: Period, now: datetime) -> Decimal:
        """Gasto acumulado del agente en ``token`` dentro del bucket de ``now``."""

    @abstractmethod
    def get_action_count(self, agent_id: str, period: Period, now: datetime) -> int:
        """Cantidad de acciones del agente dentro del bucket de ``now``."""

    @abstractmethod
    def commit(self, agent_id: str, action: ProposedAction, now: datetime) -> None:
        """Registra una acción autorizada: suma su monto y cuenta la acción.

        Solo debe llamarse cuando la acción fue autorizada (ALLOW).
        """


class InMemoryStateStore(StateStore):
    """Implementación en memoria. Se resetea al reiniciar el proceso (limitación del MVP)."""

    def __init__(self) -> None:
        # (agent_id, token, period, bucket) -> monto acumulado
        self._spend: dict[tuple[str, str, Period, str], Decimal] = {}
        # (agent_id, period, bucket) -> conteo de acciones
        self._counts: dict[tuple[str, Period, str], int] = {}

    def get_spend(self, agent_id: str, token: str, period: Period, now: datetime) -> Decimal:
        key = (agent_id, token, period, bucket_key(period, now))
        return self._spend.get(key, Decimal(0))

    def get_action_count(self, agent_id: str, period: Period, now: datetime) -> int:
        key = (agent_id, period, bucket_key(period, now))
        return self._counts.get(key, 0)

    def commit(self, agent_id: str, action: ProposedAction, now: datetime) -> None:
        for period in Period:
            bucket = bucket_key(period, now)
            count_key = (agent_id, period, bucket)
            self._counts[count_key] = self._counts.get(count_key, 0) + 1
            if action.token is not None and action.amount is not None:
                spend_key = (agent_id, action.token, period, bucket)
                self._spend[spend_key] = self._spend.get(spend_key, Decimal(0)) + action.amount
