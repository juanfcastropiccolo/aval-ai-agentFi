"""Audit trail append-only encadenado por hash."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from aval.models import GENESIS_HASH, AuditEntry, Verdict


class AuditStore(ABC):
    """Persiste veredictos en un trail encadenado y permite verificar su integridad."""

    @abstractmethod
    def record(
        self,
        *,
        timestamp: datetime,
        agent_id: str,
        mandate_id: str,
        action: dict[str, Any],
        verdict: Verdict,
        reason: str,
        failed_policy: str | None = None,
        tx_hash: str | None = None,
    ) -> AuditEntry:
        """Agrega una entrada encadenada al ``prev_hash`` actual y la devuelve."""

    @abstractmethod
    def entries(self) -> list[AuditEntry]:
        """Devuelve todas las entradas en orden."""

    def verify(self) -> bool:
        """``True`` si la cadena es íntegra: cada hash es válido y enlaza al anterior."""
        prev = GENESIS_HASH
        for entry in self.entries():
            if entry.prev_hash != prev:
                return False
            if not entry.verify(self._key):
                return False
            prev = entry.entry_hash
        return True

    @property
    def _key(self) -> bytes | None:
        return None


class JsonlAuditStore(AuditStore):
    """Audit trail en un archivo JSONL local, con hash chain SHA-256 (HMAC opcional).

    Cada entrada es una línea JSON. ``record`` falla con excepción si no puede
    escribir — el Engine trata eso como fail-closed (deniega la acción).
    """

    def __init__(self, path: str | Path, key: bytes | None = None) -> None:
        self._path = Path(path)
        self._hmac_key = key
        self._last_hash = self._load_last_hash()

    @property
    def _key(self) -> bytes | None:
        return self._hmac_key

    def _load_last_hash(self) -> str:
        if not self._path.exists():
            return GENESIS_HASH
        last = GENESIS_HASH
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last = AuditEntry.model_validate_json(line).entry_hash
        return last

    def record(
        self,
        *,
        timestamp: datetime,
        agent_id: str,
        mandate_id: str,
        action: dict[str, Any],
        verdict: Verdict,
        reason: str,
        failed_policy: str | None = None,
        tx_hash: str | None = None,
    ) -> AuditEntry:
        entry = AuditEntry.create(
            prev_hash=self._last_hash,
            timestamp=timestamp,
            agent_id=agent_id,
            mandate_id=mandate_id,
            action=action,
            verdict=verdict,
            reason=reason,
            failed_policy=failed_policy,
            tx_hash=tx_hash,
            key=self._hmac_key,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json() + "\n")
        self._last_hash = entry.entry_hash
        return entry

    def entries(self) -> list[AuditEntry]:
        if not self._path.exists():
            return []
        out: list[AuditEntry] = []
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(AuditEntry.model_validate_json(line))
        return out


class InMemoryAuditStore(AuditStore):
    """Audit trail en memoria — útil para tests."""

    def __init__(self, key: bytes | None = None) -> None:
        self._hmac_key = key
        self._entries: list[AuditEntry] = []
        self._last_hash = GENESIS_HASH

    @property
    def _key(self) -> bytes | None:
        return self._hmac_key

    def record(
        self,
        *,
        timestamp: datetime,
        agent_id: str,
        mandate_id: str,
        action: dict[str, Any],
        verdict: Verdict,
        reason: str,
        failed_policy: str | None = None,
        tx_hash: str | None = None,
    ) -> AuditEntry:
        entry = AuditEntry.create(
            prev_hash=self._last_hash,
            timestamp=timestamp,
            agent_id=agent_id,
            mandate_id=mandate_id,
            action=action,
            verdict=verdict,
            reason=reason,
            failed_policy=failed_policy,
            tx_hash=tx_hash,
            key=self._hmac_key,
        )
        self._entries.append(entry)
        self._last_hash = entry.entry_hash
        return entry

    def entries(self) -> list[AuditEntry]:
        return list(self._entries)


def load_entries(path: str | Path) -> list[AuditEntry]:
    """Carga entradas de un JSONL para inspección/verificación externa."""
    return JsonlAuditStore(path).entries()
