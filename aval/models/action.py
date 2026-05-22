"""Acción propuesta por el agente, ya normalizada por el Resolver."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProposedAction(BaseModel):
    """Una acción que mueve dinero, normalizada a una forma agnóstica de framework.

    La construye el Resolver a partir de una tool call cruda. ``amount`` ya viene
    normalizado por los decimales del token (p. ej. 1 USDC == ``Decimal("1")``,
    no ``1_000_000``). Los campos opcionales son ``None`` cuando la dimensión no
    aplica a la acción (p. ej. un ``approve`` no tiene ``recipient``).
    """

    model_config = ConfigDict(frozen=True)

    rail: str = "evm"
    chain: str
    token: str | None = None
    amount: Decimal | None = None
    recipient: str | None = None
    target_contract: str | None = None
    method: str | None = None
    selector: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
