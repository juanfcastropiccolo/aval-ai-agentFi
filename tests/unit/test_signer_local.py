"""Tarea 2: LocalKeystoreSigner — keystore cifrado, firma recuperable, sin clave en texto plano."""

import json

import pytest

pytest.importorskip("eth_account")

from eth_account import Account  # noqa: E402

from aval.execution.safe_tx import signer_of  # noqa: E402
from aval.execution.signer import LocalKeystoreSigner  # noqa: E402

HASH = "0x" + "ab" * 32


def test_keystore_round_trip_and_address() -> None:
    acct = Account.create()
    ks = LocalKeystoreSigner.create_keystore(acct.key.hex(), "passphrase-fuerte")
    signer = LocalKeystoreSigner(ks, "passphrase-fuerte")
    assert signer.address.lower() == acct.address.lower()


def test_signature_recovers_to_address() -> None:
    acct = Account.create()
    ks = LocalKeystoreSigner.create_keystore(acct.key.hex(), "pw")
    signer = LocalKeystoreSigner(ks, "pw")
    sig = signer.sign_hash(HASH)
    assert len(bytes.fromhex(sig[2:])) == 65
    assert signer_of(HASH, sig).lower() == signer.address.lower()


def test_keystore_has_no_plaintext_key() -> None:
    acct = Account.create()
    ks = LocalKeystoreSigner.create_keystore(acct.key.hex(), "pw")
    blob = json.dumps(ks).lower()
    assert acct.key.hex().lower().lstrip("0x") not in blob  # la clave NO está en texto plano


def test_wrong_passphrase_fails() -> None:
    acct = Account.create()
    ks = LocalKeystoreSigner.create_keystore(acct.key.hex(), "pw")
    with pytest.raises(ValueError):
        LocalKeystoreSigner(ks, "mal")
