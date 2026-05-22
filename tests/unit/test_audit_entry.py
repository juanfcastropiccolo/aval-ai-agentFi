"""Tarea 6: AuditEntry — determinismo del hash y sensibilidad a cualquier cambio."""

from datetime import UTC, datetime

from aval.models import GENESIS_HASH, AuditEntry, Verdict

TS = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _entry(**overrides: object) -> AuditEntry:
    fields: dict[str, object] = {
        "prev_hash": GENESIS_HASH,
        "timestamp": TS,
        "agent_id": "agent-1",
        "mandate_id": "m-1",
        "action": {"token": "USDC", "amount": "4000"},
        "verdict": Verdict.ALLOW,
        "reason": "ok",
    }
    fields.update(overrides)
    return AuditEntry.create(**fields)  # type: ignore[arg-type]


def test_hash_is_deterministic() -> None:
    assert _entry().entry_hash == _entry().entry_hash


def test_hash_is_nonempty_and_self_consistent() -> None:
    entry = _entry()
    assert len(entry.entry_hash) == 64
    assert entry.verify() is True


def test_changing_any_field_changes_hash() -> None:
    base = _entry()
    assert _entry(reason="otra").entry_hash != base.entry_hash
    assert _entry(verdict=Verdict.DENY).entry_hash != base.entry_hash
    assert _entry(action={"token": "USDC", "amount": "4001"}).entry_hash != base.entry_hash
    assert _entry(prev_hash="f" * 64).entry_hash != base.entry_hash


def test_tampering_breaks_verify() -> None:
    entry = _entry()
    tampered = entry.model_copy(update={"reason": "manipulada"})
    assert tampered.verify() is False


def test_hmac_key_changes_digest() -> None:
    plain = _entry()
    keyed = _entry(key=b"secreto")
    assert keyed.entry_hash != plain.entry_hash
    assert keyed.verify(key=b"secreto") is True
    assert keyed.verify() is False
