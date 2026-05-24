"""Tarea 8: despliegue de un Safe N+1 owners / umbral M+1 (EVM in-process)."""

import pytest

pytest.importorskip("safe_eth")
pytest.importorskip("eth_tester")

from eth_account import Account  # noqa: E402
from web3 import EthereumTesterProvider, Web3  # noqa: E402

from aval.execution.deploy import deploy_local_safe  # noqa: E402


def test_deploy_safe_3_owners_threshold_2() -> None:
    from safe_eth.eth import EthereumClient
    from safe_eth.safe.safe import Safe

    w3 = Web3(EthereumTesterProvider())
    funder = w3.eth.accounts[0]
    deployer, agent, aval1, aval2 = (Account.create() for _ in range(4))
    w3.eth.send_transaction(
        {"from": funder, "to": deployer.address, "value": w3.to_wei(50, "ether")}
    )
    client = EthereumClient()
    client.w3 = w3

    owners = [agent.address, aval1.address, aval2.address]  # agente + 2 aval (N=2)
    safe_addr = deploy_local_safe(client, deployer, owners, threshold=2)  # M=1 → umbral 2

    safe = Safe(safe_addr, client)
    assert set(a.lower() for a in safe.retrieve_owners()) == {o.lower() for o in owners}
    assert safe.retrieve_threshold() == 2
    assert len(safe.retrieve_owners()) == 3


def test_threshold_out_of_range_rejected() -> None:
    from safe_eth.eth import EthereumClient

    w3 = Web3(EthereumTesterProvider())
    client = EthereumClient()
    client.w3 = w3
    deployer = Account.create()
    with pytest.raises(ValueError):
        deploy_local_safe(client, deployer, [Account.create().address], threshold=2)
