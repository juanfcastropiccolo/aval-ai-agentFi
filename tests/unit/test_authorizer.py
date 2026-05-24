"""Tarea 7: Authorizer — ALLOW co-firma (recuperable a aval); DENY no firma, con código."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from eth_account import Account

pytest.importorskip("safe_eth")

from aval.core.engine import Engine  # noqa: E402
from aval.core.resolver import EVMResolver, TokenInfo  # noqa: E402
from aval.execution.authorizer import Authorizer  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL  # noqa: E402
from aval.execution.safe_tx import build_erc20_transfer, signer_of  # noqa: E402
from aval.execution.signer import RawKeySigner  # noqa: E402
from aval.models import Mandate, ReasonCode, Verdict  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit  # noqa: E402

CHAIN = 11155111
SAFE = "0x" + "11" * 20
USDC = "0x" + "aa" * 20
ALICE = "0x" + "33" * 20
MALLORY = "0x" + "44" * 20


def _authorizer() -> Authorizer:
    resolver = EVMResolver.from_tool_names(
        {SAFE_TX_TOOL}, tokens={USDC.lower(): TokenInfo("USDC", 6)}
    )
    engine = Engine(resolver)
    aval_key = Account.create().key.hex()
    return Authorizer(engine, RawKeySigner(aval_key))


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
        expires_at=datetime(2026, 5, 22, tzinfo=UTC) + timedelta(days=1),
    )


NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _req(recipient: str, usdc: int, nonce: int = 0):
    return build_erc20_transfer(
        safe_address=SAFE,
        chain_id=CHAIN,
        token=USDC,
        recipient=recipient,
        amount_raw=usdc * 10**6,
        nonce=nonce,
    )


def test_allow_returns_signature_recoverable_to_aval() -> None:
    auth = _authorizer()
    req = _req(ALICE, 1000)
    resp = auth.authorize(req, _mandate(), now=NOW)
    assert resp.decision.verdict is Verdict.ALLOW
    assert resp.aval_signature is not None
    assert req.safe_tx_hash is not None
    assert signer_of(req.safe_tx_hash, resp.aval_signature).lower() == auth.address.lower()


def test_deny_recipient_no_signature_with_code() -> None:
    auth = _authorizer()
    resp = auth.authorize(_req(MALLORY, 100), _mandate(), now=NOW)
    assert resp.decision.verdict is Verdict.DENY
    assert resp.aval_signature is None
    assert resp.decision.reason_code is ReasonCode.RECIPIENT_NOT_ALLOWED


def test_deny_over_limit_no_signature() -> None:
    auth = _authorizer()
    resp = auth.authorize(_req(ALICE, 9000), _mandate(), now=NOW)
    assert resp.decision.verdict is Verdict.DENY
    assert resp.decision.reason_code is ReasonCode.SPEND_LIMIT_PER_TX
    assert resp.aval_signature is None


def test_expired_mandate_no_signature() -> None:
    auth = _authorizer()
    m = _mandate().model_copy(update={"expires_at": NOW - timedelta(seconds=1)})
    resp = auth.authorize(_req(ALICE, 100), m, now=NOW)
    assert resp.decision.reason_code is ReasonCode.MANDATE_EXPIRED
    assert resp.aval_signature is None
