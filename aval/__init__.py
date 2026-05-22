"""aval — capa de confianza para agentes de IA que manejan dinero.

API pública mínima para integrar el enforcement:

    from aval import Engine, EVMResolver, Mandate, TokenInfo
    from aval import SpendLimit, RecipientAllowlist, AllowedMethods
"""

from aval.core import (
    AutoApproveReviewer,
    ConsoleHumanReviewer,
    Engine,
    EVMResolver,
    HumanReviewer,
    InMemoryAuditStore,
    InMemoryStateStore,
    JsonlAuditStore,
    Period,
    StateStore,
    TokenInfo,
    ToolBinding,
)
from aval.models import (
    AuditEntry,
    Decision,
    Mandate,
    Policy,
    PolicyResult,
    ProposedAction,
    Verdict,
)
from aval.policies import (
    AllowedMethods,
    AllowedTargets,
    AllowedTokens,
    RateLimit,
    RecipientAllowlist,
    SpendLimit,
    TimeWindow,
)

__version__ = "0.1.0"

__all__ = [
    "AllowedMethods",
    "AllowedTargets",
    "AllowedTokens",
    "AuditEntry",
    "AutoApproveReviewer",
    "ConsoleHumanReviewer",
    "Decision",
    "EVMResolver",
    "Engine",
    "HumanReviewer",
    "InMemoryAuditStore",
    "InMemoryStateStore",
    "JsonlAuditStore",
    "Mandate",
    "Period",
    "Policy",
    "PolicyResult",
    "ProposedAction",
    "RateLimit",
    "RecipientAllowlist",
    "SpendLimit",
    "StateStore",
    "TimeWindow",
    "TokenInfo",
    "ToolBinding",
    "Verdict",
]
