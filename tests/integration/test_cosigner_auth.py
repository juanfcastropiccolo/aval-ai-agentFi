"""Tarea 5: autenticación del co-signer — 401 sin token / inválido, 200 con token (FR-4, AC-3)."""

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("safe_eth")
pytest.importorskip("fastapi")

from eth_account import Account  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aval.core.engine import Engine  # noqa: E402
from aval.core.resolver import EVMResolver, TokenInfo  # noqa: E402
from aval.execution.authorizer import Authorizer  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL  # noqa: E402
from aval.execution.safe_tx import build_erc20_transfer  # noqa: E402
from aval.execution.service import create_app  # noqa: E402
from aval.execution.signer import RawKeySigner  # noqa: E402
from aval.models import Mandate  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist  # noqa: E402

TOKEN = "super-secret-token"
SAFE = "0x" + "11" * 20
USDC = "0x" + "aa" * 20
ALICE = "0x" + "33" * 20


def _client() -> TestClient:
    resolver = EVMResolver.from_tool_names(
        {SAFE_TX_TOOL}, tokens={USDC.lower(): TokenInfo("USDC", 6)}
    )
    authorizer = Authorizer(Engine(resolver), RawKeySigner(Account.create().key.hex()))
    mandate = Mandate(
        agent_id="a",
        granted_by="dev",
        policies=[
            RecipientAllowlist(recipients={ALICE.lower()}),
            AllowedMethods(methods={"transfer"}),
        ],
        token_decimals={"USDC": 6},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    app = create_app(authorizer, {SAFE: mandate}, auth_token=TOKEN)
    return TestClient(app)


def _payload() -> dict:
    req = build_erc20_transfer(
        safe_address=SAFE,
        chain_id=11155111,
        token=USDC,
        recipient=ALICE,
        amount_raw=1_000_000,
        nonce=0,
    )
    return req.model_dump()


def test_no_token_is_401() -> None:
    r = _client().post("/authorize", json=_payload())
    assert r.status_code == 401


def test_wrong_token_is_401() -> None:
    r = _client().post("/authorize", json=_payload(), headers={"Authorization": "Bearer mal"})
    assert r.status_code == 401


def test_valid_token_is_200() -> None:
    r = _client().post("/authorize", json=_payload(), headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert r.json()["decision"]["verdict"] == "allow"


def test_executed_endpoint_also_requires_auth() -> None:
    r = _client().post(
        "/executed",
        json={"safe_address": SAFE, "safe_tx_hash": "0x" + "ab" * 32, "tx_hash": "0x" + "cd" * 32},
    )
    assert r.status_code == 401
