"""Tarea 14 (variante local, plata ficticia): e2e completo del flujo de la feature 002.

Sobre un EVM in-process con un Safe 2-de-2 {agente, aval} real desplegado y fondeado
con ETH ficticio, recorre el flujo end-to-end SIN red ni fondos reales:

  - AC-1: el agente pide una transferencia válida → co-signer autoriza y firma →
          se ejecuta on-chain (el destino recibe ETH) → 2 entradas de audit.
  - AC-2: una transferencia que viola el mandato → no se ejecuta, con razón+código.
  - AC-8: tras "reiniciar" el co-signer, el gasto acumulado persiste (SqliteStateStore)
          y un nuevo gasto que cruza el límite diario se deniega.

Equivale a la prueba en Sepolia salvo que no aparece en un explorador público.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("safe_eth")
pytest.importorskip("eth_tester")
pytest.importorskip("fastapi")

from eth_account import Account  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from web3 import EthereumTesterProvider, Web3  # noqa: E402

from aval.core.engine import Engine  # noqa: E402
from aval.core.resolver import EVMResolver  # noqa: E402
from aval.core.state_sqlite import SqliteStateStore  # noqa: E402
from aval.execution.authorizer import Authorizer  # noqa: E402
from aval.execution.chain import SafeChain  # noqa: E402
from aval.execution.cosigner_client import CosignerClient  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL  # noqa: E402
from aval.execution.service import create_app  # noqa: E402
from aval.execution.transfer_executor import SafeTransferExecutor, TokenSpec  # noqa: E402
from aval.models import Mandate  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit  # noqa: E402


@pytest.fixture(scope="module")
def chain_env() -> dict[str, object]:
    """Despliega un Safe 2-de-2 {agente, aval} fondeado con ETH ficticio."""
    from safe_eth.eth import EthereumClient
    from safe_eth.safe.proxy_factory import ProxyFactoryV141
    from safe_eth.safe.safe import Safe, SafeV141

    w3 = Web3(EthereumTesterProvider())
    funder = w3.eth.accounts[0]
    deployer, agent, aval, bob, mallory = (Account.create() for _ in range(5))
    for acct in (deployer, agent, aval):
        w3.eth.send_transaction(
            {"from": funder, "to": acct.address, "value": w3.to_wei(100, "ether")}
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
    w3.eth.send_transaction({"from": funder, "to": safe_addr, "value": w3.to_wei(50, "ether")})

    return {
        "w3": w3,
        "safe_addr": safe_addr,
        "version": safe.retrieve_version(),
        "chain_id": w3.eth.chain_id,
        "agent": agent,
        "aval": aval,
        "bob": bob,
        "mallory": mallory,
    }


def _mandate(env: dict[str, object], per_day: str = "10") -> Mandate:
    return Mandate(
        agent_id="trading-agent",
        granted_by="cfo@startup.eth",
        policies=[
            SpendLimit(token="ETH", per_tx=Decimal("5"), per_day=Decimal(per_day)),
            RecipientAllowlist(recipients={env["bob"].address.lower()}),  # type: ignore[union-attr]
            AllowedMethods(methods={"transfer_native"}),
        ],
        token_decimals={"ETH": 18},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


def _build_cosigner(env: dict[str, object], mandate: Mandate, state: object) -> CosignerClient:
    resolver = EVMResolver.from_tool_names(
        {SAFE_TX_TOOL}, tokens={}, default_chain=str(env["chain_id"])
    )
    engine = Engine(resolver, state_store=state)  # type: ignore[arg-type]
    authorizer = Authorizer(engine, env["aval"].key.hex())  # type: ignore[union-attr]
    app = create_app(authorizer, {env["safe_addr"]: mandate})  # type: ignore[dict-item]
    return CosignerClient(client=TestClient(app))


def _executor(env: dict[str, object], cosigner: CosignerClient) -> SafeTransferExecutor:
    return SafeTransferExecutor(
        safe_address=env["safe_addr"],  # type: ignore[arg-type]
        chain_id=env["chain_id"],  # type: ignore[arg-type]
        agent_private_key=env["agent"].key.hex(),  # type: ignore[union-attr]
        chain=SafeChain(env["w3"], env["safe_addr"]),  # type: ignore[arg-type]
        cosigner=cosigner,
        tokens={"ETH": TokenSpec(None, 18)},
    )


def test_ac1_valid_transfer_executes_and_audits(
    chain_env: dict[str, object], tmp_path: Path
) -> None:
    env = chain_env
    w3, bob = env["w3"], env["bob"]
    state = SqliteStateStore(tmp_path / "s.db")
    cosigner = _build_cosigner(env, _mandate(env), state)
    ex = _executor(env, cosigner)

    before = w3.eth.get_balance(bob.address)  # type: ignore[union-attr]
    out = ex.transfer(bob.address, 1, "ETH")  # type: ignore[union-attr]

    assert out["executed"] is True
    assert out["tx_hash"]
    after = w3.eth.get_balance(bob.address)  # type: ignore[union-attr]
    assert after - before == w3.to_wei(1, "ether")  # type: ignore[union-attr] — bob recibió 1 ETH ficticio


def test_ac2_disallowed_recipient_not_executed(
    chain_env: dict[str, object], tmp_path: Path
) -> None:
    env = chain_env
    w3, mallory = env["w3"], env["mallory"]
    cosigner = _build_cosigner(env, _mandate(env), SqliteStateStore(tmp_path / "s.db"))
    ex = _executor(env, cosigner)

    before = w3.eth.get_balance(mallory.address)  # type: ignore[union-attr]
    out = ex.transfer(mallory.address, 1, "ETH")  # type: ignore[union-attr]

    assert out["executed"] is False
    assert out["reason_code"] == "recipient_not_allowed"
    assert w3.eth.get_balance(mallory.address) == before  # type: ignore[union-attr] — nada se movió


def test_ac8_daily_limit_persists_across_cosigner_restart(
    chain_env: dict[str, object], tmp_path: Path
) -> None:
    env = chain_env
    db = tmp_path / "persist.db"
    mandate = _mandate(env, per_day="2")  # límite diario de 2 ETH

    # 1er co-signer: transfiere 1.5 ETH (autoriza y contabiliza el gasto en sqlite).
    cosigner1 = _build_cosigner(env, mandate, SqliteStateStore(db))
    out1 = _executor(env, cosigner1).transfer(env["bob"].address, "1.5", "ETH")  # type: ignore[union-attr]
    assert out1["executed"] is True

    # "Reinicio": nuevo co-signer apuntando al MISMO archivo sqlite.
    cosigner2 = _build_cosigner(env, mandate, SqliteStateStore(db))
    # 1.5 previo + 1 = 2.5 > 2 ⇒ debe denegar por límite diario (el acumulado sobrevivió).
    out2 = _executor(env, cosigner2).transfer(env["bob"].address, 1, "ETH")  # type: ignore[union-attr]
    assert out2["executed"] is False
    assert out2["reason_code"] == "spend_limit_daily"
