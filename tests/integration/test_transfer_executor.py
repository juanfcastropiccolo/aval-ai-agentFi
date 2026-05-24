"""Tarea 11: orquestación transfer_funds — ALLOW ejecuta, DENY/caído no ejecutan (fail-closed)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest

pytest.importorskip("safe_eth")
pytest.importorskip("fastapi")

from eth_account import Account  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aval.adapters.adk import make_transfer_tool  # noqa: E402
from aval.core.engine import Engine  # noqa: E402
from aval.core.resolver import EVMResolver, TokenInfo  # noqa: E402
from aval.execution.authorizer import Authorizer  # noqa: E402
from aval.execution.cosigner_client import CosignerClient  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL  # noqa: E402
from aval.execution.service import create_app  # noqa: E402
from aval.execution.signer import RawKeySigner  # noqa: E402
from aval.execution.transfer_executor import SafeTransferExecutor, TokenSpec  # noqa: E402
from aval.models import Mandate  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit  # noqa: E402

CHAIN = 11155111
SAFE = "0x" + "11" * 20
USDC = "0x" + "aa" * 20
ALICE = "0x" + "33" * 20
MALLORY = "0x" + "44" * 20
AGENT_KEY = Account.create().key.hex()


def _mandate() -> Mandate:
    return Mandate(
        agent_id="agent-1",
        granted_by="dev",
        policies=[
            SpendLimit(token="USDC", per_tx=Decimal("5000")),
            RecipientAllowlist(recipients={ALICE.lower()}),
            AllowedMethods(methods={"transfer"}),
        ],
        token_decimals={"USDC": 6},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


def _live_cosigner() -> CosignerClient:
    resolver = EVMResolver.from_tool_names(
        {SAFE_TX_TOOL}, tokens={USDC.lower(): TokenInfo("USDC", 6)}
    )
    authorizer = Authorizer(Engine(resolver), RawKeySigner(Account.create().key.hex()))
    app = create_app(authorizer, {SAFE: _mandate()})
    return CosignerClient(client=TestClient(app))


def _executor(cosigner: CosignerClient, chain: MagicMock) -> SafeTransferExecutor:
    return SafeTransferExecutor(
        safe_address=SAFE,
        chain_id=CHAIN,
        agent_private_key=AGENT_KEY,
        chain=chain,
        cosigner=cosigner,
        tokens={"USDC": TokenSpec(USDC, 6), "ETH": TokenSpec(None, 18)},
    )


def _chain_mock() -> MagicMock:
    chain = MagicMock()
    chain.get_nonce.return_value = 0
    chain.exec_transaction.return_value = "0x" + "ab" * 32
    return chain


def test_allow_executes_onchain() -> None:
    chain = _chain_mock()
    ex = _executor(_live_cosigner(), chain)
    out = ex.transfer(ALICE, 1000, "USDC")
    assert out["executed"] is True
    assert out["tx_hash"] == "0x" + "ab" * 32
    chain.exec_transaction.assert_called_once()


def test_deny_does_not_execute() -> None:
    chain = _chain_mock()
    ex = _executor(_live_cosigner(), chain)
    out = ex.transfer(MALLORY, 100, "USDC")  # destino no permitido
    assert out["executed"] is False
    assert out["reason_code"] == "recipient_not_allowed"
    chain.exec_transaction.assert_not_called()


def test_over_limit_does_not_execute() -> None:
    chain = _chain_mock()
    ex = _executor(_live_cosigner(), chain)
    out = ex.transfer(ALICE, 9000, "USDC")
    assert out["executed"] is False
    assert out["reason_code"] == "spend_limit_per_tx"
    chain.exec_transaction.assert_not_called()


def test_cosigner_unavailable_fails_closed() -> None:
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    down = CosignerClient(
        client=httpx.Client(transport=httpx.MockTransport(_boom), base_url="http://x")
    )
    chain = _chain_mock()
    ex = _executor(down, chain)
    out = ex.transfer(ALICE, 100, "USDC")
    assert out["executed"] is False
    assert "inalcanzable" in out["reason"]
    chain.exec_transaction.assert_not_called()


def test_unknown_token_does_not_execute() -> None:
    chain = _chain_mock()
    ex = _executor(_live_cosigner(), chain)
    out = ex.transfer(ALICE, 1, "DOGE")
    assert out["executed"] is False
    chain.exec_transaction.assert_not_called()


def test_make_transfer_tool_delegates() -> None:
    chain = _chain_mock()
    ex = _executor(_live_cosigner(), chain)
    tool = make_transfer_tool(ex)
    out = tool(recipient=ALICE, amount=1000, token="USDC")
    assert out["executed"] is True
