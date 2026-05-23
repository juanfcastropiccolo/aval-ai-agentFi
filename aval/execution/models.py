"""Modelos de la capa de ejecución: la SafeTx propuesta y la respuesta del co-signer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from aval.models import Decision


class SafeTxRequest(BaseModel):
    """Una transacción de Safe propuesta por el agente, lista para co-autorizar.

    Los campos `to`/`value`/`data`/`operation` son la operación real que la cuenta
    custodia ejecutará (la verdad de fondo que aval decodifica y evalúa). `data`
    va como hex (``0x...``). El co-signer recomputa `safe_tx_hash` para verificar
    integridad y firma exactamente ese hash.
    """

    model_config = ConfigDict(frozen=True)

    safe_address: str
    chain_id: int
    to: str
    value: int = 0
    data: str = "0x"
    operation: int = 0  # 0 = CALL, 1 = DELEGATECALL (delegatecall ⇒ fail-closed)
    nonce: int
    safe_tx_gas: int = 0
    base_gas: int = 0
    gas_price: int = 0
    gas_token: str | None = None
    refund_receiver: str | None = None
    safe_version: str = "1.4.1"
    safe_tx_hash: str | None = None  # informativo; el co-signer lo recomputa


class AuthorizationResponse(BaseModel):
    """Respuesta del co-signer: la decisión y, si autoriza, la firma de aval."""

    model_config = ConfigDict(frozen=True)

    decision: Decision
    aval_signature: str | None = Field(
        default=None, description="Firma de aval (hex) sobre el safe_tx_hash; None si no autoriza."
    )


class ExecutionReport(BaseModel):
    """Aviso del agente al co-signer de que una SafeTx autorizada se ejecutó on-chain.

    Permite que el audit trail (que vive en el co-signer) registre una segunda
    entrada con el tx hash, ligada por ``safe_tx_hash`` a la autorización (FR-9).
    """

    model_config = ConfigDict(frozen=True)

    safe_address: str
    safe_tx_hash: str
    tx_hash: str
