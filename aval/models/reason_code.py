"""Códigos estructurados de veredicto, máquina-legibles (FR-8)."""

from enum import StrEnum


class ReasonCode(StrEnum):
    """Identifica la regla o causa de un veredicto, para que el agente y la
    analítica puedan actuar sobre él sin parsear texto."""

    OK = "ok"
    # Políticas
    SPEND_LIMIT_PER_TX = "spend_limit_per_tx"
    SPEND_LIMIT_DAILY = "spend_limit_daily"
    RECIPIENT_NOT_ALLOWED = "recipient_not_allowed"
    TARGET_NOT_ALLOWED = "target_not_allowed"
    TOKEN_NOT_ALLOWED = "token_not_allowed"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    TIME_WINDOW = "time_window"
    RATE_LIMIT = "rate_limit"
    # Mandato / engine
    MANDATE_EXPIRED = "mandate_expired"
    MANDATE_REVOKED = "mandate_revoked"
    UNRESOLVABLE = "unresolvable"
    DEFAULT_DENY = "default_deny"
    HUMAN_REJECTED = "human_rejected"
    AUDIT_FAILURE = "audit_failure"
    EVAL_ERROR = "eval_error"
