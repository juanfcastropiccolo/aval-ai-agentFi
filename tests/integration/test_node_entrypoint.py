"""Tarea 10: entrypoint del nodo — signer desde env y app levantable que responde /health."""

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("safe_eth")
pytest.importorskip("fastapi")

from eth_account import Account  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aval.execution.node import build_node_app, signer_from_env  # noqa: E402
from aval.execution.signer import LocalKeystoreSigner  # noqa: E402
from aval.models import Mandate  # noqa: E402
from aval.policies import AllowedMethods  # noqa: E402

SAFE = "0x" + "11" * 20


def test_signer_from_env_raw() -> None:
    acct = Account.create()
    signer = signer_from_env({"AVAL_SIGNER": "raw", "AVAL_PRIVATE_KEY": acct.key.hex()})
    assert signer.address.lower() == acct.address.lower()


def test_signer_from_env_keystore(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    acct = Account.create()
    ks_path = tmp_path / "ks.json"
    ks_path.write_text(json.dumps(LocalKeystoreSigner.create_keystore(acct.key.hex(), "pw")))
    signer = signer_from_env(
        {
            "AVAL_SIGNER": "keystore",
            "AVAL_KEYSTORE_PATH": str(ks_path),
            "AVAL_KEYSTORE_PASSPHRASE": "pw",
        }
    )
    assert signer.address.lower() == acct.address.lower()


def test_unknown_signer_kind_rejected() -> None:
    with pytest.raises(ValueError):
        signer_from_env({"AVAL_SIGNER": "magic"})


def test_build_node_app_serves_health() -> None:
    acct = Account.create()
    signer = signer_from_env({"AVAL_SIGNER": "raw", "AVAL_PRIVATE_KEY": acct.key.hex()})
    mandate = Mandate(
        agent_id="a",
        granted_by="dev",
        policies=[AllowedMethods(methods={"transfer"})],
        token_decimals={},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    app = build_node_app(signer, {SAFE: mandate}, auth_token="tok")
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["aval_address"].lower() == acct.address.lower()
