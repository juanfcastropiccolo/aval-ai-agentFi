"""Tarea 9: freshness — binding a nonce (AC-5/6) y ventana wall-clock corta (FR-5)."""

from datetime import UTC, datetime, timedelta

import pytest
from eth_account import Account

pytest.importorskip("safe_eth")

from aval.core.engine import Engine  # noqa: E402
from aval.core.resolver import EVMResolver, TokenInfo  # noqa: E402
from aval.execution.authorizer import Authorizer  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL  # noqa: E402
from aval.execution.safe_tx import build_erc20_transfer, signer_of  # noqa: E402
from aval.execution.signer import RawKeySigner  # noqa: E402
from aval.models import Mandate  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist  # noqa: E402

CHAIN = 11155111
SAFE = "0x" + "11" * 20
USDC = "0x" + "aa" * 20
ALICE = "0x" + "33" * 20
NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _authorizer(window_s: int = 120) -> Authorizer:
    resolver = EVMResolver.from_tool_names(
        {SAFE_TX_TOOL}, tokens={USDC.lower(): TokenInfo("USDC", 6)}
    )
    return Authorizer(
        Engine(resolver), RawKeySigner(Account.create().key.hex()), freshness_window_s=window_s
    )


def _mandate() -> Mandate:
    return Mandate(
        agent_id="a",
        granted_by="dev",
        policies=[
            RecipientAllowlist(recipients={ALICE.lower()}),
            AllowedMethods(methods={"transfer"}),
        ],
        token_decimals={"USDC": 6},
        expires_at=NOW + timedelta(days=1),
    )


def _req(nonce: int):
    return build_erc20_transfer(
        safe_address=SAFE,
        chain_id=CHAIN,
        token=USDC,
        recipient=ALICE,
        amount_raw=10**6,
        nonce=nonce,
    )


def test_signature_for_nonce_n_does_not_validate_for_next_nonce() -> None:
    auth = _authorizer()
    req0 = _req(0)
    resp = auth.authorize(req0, _mandate(), now=NOW)
    assert resp.aval_signature is not None

    req1 = _req(1)  # misma operación, nonce siguiente → otro hash
    assert req1.safe_tx_hash is not None
    # la firma emitida para nonce 0 NO recupera al firmante sobre el hash de nonce 1
    assert signer_of(req1.safe_tx_hash, resp.aval_signature).lower() != auth.address.lower()


def test_authorization_is_fresh_within_window_and_stale_after() -> None:
    auth = _authorizer(window_s=120)
    req = _req(0)
    auth.authorize(req, _mandate(), now=NOW)
    assert req.safe_tx_hash is not None
    assert auth.is_fresh(req.safe_tx_hash, NOW + timedelta(seconds=60)) is True
    assert auth.is_fresh(req.safe_tx_hash, NOW + timedelta(seconds=121)) is False


def test_never_authorized_hash_is_not_fresh() -> None:
    auth = _authorizer()
    assert auth.is_fresh("0x" + "ab" * 32, NOW) is False
