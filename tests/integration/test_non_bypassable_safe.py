"""Tarea 13: no-evitabilidad — un Safe 2-de-2 real rechaza 1 firma y ejecuta con 2.

Corre sobre un EVM in-process (eth-tester): despliega un Safe 2-de-2 {agente, aval}
y demuestra el corazón de la garantía de la feature 002:

  - `execTransaction` con SOLO la firma del agente → revierte (no se mueve dinero).
  - con las firmas de agente + aval (combinadas por nuestro código) → ejecuta.

De paso valida que nuestro `compute_safe_tx_hash` coincide con el hash que el
propio contrato Safe espera (verdad de fondo: si no coincidiera, la firma de aval
no validaría en una red real).
"""

from __future__ import annotations

import pytest

pytest.importorskip("safe_eth")
eth_tester = pytest.importorskip("eth_tester")  # noqa: F841

from eth_account import Account  # noqa: E402
from web3 import EthereumTesterProvider, Web3  # noqa: E402

from aval.execution.chain import SafeChain  # noqa: E402
from aval.execution.safe_tx import (  # noqa: E402
    build_native_transfer,
    combine_signatures,
    sign_safe_tx_hash,
)

ZERO = "0x" + "00" * 20


@pytest.fixture(scope="module")
def safe_env() -> dict[str, object]:
    """Despliega un Safe 2-de-2 {agente, aval} fondeado en un EVM in-process."""
    from safe_eth.eth import EthereumClient
    from safe_eth.safe.proxy_factory import ProxyFactoryV141
    from safe_eth.safe.safe import Safe, SafeV141

    w3 = Web3(EthereumTesterProvider())
    funder = w3.eth.accounts[0]
    deployer, agent, aval, bob = (Account.create() for _ in range(4))
    for acct in (deployer, agent, aval):
        w3.eth.send_transaction(
            {"from": funder, "to": acct.address, "value": w3.to_wei(50, "ether")}
        )

    client = EthereumClient()
    client.w3 = w3

    master = SafeV141.deploy_contract(client, deployer).contract_address
    factory = ProxyFactoryV141.deploy_contract(client, deployer).contract_address
    sent = SafeV141.create(
        client,
        deployer,
        master,
        owners=[agent.address, aval.address],
        threshold=2,
        proxy_factory_address=factory,
    )
    safe_addr = sent.contract_address
    safe = Safe(safe_addr, client)
    w3.eth.send_transaction({"from": funder, "to": safe_addr, "value": w3.to_wei(5, "ether")})

    return {
        "w3": w3,
        "safe": safe,
        "safe_addr": safe_addr,
        "version": safe.retrieve_version(),
        "chain_id": w3.eth.chain_id,
        "agent": agent,
        "aval": aval,
        "bob": bob,
        "deployer": deployer,
    }


def _build_req(env: dict[str, object], nonce: int = 0):
    return build_native_transfer(
        safe_address=env["safe_addr"],
        chain_id=env["chain_id"],  # type: ignore[arg-type]
        recipient=env["bob"].address,
        amount_raw=Web3.to_wei(1, "ether"),  # type: ignore[union-attr]
        nonce=nonce,
        safe_version=env["version"],
    )


def test_safe_is_2_of_2(safe_env: dict[str, object]) -> None:
    safe = safe_env["safe"]
    assert safe.retrieve_threshold() == 2  # type: ignore[union-attr]
    assert len(safe.retrieve_owners()) == 2  # type: ignore[union-attr]


def test_our_hash_matches_the_safe_contract_hash(safe_env: dict[str, object]) -> None:
    req = _build_req(safe_env)
    safe = safe_env["safe"]
    onchain = (
        "0x"
        + safe.build_multisig_tx(  # type: ignore[union-attr]
            req.to, req.value, b"", 0, 0, 0, 0, ZERO, ZERO, safe_nonce=0
        ).safe_tx_hash.hex()
    )
    assert req.safe_tx_hash == onchain  # nuestro hash == el que el contrato espera


def test_single_signature_is_rejected(safe_env: dict[str, object]) -> None:
    env = safe_env
    req = _build_req(env)
    assert req.safe_tx_hash is not None
    chain = SafeChain(env["w3"], env["safe_addr"])  # type: ignore[arg-type]
    bob = env["bob"]
    before = env["w3"].eth.get_balance(bob.address)  # type: ignore[union-attr]

    only_agent = sign_safe_tx_hash(req.safe_tx_hash, env["agent"].key.hex())  # type: ignore[union-attr]
    with pytest.raises(Exception):  # noqa: B017 - cualquier fallo on-chain sirve: NO debe ejecutar
        chain.exec_transaction(req, only_agent, env["deployer"].key.hex())  # type: ignore[union-attr]

    after = env["w3"].eth.get_balance(bob.address)  # type: ignore[union-attr]
    assert after == before  # el dinero NO se movió


def test_two_signatures_execute(safe_env: dict[str, object]) -> None:
    env = safe_env
    req = _build_req(env, nonce=0)
    assert req.safe_tx_hash is not None
    chain = SafeChain(env["w3"], env["safe_addr"])  # type: ignore[arg-type]
    bob = env["bob"]
    before = env["w3"].eth.get_balance(bob.address)  # type: ignore[union-attr]

    agent_sig = sign_safe_tx_hash(req.safe_tx_hash, env["agent"].key.hex())  # type: ignore[union-attr]
    aval_sig = sign_safe_tx_hash(req.safe_tx_hash, env["aval"].key.hex())  # type: ignore[union-attr]
    combined = combine_signatures(req.safe_tx_hash, [agent_sig, aval_sig])

    tx_hash = chain.exec_transaction(req, combined, env["deployer"].key.hex())  # type: ignore[union-attr]
    assert tx_hash

    after = env["w3"].eth.get_balance(bob.address)  # type: ignore[union-attr]
    assert after - before == Web3.to_wei(1, "ether")  # bob recibió 1 ETH
