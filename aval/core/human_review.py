"""Escalamiento a aprobación humana para acciones sensibles pero permitidas."""

from __future__ import annotations

from abc import ABC, abstractmethod

from aval.models import Decision, Verdict


class HumanReviewer(ABC):
    """Resuelve una decisión ``ESCALATE`` pidiendo aprobación a una persona.

    Devuelve un veredicto final ``ALLOW`` o ``DENY``.
    """

    @abstractmethod
    def review(self, decision: Decision) -> Verdict:
        """Pide aprobación humana y devuelve ``Verdict.ALLOW`` o ``Verdict.DENY``."""


class ConsoleHumanReviewer(HumanReviewer):
    """Aprobación interactiva por consola: lista para usar, sin configuración.

    Imprime el detalle de la acción y lee la respuesta por stdin. Cualquier
    respuesta que no sea afirmativa (``y``/``yes``/``s``/``si``) se interpreta
    como rechazo (fail-closed por defecto).
    """

    _AFFIRMATIVE = {"y", "yes", "s", "si", "sí"}

    def __init__(self, prompt: str = "¿Aprobar esta acción? [y/N]: ") -> None:
        self._prompt = prompt

    def review(self, decision: Decision) -> Verdict:
        action = decision.action
        print("\n⚠️  aval — acción escalada para aprobación humana")
        print(f"   razón:   {decision.reason}")
        if action is not None:
            print(f"   token:   {action.token}")
            print(f"   monto:   {action.amount}")
            print(f"   destino: {action.recipient}")
            print(f"   método:  {action.method}")
        answer = input(self._prompt).strip().lower()
        return Verdict.ALLOW if answer in self._AFFIRMATIVE else Verdict.DENY


class AutoApproveReviewer(HumanReviewer):
    """Reviewer no interactivo con veredicto fijo — útil para tests y CI."""

    def __init__(self, verdict: Verdict = Verdict.ALLOW) -> None:
        self._verdict = verdict

    def review(self, decision: Decision) -> Verdict:
        return self._verdict
