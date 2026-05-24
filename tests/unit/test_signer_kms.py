"""Tarea 3: KmsSigner — derivación de address, DER→r/s/v y firma recuperable.

Usa un fake-KMS respaldado por una clave secp256k1 real (sin cuenta AWS): ejercita
exactamente la conversión de la firma del KMS al formato de Ethereum.
"""

import os

import pytest

pytest.importorskip("eth_keys")

from eth_keys import keys  # noqa: E402

from aval.execution.safe_tx import signer_of  # noqa: E402
from aval.execution.signer import KmsSigner  # noqa: E402

# Prefijo SPKI estándar de una clave pública EC secp256k1 (lo que antecede a 0x04‖X‖Y).
_SPKI_PREFIX = bytes.fromhex("3056301006072a8648ce3d020106052b8104000a034200")


def _der_encode_int(x: int) -> bytes:
    b = x.to_bytes(32, "big").lstrip(b"\x00") or b"\x00"
    if b[0] & 0x80:  # DER: prepend 0x00 si el bit alto está seteado
        b = b"\x00" + b
    return b"\x02" + bytes([len(b)]) + b


class FakeKmsClient:
    """Imita boto3 KMS (get_public_key / sign) firmando con una clave local real."""

    def __init__(self) -> None:
        self._priv = keys.PrivateKey(os.urandom(32))

    def get_public_key(self, KeyId: str) -> dict[str, bytes]:  # noqa: N803 (API de boto3)
        return {"PublicKey": _SPKI_PREFIX + b"\x04" + self._priv.public_key.to_bytes()}

    def sign(self, KeyId: str, Message: bytes, MessageType: str, SigningAlgorithm: str):  # noqa: N803
        assert MessageType == "DIGEST"
        sig = self._priv.sign_msg_hash(Message)
        der = _der_encode_int(sig.r) + _der_encode_int(sig.s)
        return {"Signature": b"\x30" + bytes([len(der)]) + der}


HASH = "0x" + "cd" * 32


def test_address_derived_from_kms_public_key() -> None:
    fake = FakeKmsClient()
    signer = KmsSigner("alias/aval", fake)
    expected = fake._priv.public_key.to_checksum_address()
    assert signer.address.lower() == expected.lower()


def test_signature_recovers_to_kms_address() -> None:
    signer = KmsSigner("alias/aval", FakeKmsClient())
    sig = signer.sign_hash(HASH)
    assert len(bytes.fromhex(sig[2:])) == 65  # r‖s‖v
    assert signer_of(HASH, sig).lower() == signer.address.lower()


def test_signature_is_low_s() -> None:
    signer = KmsSigner("alias/aval", FakeKmsClient())
    sig = bytes.fromhex(signer.sign_hash(HASH)[2:])
    s = int.from_bytes(sig[32:64], "big")
    n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    assert s <= n // 2  # low-s (EIP-2)


def test_v_is_27_or_28() -> None:
    signer = KmsSigner("alias/aval", FakeKmsClient())
    sig = bytes.fromhex(signer.sign_hash(HASH)[2:])
    assert sig[64] in (27, 28)
