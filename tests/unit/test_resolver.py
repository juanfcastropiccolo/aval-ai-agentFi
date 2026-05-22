"""Tarea 7: EVM Resolver — decode de calldata, normalización y los 3 resultados."""

from decimal import Decimal

from eth_abi import encode

from aval.core.resolver import EVMResolver, ResolveStatus, TokenInfo

USDC = "0x" + "a" * 40  # token contract (6 decimales)
WETH = "0x" + "b" * 40  # token contract (18 decimales)
RECIPIENT = "0x" + "c" * 40
ROUTER = "0x" + "d" * 40

TOKENS = {USDC: TokenInfo("USDC", 6), WETH: TokenInfo("WETH", 18)}


def _resolver() -> EVMResolver:
    return EVMResolver.from_tool_names({"send_tx"}, tokens=TOKENS)


def _calldata(selector: str, types: list[str], values: list[object]) -> str:
    return "0x" + selector + encode(types, values).hex()


def test_pass_through_for_non_financial_tool() -> None:
    res = _resolver().resolve("get_balance", {"foo": "bar"})
    assert res.status is ResolveStatus.PASS_THROUGH


def test_erc20_transfer_resolves_and_normalizes() -> None:
    data = _calldata("a9059cbb", ["address", "uint256"], [RECIPIENT, 4_000_000])  # 4 USDC
    res = _resolver().resolve("send_tx", {"to": USDC, "data": data})
    assert res.status is ResolveStatus.RESOLVED
    action = res.action
    assert action is not None
    assert action.token == "USDC"
    assert action.amount == Decimal("4")
    assert action.recipient == RECIPIENT
    assert action.method == "transfer"
    assert action.selector == "0xa9059cbb"


def test_erc20_approve_has_no_recipient_but_records_spender() -> None:
    data = _calldata("095ea7b3", ["address", "uint256"], [ROUTER, 1_000_000])
    res = _resolver().resolve("send_tx", {"to": USDC, "data": data})
    assert res.status is ResolveStatus.RESOLVED
    assert res.action is not None
    assert res.action.method == "approve"
    assert res.action.recipient is None
    assert res.action.raw["spender"] == ROUTER


def test_erc20_transfer_from_resolves_recipient() -> None:
    data = _calldata("23b872dd", ["address", "address", "uint256"], [RECIPIENT, ROUTER, 2_000_000])
    res = _resolver().resolve("send_tx", {"to": USDC, "data": data})
    assert res.status is ResolveStatus.RESOLVED
    assert res.action is not None
    assert res.action.method == "transferFrom"
    assert res.action.recipient == ROUTER
    assert res.action.amount == Decimal("2")


def test_native_value_transfer() -> None:
    res = _resolver().resolve("send_tx", {"to": RECIPIENT, "value": 10**18})  # 1 ETH
    assert res.status is ResolveStatus.RESOLVED
    assert res.action is not None
    assert res.action.token == "ETH"
    assert res.action.amount == Decimal("1")
    assert res.action.method == "transfer_native"


def test_known_swap_router_resolves_token_in() -> None:
    data = _calldata(
        "38ed1739",
        ["uint256", "uint256", "address[]", "address", "uint256"],
        [5 * 10**18, 0, [WETH, USDC], RECIPIENT, 9_999_999_999],
    )
    res = _resolver().resolve("send_tx", {"to": ROUTER, "data": data})
    assert res.status is ResolveStatus.RESOLVED
    assert res.action is not None
    assert res.action.token == "WETH"  # path[0]
    assert res.action.amount == Decimal("5")
    assert res.action.method == "swapExactTokensForTokens"


def test_unknown_selector_is_unresolvable() -> None:
    data = _calldata("deadbeef", ["uint256"], [123])
    res = _resolver().resolve("send_tx", {"to": USDC, "data": data})
    assert res.status is ResolveStatus.UNRESOLVABLE
    assert "selector no reconocido" in res.reason


def test_unknown_token_is_unresolvable() -> None:
    unknown = "0x" + "e" * 40
    data = _calldata("a9059cbb", ["address", "uint256"], [RECIPIENT, 1])
    res = _resolver().resolve("send_tx", {"to": unknown, "data": data})
    assert res.status is ResolveStatus.UNRESOLVABLE
    assert "token desconocido" in res.reason


def test_invalid_hex_is_unresolvable() -> None:
    res = _resolver().resolve("send_tx", {"to": USDC, "data": "no-es-hex"})
    assert res.status is ResolveStatus.UNRESOLVABLE


def test_financial_tool_without_data_or_value_is_unresolvable() -> None:
    res = _resolver().resolve("send_tx", {"to": RECIPIENT})
    assert res.status is ResolveStatus.UNRESOLVABLE


def test_calldata_present_but_no_target_is_unresolvable() -> None:
    data = _calldata("a9059cbb", ["address", "uint256"], [RECIPIENT, 1])
    res = _resolver().resolve("send_tx", {"data": data})  # falta 'to'
    assert res.status is ResolveStatus.UNRESOLVABLE
    assert "sin contrato destino" in res.reason


def test_calldata_shorter_than_selector_is_unresolvable() -> None:
    res = _resolver().resolve("send_tx", {"to": USDC, "data": "0xabcd"})  # 2 bytes < 4
    assert res.status is ResolveStatus.UNRESOLVABLE
    assert "demasiado corto" in res.reason


def test_known_selector_with_garbage_args_fails_closed() -> None:
    # selector transfer válido pero sin los bytes de argumentos → abi_decode falla
    res = _resolver().resolve("send_tx", {"to": USDC, "data": "0xa9059cbb"})
    assert res.status is ResolveStatus.UNRESOLVABLE
    assert "no se pudieron decodificar" in res.reason
