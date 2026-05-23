"""Orquestación lado-agente de una transferencia con co-autorización de aval.

Arma la SafeTx, la firma con la llave del agente, pide la 2ª firma al co-signer,
y solo si la obtiene ejecuta `execTransaction`. Ante DENY o co-signer inalcanzable,
no ejecuta nada (fail-closed, FR-10). Es agnóstico de framework; el adaptador ADK
lo expone como un tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from aval.execution.chain import SafeChain
from aval.execution.cosigner_client import CosignerClient, CosignerUnavailable
from aval.execution.models import ExecutionReport
from aval.execution.safe_tx import (
    amount_to_raw,
    build_erc20_transfer,
    build_native_transfer,
    combine_signatures,
    sign_safe_tx_hash,
)


@dataclass(frozen=True)
class TokenSpec:
    """Token conocido por el agente: dirección de contrato (None = nativo) y decimales."""

    address: str | None
    decimals: int


class SafeTransferExecutor:
    """Ejecuta transferencias desde un Safe, gateadas por el co-signer de aval."""

    def __init__(
        self,
        *,
        safe_address: str,
        chain_id: int,
        agent_private_key: str,
        chain: SafeChain,
        cosigner: CosignerClient,
        tokens: dict[str, TokenSpec],
        native_symbol: str = "ETH",
    ) -> None:
        self._safe = safe_address
        self._chain_id = chain_id
        self._agent_key = agent_private_key
        self._chain = chain
        self._cosigner = cosigner
        self._tokens = tokens
        self._native = native_symbol

    def transfer(self, recipient: str, amount: float | str, token: str) -> dict[str, Any]:
        """Intenta transferir ``amount`` de ``token`` a ``recipient``. Nunca lanza."""
        spec = self._tokens.get(token)
        if spec is None:
            return _result(False, "deny", f"token desconocido para el agente: {token}", None, None)

        amount_raw = amount_to_raw(Decimal(str(amount)), spec.decimals)
        nonce = self._chain.get_nonce()

        if spec.address is None:  # transferencia nativa
            req = build_native_transfer(
                safe_address=self._safe,
                chain_id=self._chain_id,
                recipient=recipient,
                amount_raw=amount_raw,
                nonce=nonce,
            )
        else:
            req = build_erc20_transfer(
                safe_address=self._safe,
                chain_id=self._chain_id,
                token=spec.address,
                recipient=recipient,
                amount_raw=amount_raw,
                nonce=nonce,
            )
        assert req.safe_tx_hash is not None

        # 1ª firma: el agente.
        agent_sig = sign_safe_tx_hash(req.safe_tx_hash, self._agent_key)

        # 2ª firma: el co-signer de aval (fail-closed si no responde).
        try:
            resp = self._cosigner.authorize(req)
        except CosignerUnavailable as exc:
            return _result(
                False,
                "deny",
                f"co-signer inalcanzable (fail-closed): {exc}",
                None,
                req.safe_tx_hash,
            )

        d = resp.decision
        if not d.is_allow or resp.aval_signature is None:
            return _result(False, d.verdict.value, d.reason, d.reason_code.value, req.safe_tx_hash)

        # 2-de-2 alcanzado → ejecutar on-chain.
        combined = combine_signatures(req.safe_tx_hash, [agent_sig, resp.aval_signature])
        tx_hash = self._chain.exec_transaction(req, combined, self._agent_key)
        # Reportar la ejecución para la 2ª entrada de audit (best-effort).
        self._cosigner.report_execution(
            ExecutionReport(safe_address=self._safe, safe_tx_hash=req.safe_tx_hash, tx_hash=tx_hash)
        )
        return {
            "executed": True,
            "verdict": "allow",
            "reason": d.reason,
            "reason_code": d.reason_code.value,
            "tx_hash": tx_hash,
            "safe_tx_hash": req.safe_tx_hash,
        }


def _result(
    executed: bool, verdict: str, reason: str, code: str | None, safe_tx_hash: str | None
) -> dict[str, Any]:
    return {
        "executed": executed,
        "verdict": verdict,
        "reason": reason,
        "reason_code": code,
        "tx_hash": None,
        "safe_tx_hash": safe_tx_hash,
    }
