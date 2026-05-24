"""Tarea 9: observabilidad — decisión logueada con veredicto+código, sin secretos."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("safe_eth")

from eth_account import Account  # noqa: E402

from aval.core.engine import Engine  # noqa: E402
from aval.core.resolver import EVMResolver, TokenInfo  # noqa: E402
from aval.execution.authorizer import Authorizer  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL  # noqa: E402
from aval.execution.safe_tx import build_erc20_transfer  # noqa: E402
from aval.execution.signer import RawKeySigner  # noqa: E402
from aval.models import Mandate  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist  # noqa: E402

SAFE = "0x" + "11" * 20
USDC = "0x" + "aa" * 20
ALICE = "0x" + "33" * 20


def test_decision_is_logged_without_secrets(caplog: pytest.LogCaptureFixture) -> None:
    aval_key = Account.create().key.hex()
    resolver = EVMResolver.from_tool_names(
        {SAFE_TX_TOOL}, tokens={USDC.lower(): TokenInfo("USDC", 6)}
    )
    authorizer = Authorizer(Engine(resolver), RawKeySigner(aval_key))
    mandate = Mandate(
        agent_id="agent-1",
        granted_by="dev",
        policies=[
            RecipientAllowlist(recipients={ALICE.lower()}),
            AllowedMethods(methods={"transfer"}),
        ],
        token_decimals={"USDC": 6},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    req = build_erc20_transfer(
        safe_address=SAFE,
        chain_id=11155111,
        token=USDC,
        recipient=ALICE,
        amount_raw=1_000_000,
        nonce=0,
    )

    with caplog.at_level(logging.INFO, logger="aval.cosigner"):
        authorizer.authorize(req, mandate)

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "verdict=allow" in logged
    assert "agent=agent-1" in logged
    assert aval_key.lstrip("0x") not in logged  # la clave NO se loguea
