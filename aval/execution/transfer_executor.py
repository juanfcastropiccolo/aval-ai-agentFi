"""Orquestación lado-agente de una transferencia con co-autorización M-de-N de aval.

Arma la SafeTx, la firma con la llave del agente, pide co-firmas a N co-autorizadores
independientes y reúne **M** de ellas. Solo si junta M (umbral M+1 del Safe contando al
agente) ejecuta `execTransaction`. Ante menos de M autorizaciones o co-autorizadores
inalcanzables, no ejecuta nada (fail-closed, FR-7). Es agnóstico de framework; el
adaptador ADK lo expone como un tool.
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
    """Ejecuta transferencias desde un Safe, gateadas por M-de-N co-autorizadores de aval."""

    def __init__(
        self,
        *,
        safe_address: str,
        chain_id: int,
        agent_private_key: str,
        chain: SafeChain,
        tokens: dict[str, TokenSpec],
        cosigner: CosignerClient | None = None,
        cosigners: list[CosignerClient] | None = None,
        threshold_m: int = 1,
        native_symbol: str = "ETH",
    ) -> None:
        self._safe = safe_address
        self._chain_id = chain_id
        self._agent_key = agent_private_key
        self._chain = chain
        self._tokens = tokens
        self._native = native_symbol
        # Acepta un único co-autorizador (compat) o una lista (umbral M-de-N).
        if cosigners is None:
            cosigners = [cosigner] if cosigner is not None else []
        if not cosigners:
            raise ValueError("se requiere al menos un co-autorizador")
        self._cosigners = cosigners
        self._m = threshold_m

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

        # Reunir M co-firmas de los N co-autorizadores (cada uno evalúa el mandato por su cuenta).
        aval_sigs: list[str] = []
        last_reason = "ningún co-autorizador autorizó"
        last_code: str | None = None
        for cosigner in self._cosigners:
            if len(aval_sigs) >= self._m:
                break
            try:
                resp = cosigner.authorize(req)
            except CosignerUnavailable:
                last_reason = "co-autorizador inalcanzable"
                continue
            if resp.decision.is_allow and resp.aval_signature is not None:
                aval_sigs.append(resp.aval_signature)
            else:
                last_reason = resp.decision.reason
                last_code = resp.decision.reason_code.value

        if len(aval_sigs) < self._m:
            reason = (
                f"co-autorizaciones insuficientes: {len(aval_sigs)}/{self._m} "
                f"(fail-closed) — {last_reason}"
            )
            return _result(False, "deny", reason, last_code, req.safe_tx_hash)

        # Umbral alcanzado (agente + M) → ejecutar on-chain.
        combined = combine_signatures(req.safe_tx_hash, [agent_sig, *aval_sigs])
        tx_hash = self._chain.exec_transaction(req, combined, self._agent_key)
        report = ExecutionReport(
            safe_address=self._safe, safe_tx_hash=req.safe_tx_hash, tx_hash=tx_hash
        )
        for cosigner in self._cosigners:  # registro de ejecución best-effort en cada nodo
            cosigner.report_execution(report)
        return {
            "executed": True,
            "verdict": "allow",
            "reason": f"ejecutada con {len(aval_sigs)}/{self._m} co-autorizaciones",
            "reason_code": "ok",
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
