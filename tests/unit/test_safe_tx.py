"""Tarea 5: construcción, hash determinístico y firma de SafeTx."""

from decimal import Decimal

import pytest
from eth_account import Account

pytest.importorskip("safe_eth")

from aval.execution.safe_tx import (  # noqa: E402
    amount_to_raw,
    build_erc20_transfer,
    build_native_transfer,
    combine_signatures,
    sign_safe_tx_hash,
    signer_of,
)

SAFE = "0x" + "11" * 20
TOKEN = "0x" + "22" * 20
BOB = "0x" + "33" * 20
CHAIN = 11155111  # Sepolia


def test_erc20_transfer_builds_calldata_and_hash() -> None:
    req = build_erc20_transfer(
        safe_address=SAFE,
        chain_id=CHAIN,
        token=TOKEN,
        recipient=BOB,
        amount_raw=amount_to_raw(Decimal("10"), 6),
        nonce=0,
    )
    assert req.to.lower() == TOKEN
    assert req.data.startswith("0xa9059cbb")
    assert req.value == 0
    assert req.safe_tx_hash is not None and len(req.safe_tx_hash) == 66


def test_native_transfer_builds_value() -> None:
    req = build_native_transfer(
        safe_address=SAFE,
        chain_id=CHAIN,
        recipient=BOB,
        amount_raw=10**18,
        nonce=3,
    )
    assert req.to.lower() == BOB
    assert req.value == 10**18
    assert req.data == "0x"


def test_hash_is_deterministic_and_nonce_sensitive() -> None:
    a = build_erc20_transfer(
        safe_address=SAFE, chain_id=CHAIN, token=TOKEN, recipient=BOB, amount_raw=1, nonce=0
    )
    b = build_erc20_transfer(
        safe_address=SAFE, chain_id=CHAIN, token=TOKEN, recipient=BOB, amount_raw=1, nonce=0
    )
    c = build_erc20_transfer(
        safe_address=SAFE, chain_id=CHAIN, token=TOKEN, recipient=BOB, amount_raw=1, nonce=1
    )  # nonce distinto
    assert a.safe_tx_hash == b.safe_tx_hash
    assert a.safe_tx_hash != c.safe_tx_hash  # binding al nonce (anti-replay)


def test_sign_and_recover() -> None:
    acct = Account.create()
    req = build_native_transfer(
        safe_address=SAFE, chain_id=CHAIN, recipient=BOB, amount_raw=1, nonce=0
    )
    assert req.safe_tx_hash is not None
    sig = sign_safe_tx_hash(req.safe_tx_hash, acct.key.hex())
    assert len(bytes.fromhex(sig[2:])) == 65
    assert signer_of(req.safe_tx_hash, sig).lower() == acct.address.lower()


def test_combine_signatures_sorted_by_signer() -> None:
    req = build_native_transfer(
        safe_address=SAFE, chain_id=CHAIN, recipient=BOB, amount_raw=1, nonce=0
    )
    assert req.safe_tx_hash is not None
    a, b = Account.create(), Account.create()
    sig_a = sign_safe_tx_hash(req.safe_tx_hash, a.key.hex())
    sig_b = sign_safe_tx_hash(req.safe_tx_hash, b.key.hex())
    combined = combine_signatures(req.safe_tx_hash, [sig_a, sig_b])
    # 2 firmas de 65 bytes = 130 bytes = 260 hex
    assert len(combined[2:]) == 260
    # primer firmante es el de menor dirección
    lower = a if int(a.address, 16) < int(b.address, 16) else b
    first_sig = "0x" + combined[2 : 2 + 130]
    assert signer_of(req.safe_tx_hash, first_sig).lower() == lower.address.lower()
