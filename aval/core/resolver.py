"""EVM Resolver: convierte una tool call cruda en una ``ProposedAction`` normalizada.

El dev declara, de forma explícita (nunca por autodetección), qué tools mueven
dinero y qué tokens conoce. El resolver decodifica el calldata EVM vía una tabla
estática de selectores, normaliza el monto por los decimales del token, y produce
uno de tres resultados:

- ``RESOLVED``      → una ``ProposedAction`` lista para evaluar.
- ``PASS_THROUGH``  → el tool no mueve dinero; el engine lo deja pasar.
- ``UNRESOLVABLE``  → es financiero pero no se pudo resolver; el engine deniega (fail-closed).

Sin llamadas de red ni RPC: todo es decode local puro (``eth-abi``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto
from typing import Any

from eth_abi import decode as abi_decode  # type: ignore[attr-defined]
from eth_utils import decode_hex  # type: ignore[attr-defined]

from aval.models import ProposedAction

# --- Configuración declarativa que provee el dev -------------------------------------------


@dataclass(frozen=True)
class TokenInfo:
    """Un token conocido: símbolo legible y decimales para normalizar montos."""

    symbol: str
    decimals: int


@dataclass(frozen=True)
class ToolBinding:
    """Cómo leer los campos de una transacción EVM de las args de un tool financiero.

    Por defecto asume el shape estándar ``{to, data, value, chain}``. El dev puede
    mapear nombres distintos si su tool usa otras claves.
    """

    to: str = "to"
    data: str = "data"
    value: str = "value"
    chain: str = "chain"


@dataclass(frozen=True)
class Extracted:
    """Lo que un decoder de selector extrae del calldata, antes de normalizar."""

    method: str
    amount_raw: int | None
    recipient: str | None
    token_address: str | None  # None ⇒ usar el contrato llamado (caso ERC-20)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectorSpec:
    """Tipos ABI de los argumentos de una función y cómo extraer sus campos de dinero."""

    arg_types: list[str]
    extract: Callable[[tuple[Any, ...], str], Extracted]


# --- Decoders de los selectores conocidos del MVP ------------------------------------------


def _erc20_transfer(args: tuple[Any, ...], target: str) -> Extracted:
    recipient, amount = args
    return Extracted("transfer", int(amount), str(recipient).lower(), None)


def _erc20_approve(args: tuple[Any, ...], target: str) -> Extracted:
    spender, amount = args
    # approve no entrega fondos a un destinatario: recipient queda None;
    # el spender se guarda en extra para políticas que quieran inspeccionarlo.
    return Extracted("approve", int(amount), None, None, {"spender": str(spender).lower()})


def _erc20_transfer_from(args: tuple[Any, ...], target: str) -> Extracted:
    sender, recipient, amount = args
    return Extracted(
        "transferFrom", int(amount), str(recipient).lower(), None, {"from": str(sender).lower()}
    )


def _swap_exact_tokens(args: tuple[Any, ...], target: str) -> Extracted:
    amount_in, _amount_out_min, path, to, _deadline = args
    token_in = str(path[0]).lower() if path else None
    return Extracted("swapExactTokensForTokens", int(amount_in), str(to).lower(), token_in)


NATIVE_ETH = TokenInfo("ETH", 18)
"""Token nativo por defecto del rail EVM (18 decimales)."""


BUILTIN_SELECTORS: dict[str, SelectorSpec] = {
    "a9059cbb": SelectorSpec(["address", "uint256"], _erc20_transfer),
    "095ea7b3": SelectorSpec(["address", "uint256"], _erc20_approve),
    "23b872dd": SelectorSpec(["address", "address", "uint256"], _erc20_transfer_from),
    "38ed1739": SelectorSpec(
        ["uint256", "uint256", "address[]", "address", "uint256"], _swap_exact_tokens
    ),
}


# --- Resultado del resolver ----------------------------------------------------------------


class ResolveStatus(Enum):
    RESOLVED = auto()
    PASS_THROUGH = auto()
    UNRESOLVABLE = auto()


@dataclass(frozen=True)
class ResolverResult:
    status: ResolveStatus
    action: ProposedAction | None = None
    reason: str = ""

    @classmethod
    def resolved(cls, action: ProposedAction) -> ResolverResult:
        return cls(ResolveStatus.RESOLVED, action=action)

    @classmethod
    def pass_through(cls, reason: str = "tool no financiero") -> ResolverResult:
        return cls(ResolveStatus.PASS_THROUGH, reason=reason)

    @classmethod
    def unresolvable(cls, reason: str) -> ResolverResult:
        return cls(ResolveStatus.UNRESOLVABLE, reason=reason)


# --- Resolver ------------------------------------------------------------------------------


class EVMResolver:
    """Resuelve tool calls EVM a ``ProposedAction`` usando configuración declarativa."""

    def __init__(
        self,
        *,
        financial_tools: dict[str, ToolBinding],
        tokens: dict[str, TokenInfo],
        native: TokenInfo = NATIVE_ETH,
        default_chain: str = "ethereum",
        extra_selectors: dict[str, SelectorSpec] | None = None,
    ) -> None:
        self._financial = financial_tools
        # registro de tokens keyed por dirección en minúscula
        self._tokens = {addr.lower(): info for addr, info in tokens.items()}
        self._native = native
        self._default_chain = default_chain
        self._selectors = {**BUILTIN_SELECTORS, **(extra_selectors or {})}

    @classmethod
    def from_tool_names(
        cls, financial_tools: set[str], tokens: dict[str, TokenInfo], **kwargs: Any
    ) -> EVMResolver:
        """Atajo cuando todos los tools usan el binding estándar ``{to, data, value}``."""
        bindings = {name: ToolBinding() for name in financial_tools}
        return cls(financial_tools=bindings, tokens=tokens, **kwargs)

    def resolve(self, tool_name: str, args: dict[str, Any]) -> ResolverResult:
        binding = self._financial.get(tool_name)
        if binding is None:
            return ResolverResult.pass_through()

        chain = str(args.get(binding.chain, self._default_chain))
        target_raw = args.get(binding.to)
        target = str(target_raw).lower() if target_raw is not None else None
        value = int(args.get(binding.value, 0) or 0)
        data = args.get(binding.data)

        # Transferencia de valor nativo (sin calldata, value > 0).
        if not data or data in ("0x", "0x0"):
            if value > 0 and target is not None:
                amount = Decimal(value) / (Decimal(10) ** self._native.decimals)
                return ResolverResult.resolved(
                    ProposedAction(
                        chain=chain,
                        token=self._native.symbol,
                        amount=amount,
                        recipient=target,
                        target_contract=target,
                        method="transfer_native",
                        raw={"tool": tool_name, "value": value},
                    )
                )
            return ResolverResult.unresolvable(
                f"tool financiero '{tool_name}' sin calldata ni valor nativo reconocible"
            )

        if target is None:
            return ResolverResult.unresolvable(
                f"tool financiero '{tool_name}' sin contrato destino ('{binding.to}')"
            )

        # Decode del calldata por selector.
        try:
            raw_bytes = decode_hex(data)
        except (ValueError, TypeError):
            return ResolverResult.unresolvable(f"calldata no es hex válido en '{tool_name}'")

        if len(raw_bytes) < 4:
            return ResolverResult.unresolvable(f"calldata demasiado corto en '{tool_name}'")

        selector = raw_bytes[:4].hex()
        spec = self._selectors.get(selector)
        if spec is None:
            return ResolverResult.unresolvable(
                f"selector no reconocido '0x{selector}' — registralo si este tool debe permitirse"
            )

        try:
            decoded = abi_decode(spec.arg_types, raw_bytes[4:])
            extracted = spec.extract(decoded, target)
        except Exception as exc:  # decode/extract falló: fail-closed
            return ResolverResult.unresolvable(
                f"no se pudieron decodificar los parámetros de '0x{selector}': {exc}"
            )

        token_addr = (extracted.token_address or target).lower()
        token_info = self._tokens.get(token_addr)
        if token_info is None:
            return ResolverResult.unresolvable(
                f"token desconocido '{token_addr}' — declaralo en el registro de tokens"
            )

        norm_amount: Decimal | None = None
        if extracted.amount_raw is not None:
            norm_amount = Decimal(extracted.amount_raw) / (Decimal(10) ** token_info.decimals)

        return ResolverResult.resolved(
            ProposedAction(
                chain=chain,
                token=token_info.symbol,
                amount=norm_amount,
                recipient=extracted.recipient,
                target_contract=token_addr,
                method=extracted.method,
                selector=f"0x{selector}",
                raw={"tool": tool_name, "called_contract": target, **extracted.extra},
            )
        )
