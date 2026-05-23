"""Decodifica una SafeTx a la operación efectiva que evaluará el mandato (FR-4).

Reusa el `EVMResolver` de la feature 001 sobre los campos `to`/`value`/`data` de
la SafeTx — la verdad de fondo, no lo que el agente diga. Fail-closed ante
`operation != CALL` (delegatecall) y ante cualquier patrón no reconocido (lotes /
MultiSend caen acá porque usan delegatecall o un selector desconocido).
"""

from __future__ import annotations

from aval.core.resolver import EVMResolver, ResolverResult, ResolveStatus
from aval.execution.models import SafeTxRequest

SAFE_TX_TOOL = "safe_transaction"
"""Nombre de tool sintético: en el co-signer, toda SafeTx se trata como financiera."""


def decode_safe_tx(resolver: EVMResolver, req: SafeTxRequest) -> ResolverResult:
    """Convierte la SafeTx en un `ResolverResult`. Fail-closed ante lo no resoluble."""
    if req.operation != 0:
        return ResolverResult.unresolvable(
            f"operation={req.operation} (no es CALL) — delegatecall/lote no soportado (fail-closed)"
        )
    args = {
        "to": req.to,
        "data": req.data,
        "value": req.value,
        "chain": str(req.chain_id),
    }
    result = resolver.resolve(SAFE_TX_TOOL, args)
    # En el co-signer no existe el pass-through: una SafeTx que no entendemos no se firma.
    if result.status is ResolveStatus.PASS_THROUGH:
        return ResolverResult.unresolvable(
            "SafeTx no reconocida como transferencia conocida (fail-closed)"
        )
    return result
