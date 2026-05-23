"""Tarea 6: decode de SafeTx → ProposedAction, con fail-closed en delegatecall/lote."""

from decimal import Decimal

import pytest

pytest.importorskip("safe_eth")

from aval.core.resolver import EVMResolver, ResolveStatus, TokenInfo  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL, decode_safe_tx  # noqa: E402
from aval.execution.safe_tx import build_erc20_transfer, build_native_transfer  # noqa: E402

SAFE = "0x" + "11" * 20
USDC = "0x" + "aa" * 20
BOB = "0x" + "33" * 20
CHAIN = 11155111


def _resolver() -> EVMResolver:
    return EVMResolver.from_tool_names({SAFE_TX_TOOL}, tokens={USDC.lower(): TokenInfo("USDC", 6)})


def test_decodes_erc20_transfer() -> None:
    req = build_erc20_transfer(
        safe_address=SAFE, chain_id=CHAIN, token=USDC, recipient=BOB, amount_raw=4_000_000, nonce=0
    )
    res = decode_safe_tx(_resolver(), req)
    assert res.status is ResolveStatus.RESOLVED
    assert res.action is not None
    assert res.action.token == "USDC"
    assert res.action.amount == Decimal("4")
    assert res.action.recipient == BOB.lower()
    assert res.action.method == "transfer"


def test_decodes_native_transfer() -> None:
    req = build_native_transfer(
        safe_address=SAFE, chain_id=CHAIN, recipient=BOB, amount_raw=10**18, nonce=0
    )
    res = decode_safe_tx(_resolver(), req)
    assert res.status is ResolveStatus.RESOLVED
    assert res.action is not None
    assert res.action.token == "ETH"
    assert res.action.amount == Decimal("1")


def test_delegatecall_fails_closed() -> None:
    req = build_erc20_transfer(
        safe_address=SAFE, chain_id=CHAIN, token=USDC, recipient=BOB, amount_raw=1, nonce=0
    ).model_copy(update={"operation": 1})
    res = decode_safe_tx(_resolver(), req)
    assert res.status is ResolveStatus.UNRESOLVABLE
    assert "delegatecall" in res.reason


def test_unknown_selector_fails_closed() -> None:
    # SafeTx hacia un contrato con un selector no reconocido (proxy de un "lote")
    req = build_native_transfer(
        safe_address=SAFE, chain_id=CHAIN, recipient=USDC, amount_raw=0, nonce=0
    ).model_copy(update={"data": "0xdeadbeef" + "00" * 32, "value": 0})
    res = decode_safe_tx(_resolver(), req)
    assert res.status is ResolveStatus.UNRESOLVABLE
