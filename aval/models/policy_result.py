"""Resultado de evaluar una única política contra una acción."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from aval.models.verdict import Verdict


class PolicyResult(BaseModel):
    """Lo que devuelve ``Policy.evaluate``.

    ``passed`` indica si la política autoriza la acción. ``verdict`` matiza ese
    resultado: una política puede *pasar* pero pedir escalamiento. Una política
    que no aplica a la dimensión de la acción devuelve :meth:`not_applicable`
    (pasa de forma neutra, sin opinar).
    """

    model_config = ConfigDict(frozen=True)

    passed: bool
    verdict: Verdict
    reason: str
    policy_name: str
    applicable: bool = True

    @classmethod
    def allow(cls, policy_name: str, reason: str = "ok") -> PolicyResult:
        return cls(passed=True, verdict=Verdict.ALLOW, reason=reason, policy_name=policy_name)

    @classmethod
    def deny(cls, policy_name: str, reason: str) -> PolicyResult:
        return cls(passed=False, verdict=Verdict.DENY, reason=reason, policy_name=policy_name)

    @classmethod
    def escalate(cls, policy_name: str, reason: str) -> PolicyResult:
        return cls(passed=True, verdict=Verdict.ESCALATE, reason=reason, policy_name=policy_name)

    @classmethod
    def not_applicable(cls, policy_name: str) -> PolicyResult:
        """La política no gobierna esta dimensión de la acción: pasa neutra y no opina.

        Marcada con ``applicable=False`` para que el Policy Engine la distinga de
        un ALLOW afirmativo (default-deny exige que *alguna* política autorice).
        """
        return cls(
            passed=True,
            verdict=Verdict.ALLOW,
            reason="not applicable",
            policy_name=policy_name,
            applicable=False,
        )
