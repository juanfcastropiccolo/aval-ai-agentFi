"""Engine: orquesta la pipeline Resolver → Policy Engine → Human Review → Audit.

Es el punto de integración estable que los adaptadores invocan. Síncrono y sin
conocimiento de framework. Garantiza fail-closed en cada borde: una acción solo
se autoriza si se resolvió, respeta el mandato activo, y su veredicto quedó
registrado en el audit trail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aval.core.audit import AuditStore, InMemoryAuditStore
from aval.core.human_review import ConsoleHumanReviewer, HumanReviewer
from aval.core.policy_engine import PolicyEngine
from aval.core.resolver import EVMResolver, ResolveStatus
from aval.core.state import InMemoryStateStore, StateStore
from aval.models import Decision, Mandate, ProposedAction, Verdict


class Engine:
    """Evalúa cada tool call que el agente intenta, contra un mandato."""

    def __init__(
        self,
        resolver: EVMResolver,
        *,
        audit_store: AuditStore | None = None,
        state_store: StateStore | None = None,
        human_reviewer: HumanReviewer | None = None,
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self._resolver = resolver
        self._audit = audit_store if audit_store is not None else InMemoryAuditStore()
        self._state = state_store if state_store is not None else InMemoryStateStore()
        # Mecanismo de aprobación funcional por defecto (FR-8): sin configuración extra.
        self._reviewer = human_reviewer if human_reviewer is not None else ConsoleHumanReviewer()
        self._policy_engine = policy_engine or PolicyEngine()

    @property
    def audit(self) -> AuditStore:
        return self._audit

    def evaluate(
        self,
        tool_name: str,
        args: dict[str, Any],
        mandate: Mandate,
        now: datetime | None = None,
    ) -> Decision:
        """Devuelve el veredicto para una tool call. Nunca lanza: ante error, deniega."""
        now = now or datetime.now(UTC)
        try:
            result = self._resolver.resolve(tool_name, args)

            # FR-11: las acciones no financieras pasan sin enforcement ni audit.
            if result.status is ResolveStatus.PASS_THROUGH:
                return Decision.allow("pass-through: acción no financiera")

            if result.status is ResolveStatus.UNRESOLVABLE:
                decision = Decision.deny(f"acción no resoluble (fail-closed): {result.reason}")
                return self._record_then(decision, mandate, now, None, commit=False)

            action = result.action
            assert action is not None  # RESOLVED ⇒ siempre trae acción

            # FR-13: mandato expirado o revocado deniega toda acción de dinero.
            if not mandate.is_active(now):
                reason = "mandato revocado" if mandate.revoked else "mandato expirado"
                decision = Decision.deny(reason, action=action)
                return self._record_then(decision, mandate, now, action, commit=False)

            decision = self._policy_engine.evaluate(action, mandate, self._state, now)

            # FR-8: escalamiento a humano.
            if decision.is_escalate:
                decision = self._resolve_escalation(decision, action)

            return self._record_then(decision, mandate, now, action, commit=decision.is_allow)

        except Exception as exc:  # error inesperado ⇒ deny y registrar (nunca autoriza)
            decision = Decision.deny(f"error durante la evaluación (fail-closed): {exc}")
            return self._record_then(decision, mandate, now, None, commit=False)

    def _resolve_escalation(self, decision: Decision, action: ProposedAction) -> Decision:
        verdict = self._reviewer.review(decision)
        if verdict is Verdict.ALLOW:
            return Decision.allow(f"aprobado por humano ({decision.reason})", action=action)
        return Decision.deny(
            f"rechazado por humano ({decision.reason})",
            failed_policy=decision.failed_policy,
            action=action,
        )

    def _record_then(
        self,
        decision: Decision,
        mandate: Mandate,
        now: datetime,
        action: ProposedAction | None,
        *,
        commit: bool,
    ) -> Decision:
        """Registra el veredicto (camino crítico) y luego, si ALLOW, contabiliza el gasto.

        Si no se puede dejar rastro, deniega: registrar es parte del camino crítico
        y un ALLOW sin audit no debe contabilizarse.
        """
        try:
            entry = self._audit.record(
                timestamp=now,
                agent_id=mandate.agent_id,
                mandate_id=mandate.fingerprint,
                action=action.model_dump(mode="json") if action is not None else {},
                verdict=decision.verdict,
                reason=decision.reason,
                failed_policy=decision.failed_policy,
            )
        except Exception as exc:
            return Decision.deny(
                f"fallo al registrar en el audit trail (fail-closed): {exc}", action=action
            )

        final = decision.with_entry_hash(entry.entry_hash)
        if commit and final.is_allow and action is not None:
            self._state.commit(mandate.agent_id, action, now)
        return final
