"""Demo local de la feature 002: agente + aval co-firmando transferencias de un Safe 2-de-2.

Corre **sin configuración ni fondos reales**: levanta una blockchain en proceso,
despliega un Safe 2-de-2 {agente, aval}, lo fondea con ETH ficticio y recorre tres
escenarios mostrando el enforcement no-evitable end-to-end.

    python -m examples.safe_transfer_demo

Para el demo en una red pública (Sepolia) hacen falta un RPC, un Safe real y fondos
de faucet — ver el README.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from eth_account import Account
from fastapi.testclient import TestClient
from web3 import EthereumTesterProvider, Web3

from aval.core.engine import Engine
from aval.core.resolver import EVMResolver
from aval.execution.authorizer import Authorizer
from aval.execution.chain import SafeChain
from aval.execution.cosigner_client import CosignerClient
from aval.execution.decode import SAFE_TX_TOOL
from aval.execution.service import create_app
from aval.execution.signer import RawKeySigner
from aval.execution.transfer_executor import SafeTransferExecutor, TokenSpec
from aval.models import Mandate
from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit


def _deploy_safe_2of2(w3: Web3, agent: Any, aval: Any, deployer: Any) -> str:
    from safe_eth.eth import EthereumClient
    from safe_eth.safe.proxy_factory import ProxyFactoryV141
    from safe_eth.safe.safe import SafeV141

    client = EthereumClient()
    client.w3 = w3
    master = SafeV141.deploy_contract(client, deployer).contract_address
    factory = ProxyFactoryV141.deploy_contract(client, deployer).contract_address
    return SafeV141.create(
        client,
        deployer,
        master,
        owners=[agent.address, aval.address],
        threshold=2,
        proxy_factory_address=factory,
    ).contract_address


def main() -> None:
    w3 = Web3(EthereumTesterProvider())
    funder = w3.eth.accounts[0]
    deployer, agent, aval, alice, mallory = (Account.create() for _ in range(5))
    for acct in (deployer, agent, aval):
        w3.eth.send_transaction(
            {"from": funder, "to": acct.address, "value": w3.to_wei(100, "ether")}
        )

    safe = _deploy_safe_2of2(w3, agent, aval, deployer)
    w3.eth.send_transaction({"from": funder, "to": safe, "value": w3.to_wei(50, "ether")})
    chain_id = w3.eth.chain_id

    print("=" * 68)
    print(f"Safe 2-de-2 desplegado: {safe}")
    print(f"  owner 1 (agente): {agent.address}")
    print(f"  owner 2 (aval):   {aval.address}")
    print(f"  balance: {w3.from_wei(w3.eth.get_balance(safe), 'ether')} ETH (ficticio)")

    # El dev declara el mandato: ≤5 ETH/tx, ≤10 ETH/día, solo a Alice, solo transferencias.
    mandate = Mandate(
        agent_id="trading-agent",
        granted_by="cfo@startup.eth",
        policies=[
            SpendLimit(token="ETH", per_tx=Decimal("5"), per_day=Decimal("10")),
            RecipientAllowlist(recipients={alice.address.lower()}),
            AllowedMethods(methods={"transfer_native"}),
        ],
        token_decimals={"ETH": 18},
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )

    # El co-signer de aval corre como servicio (acá in-process; en prod, separado).
    resolver = EVMResolver.from_tool_names({SAFE_TX_TOOL}, tokens={}, default_chain=str(chain_id))
    authorizer = Authorizer(Engine(resolver), RawKeySigner(aval.key.hex()))
    cosigner = CosignerClient(client=TestClient(create_app(authorizer, {safe: mandate})))

    # El agente arma, junta 2 firmas y ejecuta.
    executor = SafeTransferExecutor(
        safe_address=safe,
        chain_id=chain_id,
        agent_private_key=agent.key.hex(),
        chain=SafeChain(w3, safe),
        cosigner=cosigner,
        tokens={"ETH": TokenSpec(None, 18)},
    )

    def show(titulo: str, recipient: str, amount: float) -> None:
        out = executor.transfer(recipient, amount, "ETH")
        icon = "✅" if out["executed"] else "🛑"
        print(f"\n{icon} {titulo}")
        print(f"     veredicto: {out['verdict'].upper()} ({out['reason_code']})")
        print(f"     {out['reason']}")
        if out["executed"]:
            print(
                f"     tx: {out['tx_hash'][:18]}…  Alice ahora tiene "
                f"{w3.from_wei(w3.eth.get_balance(alice.address), 'ether')} ETH"
            )

    print("\n" + "=" * 68)
    print("MANDATO: hasta 5 ETH/tx, solo a Alice, solo transferencias\n")
    show("Transferir 2 ETH a Alice (válido)", alice.address, 2)
    show("Transferir 2 ETH a un atacante (destino no permitido)", mallory.address, 2)
    show("Transferir 8 ETH a Alice (excede el límite por tx)", alice.address, 8)

    print("\n" + "=" * 68)
    print(f"Co-signer aval: {authorizer.address}")
    print("La transferencia a Alice se ejecutó porque aval co-firmó; las otras dos,")
    print("aunque el agente las intentó, nunca alcanzaron las 2 firmas → no se movió nada.")


if __name__ == "__main__":
    main()
