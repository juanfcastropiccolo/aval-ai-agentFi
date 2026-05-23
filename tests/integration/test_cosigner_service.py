"""Tarea 8: servicio co-signer por HTTP — ALLOW→firma, DENY→{code,reason}, fail-closed."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

pytest.importorskip("safe_eth")
pytest.importorskip("fastapi")

from eth_account import Account  # noqa: E402

from aval.core.engine import Engine  # noqa: E402
from aval.core.resolver import EVMResolver, TokenInfo  # noqa: E402
from aval.execution.authorizer import Authorizer  # noqa: E402
from aval.execution.cosigner_client import CosignerClient, CosignerUnavailable  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL  # noqa: E402
from aval.execution.safe_tx import build_erc20_transfer, signer_of  # noqa: E402
from aval.execution.service import create_app  # noqa: E402
from aval.models import Mandate, ReasonCode, Verdict  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit  # noqa: E402

CHAIN = 11155111
SAFE = "0x" + "11" * 20
USDC = "0x" + "aa" * 20
ALICE = "0x" + "33" * 20
MALLORY = "0x" + "44" * 20


def _client_and_addr() -> tuple[CosignerClient, str]:
    resolver = EVMResolver.from_tool_names(
        {SAFE_TX_TOOL}, tokens={USDC.lower(): TokenInfo("USDC", 6)}
    )
    engine = Engine(resolver)
    authorizer = Authorizer(engine, Account.create().key.hex())
    mandate = Mandate(
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
    app = create_app(authorizer, {SAFE: mandate})
    # TestClient (httpx.Client) hace el puente sync↔ASGI en proceso, ejercitando el
    # mismo CosignerClient que usaría el agente contra el servicio real.
    from fastapi.testclient import TestClient

    return CosignerClient(client=TestClient(app)), authorizer.address


def _req(recipient: str, usdc: int, nonce: int = 0):
    return build_erc20_transfer(
        safe_address=SAFE,
        chain_id=CHAIN,
        token=USDC,
        recipient=recipient,
        amount_raw=usdc * 10**6,
        nonce=nonce,
    )


def test_allow_over_http_returns_signature() -> None:
    client, aval_addr = _client_and_addr()
    req = _req(ALICE, 1000)
    resp = client.authorize(req)
    assert resp.decision.verdict is Verdict.ALLOW
    assert resp.aval_signature is not None
    assert req.safe_tx_hash is not None
    assert signer_of(req.safe_tx_hash, resp.aval_signature).lower() == aval_addr.lower()


def test_deny_over_http_has_code_no_signature() -> None:
    client, _ = _client_and_addr()
    resp = client.authorize(_req(MALLORY, 100))
    assert resp.decision.verdict is Verdict.DENY
    assert resp.decision.reason_code is ReasonCode.RECIPIENT_NOT_ALLOWED
    assert resp.aval_signature is None


def test_unknown_safe_is_denied() -> None:
    client, _ = _client_and_addr()
    req = build_erc20_transfer(
        safe_address="0x" + "99" * 20,
        chain_id=CHAIN,
        token=USDC,
        recipient=ALICE,
        amount_raw=1,
        nonce=0,
    )
    resp = client.authorize(req)
    assert resp.decision.verdict is Verdict.DENY
    assert "sin mandato registrado" in resp.decision.reason


def test_unreachable_cosigner_raises_unavailable() -> None:
    # Cliente apuntando a un transporte que siempre falla la conexión.
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    http = httpx.Client(transport=httpx.MockTransport(_boom), base_url="http://down")
    client = CosignerClient(client=http)
    with pytest.raises(CosignerUnavailable):
        client.authorize(_req(ALICE, 100))
