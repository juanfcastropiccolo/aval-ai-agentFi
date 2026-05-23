"""Capa de cadena: leer el nonce del Safe y ejecutar `execTransaction` (web3).

Aislada del core (que sigue sin RPC). La construcción de los argumentos de
`execTransaction` es pura y testeable; el envío usa web3 y se ejercita en el e2e.
"""

from __future__ import annotations

from typing import Any

from eth_utils import to_checksum_address  # type: ignore[attr-defined]

from aval.execution.models import SafeTxRequest

ZERO_ADDRESS = "0x" + "00" * 20

# ABI mínima del Safe: solo lo que usamos (nonce de lectura + execTransaction).
SAFE_ABI: list[dict[str, Any]] = [
    {
        "inputs": [],
        "name": "nonce",
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"type": "address", "name": "to"},
            {"type": "uint256", "name": "value"},
            {"type": "bytes", "name": "data"},
            {"type": "uint8", "name": "operation"},
            {"type": "uint256", "name": "safeTxGas"},
            {"type": "uint256", "name": "baseGas"},
            {"type": "uint256", "name": "gasPrice"},
            {"type": "address", "name": "gasToken"},
            {"type": "address", "name": "refundReceiver"},
            {"type": "bytes", "name": "signatures"},
        ],
        "name": "execTransaction",
        "outputs": [{"type": "bool", "name": "success"}],
        "stateMutability": "payable",
        "type": "function",
    },
]


def _hex_to_bytes(value: str) -> bytes:
    return bytes.fromhex(value[2:] if value.startswith("0x") else value)


def build_exec_args(req: SafeTxRequest, signatures: str) -> list[Any]:
    """Args posicionales de `execTransaction` (puro, sin red)."""
    return [
        to_checksum_address(req.to),
        req.value,
        _hex_to_bytes(req.data),
        req.operation,
        req.safe_tx_gas,
        req.base_gas,
        req.gas_price,
        to_checksum_address(req.gas_token) if req.gas_token else to_checksum_address(ZERO_ADDRESS),
        to_checksum_address(req.refund_receiver)
        if req.refund_receiver
        else to_checksum_address(ZERO_ADDRESS),
        _hex_to_bytes(signatures),
    ]


class SafeChain:
    """Cliente de cadena para un Safe concreto."""

    def __init__(self, w3: Any, safe_address: str) -> None:
        self._w3 = w3
        self._safe = w3.eth.contract(address=to_checksum_address(safe_address), abi=SAFE_ABI)

    def get_nonce(self) -> int:
        """Nonce actual del Safe (anti-replay: cada SafeTx ejecutada lo incrementa)."""
        return int(self._safe.functions.nonce().call())

    def exec_transaction(self, req: SafeTxRequest, signatures: str, sender_key: str) -> str:
        """Construye, firma y envía `execTransaction`; devuelve el tx hash on-chain."""
        from eth_account import Account

        sender = Account.from_key(sender_key).address
        fn = self._safe.functions.execTransaction(*build_exec_args(req, signatures))
        tx = fn.build_transaction(
            {"from": sender, "nonce": self._w3.eth.get_transaction_count(sender)}
        )
        signed = self._w3.eth.account.sign_transaction(tx, sender_key)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        self._w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()
