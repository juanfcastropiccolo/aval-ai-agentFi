"""Tarea 10: capa de cadena — args de execTransaction (puro) y wiring de envío (mock)."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("safe_eth")

from aval.execution.chain import ZERO_ADDRESS, SafeChain, build_exec_args  # noqa: E402
from aval.execution.safe_tx import build_erc20_transfer  # noqa: E402

CHAIN = 11155111
SAFE = "0x" + "11" * 20
USDC = "0x" + "aa" * 20
ALICE = "0x" + "33" * 20


def _req():
    return build_erc20_transfer(
        safe_address=SAFE, chain_id=CHAIN, token=USDC, recipient=ALICE, amount_raw=10**6, nonce=0
    )


def test_build_exec_args_shapes() -> None:
    sigs = "0x" + "ab" * 130  # 2 firmas de 65 bytes
    args = build_exec_args(_req(), sigs)
    assert len(args) == 10
    assert args[1] == 0  # value
    assert isinstance(args[2], bytes) and args[2][:4].hex() == "a9059cbb"  # data = transfer
    assert args[3] == 0  # operation CALL
    assert args[7].lower() == ZERO_ADDRESS  # gasToken
    assert args[8].lower() == ZERO_ADDRESS  # refundReceiver
    assert isinstance(args[9], bytes) and len(args[9]) == 130  # signatures bytes


def test_get_nonce_reads_contract() -> None:
    w3 = MagicMock()
    w3.eth.contract.return_value.functions.nonce.return_value.call.return_value = 7
    chain = SafeChain(w3, SAFE)
    assert chain.get_nonce() == 7


def test_exec_transaction_sends_and_returns_hash() -> None:
    from eth_account import Account

    sender_key = Account.create().key.hex()
    w3 = MagicMock()
    contract = w3.eth.contract.return_value
    contract.functions.execTransaction.return_value.build_transaction.return_value = {"x": 1}
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.account.sign_transaction.return_value.raw_transaction = b"\x01\x02"
    w3.eth.send_raw_transaction.return_value = bytes.fromhex("ab" * 32)

    chain = SafeChain(w3, SAFE)
    tx_hash = chain.exec_transaction(_req(), "0x" + "cd" * 130, sender_key)

    assert tx_hash == "ab" * 32
    w3.eth.send_raw_transaction.assert_called_once()
    w3.eth.wait_for_transaction_receipt.assert_called_once()
