"""Tarea 12: doble entrada de audit (autorización + ejecución) ligadas por safe_tx_hash."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

pytest.importorskip("safe_eth")
pytest.importorskip("fastapi")

from eth_account import Account  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aval.core.engine import Engine  # noqa: E402
from aval.core.resolver import EVMResolver, TokenInfo  # noqa: E402
from aval.execution.authorizer import Authorizer  # noqa: E402
from aval.execution.cosigner_client import CosignerClient  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL  # noqa: E402
from aval.execution.service import create_app  # noqa: E402
from aval.execution.signer import RawKeySigner  # noqa: E402
from aval.execution.transfer_executor import SafeTransferExecutor, TokenSpec  # noqa: E402
from aval.models import Mandate, Verdict  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit  # noqa: E402

CHAIN = 11155111
SAFE = "0x" + "11" * 20
USDC = "0x" + "aa" * 20
ALICE = "0x" + "33" * 20


def test_authorization_and_execution_entries_are_linked() -> None:
    resolver = EVMResolver.from_tool_names(
        {SAFE_TX_TOOL}, tokens={USDC.lower(): TokenInfo("USDC", 6)}
    )
    engine = Engine(resolver)  # InMemoryAuditStore por defecto
    authorizer = Authorizer(engine, RawKeySigner(Account.create().key.hex()))
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
    cosigner = CosignerClient(client=TestClient(app))

    chain = MagicMock()
    chain.get_nonce.return_value = 0
    chain.exec_transaction.return_value = "0x" + "ab" * 32

    ex = SafeTransferExecutor(
        safe_address=SAFE,
        chain_id=CHAIN,
        agent_private_key=Account.create().key.hex(),
        chain=chain,
        cosigner=cosigner,
        tokens={"USDC": TokenSpec(USDC, 6)},
    )
    out = ex.transfer(ALICE, 1000, "USDC")
    assert out["executed"] is True

    entries = engine.audit.entries()
    assert len(entries) == 2  # autorización + ejecución
    auth_entry, exec_entry = entries
    assert auth_entry.verdict is Verdict.ALLOW and auth_entry.tx_hash is None
    assert exec_entry.tx_hash == "0x" + "ab" * 32
    # ligadas por el safe_tx_hash
    assert exec_entry.action["safe_tx_hash"] == out["safe_tx_hash"]
    # cadena de hash íntegra tras las dos entradas
    assert engine.audit.verify() is True
