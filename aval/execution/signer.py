"""Abstracción de firma para el co-autorizador: la clave nunca aparece en texto plano.

`Signer` desacopla *cómo* se firma del resto del flujo. Implementaciones:
- `LocalKeystoreSigner`: keystore JSON v3 cifrado por passphrase (desarrollo).
- `KmsSigner`: firma dentro de un KMS, la clave nunca sale del backend (producción).

Todas devuelven una firma de 65 bytes (r‖s‖v, hex con prefijo), el formato que consume
`combine_signatures` y que la cuenta custodia (Safe) espera de un owner EOA.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from eth_account import Account
from eth_keys import keys

# Orden del grupo secp256k1 (para normalizar s a low-s, EIP-2).
_SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def _digest_bytes(hash_hex: str) -> bytes:
    return bytes.fromhex(hash_hex[2:] if hash_hex.startswith("0x") else hash_hex)


def _decode_der_signature(der: bytes) -> tuple[int, int]:
    """Decodifica una firma ECDSA DER ``SEQUENCE { r INTEGER, s INTEGER }``."""
    if der[0] != 0x30:
        raise ValueError("firma DER inválida: no es SEQUENCE")
    idx = 2
    if der[idx] != 0x02:
        raise ValueError("firma DER inválida: r no es INTEGER")
    r_len = der[idx + 1]
    r = int.from_bytes(der[idx + 2 : idx + 2 + r_len], "big")
    idx = idx + 2 + r_len
    if der[idx] != 0x02:
        raise ValueError("firma DER inválida: s no es INTEGER")
    s_len = der[idx + 1]
    s = int.from_bytes(der[idx + 2 : idx + 2 + s_len], "big")
    return r, s


class Signer(ABC):
    """Produce firmas EOA sobre un hash de 32 bytes, sin exponer la clave."""

    @property
    @abstractmethod
    def address(self) -> str:
        """Dirección del firmante (un owner del Safe)."""

    @abstractmethod
    def sign_hash(self, hash_hex: str) -> str:
        """Firma el hash (hex 0x…) y devuelve 65 bytes hex r‖s‖v."""


class LocalKeystoreSigner(Signer):
    """Firma con una clave guardada en un keystore JSON v3 cifrado (passphrase).

    Para desarrollo: la clave se descifra en memoria al construir; nunca vive en
    texto plano en disco ni en configuración.
    """

    def __init__(self, keystore_json: dict[str, Any] | str, passphrase: str) -> None:
        self._key = Account.decrypt(keystore_json, passphrase)
        self._address = Account.from_key(self._key).address

    @staticmethod
    def create_keystore(private_key: str, passphrase: str) -> dict[str, Any]:
        """Crea un keystore JSON v3 cifrado a partir de una private key."""
        return Account.encrypt(private_key, passphrase)

    @property
    def address(self) -> str:
        return self._address

    def sign_hash(self, hash_hex: str) -> str:
        signed = Account.unsafe_sign_hash(_digest_bytes(hash_hex), self._key)
        return "0x" + signed.signature.hex()


class RawKeySigner(Signer):
    """Firma con una private key en memoria. **Solo dev/test/ejemplos.**

    En producción usá ``KmsSigner`` (clave custodiada) o ``LocalKeystoreSigner``
    (clave cifrada). Esta clase tiene la clave en texto plano en memoria.
    """

    def __init__(self, private_key: str) -> None:
        self._acct = Account.from_key(private_key)

    @property
    def address(self) -> str:
        return self._acct.address

    def sign_hash(self, hash_hex: str) -> str:
        signed = Account.unsafe_sign_hash(_digest_bytes(hash_hex), self._acct.key)
        return "0x" + signed.signature.hex()


class KmsSigner(Signer):
    """Firma dentro de un KMS (AWS): la clave secp256k1 nunca sale del backend.

    Deriva la address una vez de la pubkey del KMS y, en cada firma, convierte la
    firma DER del KMS al formato r‖s‖v de Ethereum: normaliza ``s`` a low-s (EIP-2)
    y recupera ``v`` probando cuál reproduce la address conocida (el KMS no devuelve v).

    ``kms_client`` es un cliente con la interfaz de boto3 KMS (``get_public_key``,
    ``sign``); se inyecta para poder testear sin nube.
    """

    def __init__(self, key_id: str, kms_client: Any) -> None:
        self._kms = kms_client
        self._key_id = key_id
        der_pub = kms_client.get_public_key(KeyId=key_id)["PublicKey"]
        # En el SPKI de una clave secp256k1, los últimos 64 bytes son X‖Y.
        self._public_key = keys.PublicKey(der_pub[-64:])
        self._address = self._public_key.to_checksum_address()

    @property
    def address(self) -> str:
        return self._address

    def sign_hash(self, hash_hex: str) -> str:
        digest = _digest_bytes(hash_hex)
        der_sig = self._kms.sign(
            KeyId=self._key_id,
            Message=digest,
            MessageType="DIGEST",
            SigningAlgorithm="ECDSA_SHA_256",
        )["Signature"]
        r, s = _decode_der_signature(der_sig)
        if s > _SECP256K1_N // 2:  # low-s (EIP-2)
            s = _SECP256K1_N - s
        v = self._recover_v(digest, r, s)
        return "0x" + r.to_bytes(32, "big").hex() + s.to_bytes(32, "big").hex() + bytes([v]).hex()

    def _recover_v(self, digest: bytes, r: int, s: int) -> int:
        """Recupera el byte de recuperación (27/28) probando cuál reproduce la address."""
        for recovery_id in (0, 1):
            candidate = keys.Signature(vrs=(recovery_id, r, s))
            recovered = candidate.recover_public_key_from_msg_hash(digest)
            if recovered.to_checksum_address().lower() == self._address.lower():
                return recovery_id + 27
        raise ValueError("no se pudo recuperar v: la firma no corresponde a la address del KMS")
