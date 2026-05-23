"""Construcción, hash (EIP-712) y firma de transacciones de Safe.

Apoyado en `safe-eth-py` para el hash canónico de la SafeTx (un hash distinto del
que el contrato espera haría que la firma no validara on-chain). El cómputo del
hash y la firma son puros: no requieren RPC.
"""

from __future__ import annotations

from decimal import Decimal

from eth_abi import encode  # type: ignore[attr-defined]
from eth_account import Account
from eth_utils import to_checksum_address  # type: ignore[attr-defined]
from safe_eth.safe.safe_tx import SafeTx

from aval.execution.models import SafeTxRequest

ERC20_TRANSFER_SELECTOR = "a9059cbb"


def erc20_transfer_calldata(recipient: str, amount_raw: int) -> str:
    """Calldata de `transfer(address,uint256)` (hex con prefijo)."""
    args = encode(["address", "uint256"], [to_checksum_address(recipient), amount_raw]).hex()
    return "0x" + ERC20_TRANSFER_SELECTOR + args


def build_native_transfer(
    *, safe_address: str, chain_id: int, recipient: str, amount_raw: int, nonce: int, **kw: object
) -> SafeTxRequest:
    """SafeTx de una transferencia de activo nativo (value > 0, sin calldata)."""
    req = SafeTxRequest(
        safe_address=to_checksum_address(safe_address),
        chain_id=chain_id,
        to=to_checksum_address(recipient),
        value=amount_raw,
        data="0x",
        nonce=nonce,
        **kw,  # type: ignore[arg-type]
    )
    return req.model_copy(update={"safe_tx_hash": compute_safe_tx_hash(req)})


def build_erc20_transfer(
    *,
    safe_address: str,
    chain_id: int,
    token: str,
    recipient: str,
    amount_raw: int,
    nonce: int,
    **kw: object,
) -> SafeTxRequest:
    """SafeTx de una transferencia ERC-20 (to = token, data = transfer calldata)."""
    req = SafeTxRequest(
        safe_address=to_checksum_address(safe_address),
        chain_id=chain_id,
        to=to_checksum_address(token),
        value=0,
        data=erc20_transfer_calldata(recipient, amount_raw),
        nonce=nonce,
        **kw,  # type: ignore[arg-type]
    )
    return req.model_copy(update={"safe_tx_hash": compute_safe_tx_hash(req)})


def _safe_tx(req: SafeTxRequest) -> SafeTx:
    """Reconstruye el objeto SafeTx de safe-eth-py (sin cliente RPC: solo para hash)."""
    return SafeTx(
        None,  # ethereum_client — no se usa para el hash
        to_checksum_address(req.safe_address),
        to_checksum_address(req.to),
        req.value,
        bytes.fromhex(req.data[2:] if req.data.startswith("0x") else req.data),
        req.operation,
        req.safe_tx_gas,
        req.base_gas,
        req.gas_price,
        to_checksum_address(req.gas_token) if req.gas_token else None,
        to_checksum_address(req.refund_receiver) if req.refund_receiver else None,
        safe_nonce=req.nonce,
        safe_version=req.safe_version,
        chain_id=req.chain_id,
    )


def compute_safe_tx_hash(req: SafeTxRequest) -> str:
    """Hash EIP-712 de la SafeTx (hex con prefijo)."""
    return "0x" + _safe_tx(req).safe_tx_hash.hex()


def sign_safe_tx_hash(safe_tx_hash: str, private_key: str) -> str:
    """Firma EOA (65 bytes, hex) del hash de la SafeTx — el formato que el Safe espera."""
    digest = bytes.fromhex(safe_tx_hash[2:] if safe_tx_hash.startswith("0x") else safe_tx_hash)
    signed = Account.unsafe_sign_hash(digest, private_key)
    return "0x" + signed.signature.hex()


def signer_of(safe_tx_hash: str, signature: str) -> str:
    """Dirección que produjo `signature` sobre `safe_tx_hash` (para validar/ordenar)."""
    digest = bytes.fromhex(safe_tx_hash[2:] if safe_tx_hash.startswith("0x") else safe_tx_hash)
    sig = bytes.fromhex(signature[2:] if signature.startswith("0x") else signature)
    return str(Account._recover_hash(digest, signature=sig))


def combine_signatures(safe_tx_hash: str, signatures: list[str]) -> str:
    """Concatena las firmas ordenadas ascendente por dirección del firmante.

    Es el formato que `execTransaction` exige para verificar el threshold.
    """
    by_signer = sorted(signatures, key=lambda s: int(signer_of(safe_tx_hash, s), 16))
    return "0x" + "".join(s[2:] if s.startswith("0x") else s for s in by_signer)


def amount_to_raw(amount: Decimal, decimals: int) -> int:
    """Convierte un monto humano a su representación entera por decimales del token."""
    return int(amount * (Decimal(10) ** decimals))
