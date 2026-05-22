"""Veredictos posibles de una evaluación de política o decisión del engine."""

from enum import StrEnum


class Verdict(StrEnum):
    """Resultado de evaluar una acción contra el mandato.

    - ``ALLOW``: la acción respeta el mandato y puede ejecutarse.
    - ``DENY``: la acción viola el mandato (o es no resoluble) y se bloquea.
    - ``ESCALATE``: la acción es sensible pero permitida; requiere aprobación humana.
    """

    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"
