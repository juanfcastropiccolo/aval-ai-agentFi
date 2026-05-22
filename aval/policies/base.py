"""Re-export de la clase base ``Policy``.

La definición vive en :mod:`aval.models.policy` (Policy es parte del modelo de
dominio). Este módulo se mantiene por conveniencia: las políticas concretas
importan ``from aval.policies.base import Policy``.
"""

from aval.models.policy import Policy

__all__ = ["Policy"]
