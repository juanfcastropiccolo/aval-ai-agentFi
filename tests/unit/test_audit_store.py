"""Tarea 13: AuditStore — append encadenado y detección de manipulación (AC-7)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from aval.core.audit import JsonlAuditStore
from aval.models import GENESIS_HASH, Verdict

TS = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _record(store: JsonlAuditStore, reason: str, verdict: Verdict = Verdict.ALLOW) -> None:
    store.record(
        timestamp=TS,
        agent_id="agent-1",
        mandate_id="m-1",
        action={"token": "USDC", "reason": reason},
        verdict=verdict,
        reason=reason,
    )


def test_append_chains_entries(tmp_path: Path) -> None:
    store = JsonlAuditStore(tmp_path / "audit.jsonl")
    _record(store, "a")
    _record(store, "b")
    _record(store, "c")

    entries = store.entries()
    assert len(entries) == 3
    assert entries[0].prev_hash == GENESIS_HASH
    assert entries[1].prev_hash == entries[0].entry_hash
    assert entries[2].prev_hash == entries[1].entry_hash
    assert store.verify() is True


def test_reopen_continues_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    _record(JsonlAuditStore(path), "first")
    store2 = JsonlAuditStore(path)  # reabre y continúa
    _record(store2, "second")
    assert store2.verify() is True
    assert store2.entries()[1].prev_hash == store2.entries()[0].entry_hash


def test_tampering_intermediate_entry_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    store = JsonlAuditStore(path)
    _record(store, "a")
    _record(store, "b")
    _record(store, "c")
    assert store.verify() is True

    # Alterar el contenido de la entrada intermedia, conservando su entry_hash.
    lines = path.read_text(encoding="utf-8").splitlines()
    mid = json.loads(lines[1])
    mid["reason"] = "MANIPULADA"
    lines[1] = json.dumps(mid)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert JsonlAuditStore(path).verify() is False


def test_hmac_protects_chain(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    store = JsonlAuditStore(path, key=b"clave-local")
    _record(store, "a")
    _record(store, "b")
    assert store.verify() is True
    # Verificar sin la clave (o con otra) falla.
    assert JsonlAuditStore(path).verify() is False
