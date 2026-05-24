"""Despliegue de la cuenta custodia (Safe) con una lista de owners y umbral parametrizables.

Generaliza el 2-de-2 a **N+1 owners / umbral M+1** (agente + N co-autorizadores aval,
M co-firmas requeridas). En redes reales se usan los singletons canónicos de Safe ya
desplegados; en cadenas locales/efímeras se despliegan master copy y proxy factory.
"""

from __future__ import annotations

from typing import Any

# Direcciones canónicas de Safe v1.4.1 (deterministas en la mayoría de redes, incl. Sepolia).
CANONICAL_SAFE_SINGLETON = "0x41675C099F32341bf84BFc5382aF534df5C7461a"
CANONICAL_PROXY_FACTORY = "0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67"
CANONICAL_FALLBACK_HANDLER = "0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99"


def deploy_safe(
    ethereum_client: Any,
    deployer_account: Any,
    owners: list[str],
    threshold: int,
    *,
    master_copy: str = CANONICAL_SAFE_SINGLETON,
    proxy_factory: str = CANONICAL_PROXY_FACTORY,
    fallback_handler: str = CANONICAL_FALLBACK_HANDLER,
) -> str:
    """Crea un Safe con ``owners`` y ``threshold`` usando los singletons canónicos.

    Para una config M-de-N de aval: ``owners = [agente, aval_1, …, aval_N]`` y
    ``threshold = M + 1``. Devuelve la dirección del Safe.
    """
    from eth_utils import to_checksum_address  # type: ignore[attr-defined]
    from safe_eth.safe.safe import SafeV141

    if not 1 <= threshold <= len(owners):
        raise ValueError(f"threshold {threshold} fuera de rango para {len(owners)} owners")
    sent = SafeV141.create(
        ethereum_client,
        deployer_account,
        to_checksum_address(master_copy),
        owners=[to_checksum_address(o) for o in owners],
        threshold=threshold,
        fallback_handler=to_checksum_address(fallback_handler),
        proxy_factory_address=to_checksum_address(proxy_factory),
    )
    return sent.contract_address


def deploy_local_safe(
    ethereum_client: Any, deployer_account: Any, owners: list[str], threshold: int
) -> str:
    """Igual que :func:`deploy_safe` pero desplegando master copy y proxy factory.

    Para cadenas locales/efímeras (tests) donde los singletons canónicos no existen.
    """
    from safe_eth.safe.proxy_factory import ProxyFactoryV141
    from safe_eth.safe.safe import SafeV141

    if not 1 <= threshold <= len(owners):  # validar antes de gastar gas
        raise ValueError(f"threshold {threshold} fuera de rango para {len(owners)} owners")

    master = SafeV141.deploy_contract(ethereum_client, deployer_account).contract_address
    factory = ProxyFactoryV141.deploy_contract(ethereum_client, deployer_account).contract_address
    return deploy_safe(
        ethereum_client,
        deployer_account,
        owners,
        threshold,
        master_copy=master,
        proxy_factory=factory,
    )
