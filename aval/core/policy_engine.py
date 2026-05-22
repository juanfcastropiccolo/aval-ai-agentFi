"""Policy Engine: combina las políticas del mandato por conjunción default-deny."""

from __future__ import annotations

from datetime import datetime

from aval.core.state import StateStore
from aval.models import Decision, Mandate, ProposedAction, Verdict


class PolicyEngine:
    """Evalúa una acción contra todas las políticas de un mandato.

    Reglas de combinación (FR-6, FR-7):

    - Si **alguna** política rechaza (DENY) → ``DENY`` (precedencia máxima; el
      primer rechazo determina la razón y ``failed_policy``).
    - Si no hay rechazos pero **alguna** pide escalamiento → ``ESCALATE``.
    - Si no hay rechazos ni escalamientos y **al menos una** política aplicable
      autoriza → ``ALLOW``.
    - Si **ninguna** política aplica/autoriza → ``DENY`` (default-deny: nada
      autoriza la acción de forma afirmativa).
    """

    def evaluate(
        self,
        action: ProposedAction,
        mandate: Mandate,
        state: StateStore,
        now: datetime,
    ) -> Decision:
        results = [
            policy.evaluate(action, state, mandate.agent_id, now) for policy in mandate.policies
        ]

        for result in results:
            if result.verdict is Verdict.DENY:
                return Decision.deny(result.reason, failed_policy=result.policy_name, action=action)

        for result in results:
            if result.verdict is Verdict.ESCALATE:
                return Decision.escalate(
                    result.reason, failed_policy=result.policy_name, action=action
                )

        affirmative = [r for r in results if r.applicable and r.passed]
        if affirmative:
            reason = "; ".join(r.reason for r in affirmative)
            return Decision.allow(reason, action=action)

        return Decision.deny(
            "ninguna política del mandato autoriza esta acción (default-deny)", action=action
        )
