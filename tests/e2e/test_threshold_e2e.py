"""Tarea 12: E2E de umbral M-de-N on-chain (EVM in-process).

Despliega un Safe con N+1 owners / umbral M+1 y demuestra:
- con agente + M co-firmas de aval → `execTransaction` ejecuta;
- con menos firmas que el umbral → revierte (no-evitabilidad del umbral);
- una co-firma producida por un `KmsSigner` (fake-KMS) es **aceptada on-chain** (AC-7).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

pytest.importorskip("safe_eth")
pytest.importorskip("eth_tester")
pytest.importorskip("fastapi")

from eth_account import Account  # noqa: E402
from eth_keys import keys  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from web3 import EthereumTesterProvider, Web3  # noqa: E402

from aval.execution.chain import SafeChain  # noqa: E402
from aval.execution.cosigner_client import CosignerClient  # noqa: E402
from aval.execution.deploy import deploy_local_safe  # noqa: E402
from aval.execution.node import build_node_app  # noqa: E402
from aval.execution.safe_tx import (  # noqa: E402
    build_native_transfer,
    combine_signatures,
    sign_safe_tx_hash,
)
from aval.execution.signer import KmsSigner, RawKeySigner  # noqa: E402
from aval.execution.transfer_executor import SafeTransferExecutor, TokenSpec  # noqa: E402
from aval.models import Mandate  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit  # noqa: E402

_SPKI_PREFIX = bytes.fromhex("3056301006072a8648ce3d020106052b8104000a034200")


def _der_int(x: int) -> bytes:
    b = x.to_bytes(32, "big").lstrip(b"\x00") or b"\x00"
    if b[0] & 0x80:
        b = b"\x00" + b
    return b"\x02" + bytes([len(b)]) + b


class FakeKmsClient:
    """Imita boto3 KMS firmando con una clave secp256k1 local real."""

    def __init__(self) -> None:
        self._priv = keys.PrivateKey(os.urandom(32))

    def get_public_key(self, KeyId: str) -> dict[str, bytes]:  # noqa: N803
        return {"PublicKey": _SPKI_PREFIX + b"\x04" + self._priv.public_key.to_bytes()}

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):  # noqa: N803
        sig = self._priv.sign_msg_hash(Message)
        der = _der_int(sig.r) + _der_int(sig.s)
        return {"Signature": b"\x30" + bytes([len(der)]) + der}


def _w3_and_funder():  # type: ignore[no-untyped-def]
    w3 = Web3(EthereumTesterProvider())
    return w3, w3.eth.accounts[0]


def _client(w3, signer, mandate, safe):  # type: ignore[no-untyped-def]
    app = build_node_app(
        signer, {safe: mandate}, auth_token="tok", default_chain=str(w3.eth.chain_id)
    )
    return CosignerClient(client=TestClient(app), auth_token="tok")


def _mandate(safe, bob):  # type: ignore[no-untyped-def]
    return Mandate(
        agent_id="agent-1",
        granted_by="cfo",
        policies=[
            SpendLimit(token="ETH", per_tx=Decimal("5")),
            RecipientAllowlist(recipients={bob.address.lower()}),
            AllowedMethods(methods={"transfer_native"}),
        ],
        token_decimals={"ETH": 18},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


def test_threshold_executes_and_subthreshold_reverts() -> None:
    from safe_eth.eth import EthereumClient

    w3, funder = _w3_and_funder()
    deployer, agent, aval1, aval2, bob = (Account.create() for _ in range(5))
    for a in (deployer, agent):
        w3.eth.send_transaction({"from": funder, "to": a.address, "value": w3.to_wei(50, "ether")})
    client = EthereumClient()
    client.w3 = w3

    # Safe 3-de-3: agente + aval1 + aval2 (N=2 aval, M=2 → umbral 3).
    owners = [agent.address, aval1.address, aval2.address]
    safe = deploy_local_safe(client, deployer, owners, threshold=3)
    w3.eth.send_transaction({"from": funder, "to": safe, "value": w3.to_wei(10, "ether")})

    mandate = _mandate(safe, bob)
    cosigners = [
        _client(w3, RawKeySigner(aval1.key.hex()), mandate, safe),
        _client(w3, RawKeySigner(aval2.key.hex()), mandate, safe),
    ]
    ex = SafeTransferExecutor(
        safe_address=safe,
        chain_id=w3.eth.chain_id,
        agent_private_key=agent.key.hex(),
        chain=SafeChain(w3, safe),
        cosigners=cosigners,
        threshold_m=2,
        tokens={"ETH": TokenSpec(None, 18)},
    )

    before = w3.eth.get_balance(bob.address)
    out = ex.transfer(bob.address, "1", "ETH")
    assert out["executed"] is True  # agente + 2 aval = 3 firmas → umbral alcanzado
    assert w3.eth.get_balance(bob.address) - before == w3.to_wei(1, "ether")

    # Sub-umbral: agente + 1 aval (2 firmas) sobre un Safe de umbral 3 → revierte.
    req = build_native_transfer(
        safe_address=safe,
        chain_id=w3.eth.chain_id,
        recipient=bob.address,
        amount_raw=w3.to_wei(1, "ether"),
        nonce=1,
        safe_version="1.4.1",
    )
    two_sigs = combine_signatures(
        req.safe_tx_hash,
        [
            sign_safe_tx_hash(req.safe_tx_hash, agent.key.hex()),
            sign_safe_tx_hash(req.safe_tx_hash, aval1.key.hex()),
        ],
    )
    before2 = w3.eth.get_balance(bob.address)
    with pytest.raises(Exception):  # noqa: B017 — el Safe rechaza por umbral insuficiente
        SafeChain(w3, safe).exec_transaction(req, two_sigs, agent.key.hex())
    assert w3.eth.get_balance(bob.address) == before2  # no se movió nada


def test_kms_signed_node_is_accepted_onchain() -> None:
    from safe_eth.eth import EthereumClient

    w3, funder = _w3_and_funder()
    deployer, agent, bob = (Account.create() for _ in range(3))
    for a in (deployer, agent):
        w3.eth.send_transaction({"from": funder, "to": a.address, "value": w3.to_wei(50, "ether")})
    client = EthereumClient()
    client.w3 = w3

    # Un nodo aval firma vía KMS (fake). Su address debe ser owner del Safe.
    kms_signer = KmsSigner("alias/aval", FakeKmsClient())
    owners = [agent.address, kms_signer.address]  # umbral 2 (agente + 1 aval-KMS)
    safe = deploy_local_safe(client, deployer, owners, threshold=2)
    w3.eth.send_transaction({"from": funder, "to": safe, "value": w3.to_wei(10, "ether")})

    mandate = _mandate(safe, bob)
    cosigner = _client(w3, kms_signer, mandate, safe)
    ex = SafeTransferExecutor(
        safe_address=safe,
        chain_id=w3.eth.chain_id,
        agent_private_key=agent.key.hex(),
        chain=SafeChain(w3, safe),
        cosigners=[cosigner],
        threshold_m=1,
        tokens={"ETH": TokenSpec(None, 18)},
    )

    before = w3.eth.get_balance(bob.address)
    out = ex.transfer(bob.address, "1", "ETH")
    assert out["executed"] is True  # la firma estilo-KMS fue aceptada on-chain
    assert w3.eth.get_balance(bob.address) - before == w3.to_wei(1, "ether")
