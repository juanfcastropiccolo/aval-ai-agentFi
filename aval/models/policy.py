"""Clase base de las políticas del mandato.

``Policy`` es parte del modelo de dominio (es un campo de ``Mandate``), por eso
vive en ``aval.models``: así importar los modelos nunca arrastra el paquete
``aval.policies`` (que sí depende de ``core`` y ``models``). Las subclases
concretas, con su lógica de evaluación, viven en ``aval/policies/``.

Cada política gobierna una dimensión de una :class:`ProposedAction`. Si la
dimensión no aplica a la acción evaluada, devuelve
:meth:`PolicyResult.not_applicable` — pasa neutra y no opina. El Policy Engine
combina todos los resultados por conjunción (default-deny).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from aval.models.action import ProposedAction
from aval.models.policy_result import PolicyResult

if TYPE_CHECKING:
    from aval.core.state import StateStore


class Policy(BaseModel, ABC):
    """Regla declarativa evaluable contra una acción.

    Es un modelo Pydantic (config serializable) con comportamiento. Las
    subclases concretas declaran sus parámetros como campos y la lógica en
    :meth:`evaluate`.
    """

    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def evaluate(
        self,
        action: ProposedAction,
        state: StateStore,
        agent_id: str,
        now: datetime,
    ) -> PolicyResult:
        """Decide si esta política autoriza ``action``.

        ``state``/``agent_id``/``now`` permiten a las políticas con memoria
        (gasto por período, rate limit) consultar acumulados.
        """
