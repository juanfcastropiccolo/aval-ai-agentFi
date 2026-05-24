"""Tarea 11: M-de-N por HTTP — junta M de nodos reales, tolera uno que deniega, auth enforced."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

pytest.importorskip("safe_eth")
pytest.importorskip("fastapi")

from eth_account import Account  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aval.execution.cosigner_client import CosignerClient  # noqa: E402
from aval.execution.node import build_node_app  # noqa: E402
from aval.execution.signer import RawKeySigner  # noqa: E402
from aval.execution.transfer_executor import SafeTransferExecutor, TokenSpec  # noqa: E402
from aval.models import Mandate  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit  # noqa: E402

CHAIN = 11155111
SAFE = "0x" + "11" * 20
BOB = "0x" + "33" * 20
OTHER = "0x" + "44" * 20
TOKEN = "tok"


def _mandate(allowed_recipient: str) -> Mandate:
    return Mandate(
        agent_id="a",
        granted_by="dev",
        policies=[
            SpendLimit(token="ETH", per_tx=Decimal("5")),
            RecipientAllowlist(recipients={allowed_recipient.lower()}),
            AllowedMethods(methods={"transfer_native"}),
        ],
        token_decimals={"ETH": 18},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


def _node(mandate: Mandate, token: str = TOKEN) -> CosignerClient:
    signer = RawKeySigner(Account.create().key.hex())
    app = build_node_app(signer, {SAFE: mandate}, auth_token=token, default_chain=str(CHAIN))
    return CosignerClient(client=TestClient(app), auth_token=TOKEN)


def _chain() -> MagicMock:
    chain = MagicMock()
    chain.get_nonce.return_value = 0
    chain.exec_transaction.return_value = "0x" + "ab" * 32
    return chain


def test_gathers_m_over_http_tolerating_one_denial() -> None:
    chain = _chain()
    # nodos 1 y 2 permiten a BOB; nodo 3 tiene un mandato que solo permite OTHER (deniega BOB)
    cosigners = [_node(_mandate(BOB)), _node(_mandate(BOB)), _node(_mandate(OTHER))]
    ex = SafeTransferExecutor(
        safe_address=SAFE,
        chain_id=CHAIN,
        agent_private_key=Account.create().key.hex(),
        chain=chain,
        cosigners=cosigners,
        threshold_m=2,
        tokens={"ETH": TokenSpec(None, 18)},
    )
    out = ex.transfer(BOB, "1", "ETH")
    assert out["executed"] is True  # juntó 2 co-firmas de los nodos que permiten
    chain.exec_transaction.assert_called_once()


def test_wrong_auth_token_fails_closed() -> None:
    chain = _chain()
    signer = RawKeySigner(Account.create().key.hex())
    app = build_node_app(
        signer, {SAFE: _mandate(BOB)}, auth_token="correcto", default_chain=str(CHAIN)
    )
    bad_client = CosignerClient(client=TestClient(app), auth_token="incorrecto")
    ex = SafeTransferExecutor(
        safe_address=SAFE,
        chain_id=CHAIN,
        agent_private_key=Account.create().key.hex(),
        chain=chain,
        cosigners=[bad_client],
        threshold_m=1,
        tokens={"ETH": TokenSpec(None, 18)},
    )
    out = ex.transfer(BOB, "1", "ETH")
    assert out["executed"] is False  # 401 → co-autorización no obtenida → fail-closed
    chain.exec_transaction.assert_not_called()
