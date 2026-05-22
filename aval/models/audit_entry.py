"""Entrada del audit trail, encadenada por hash (tamper-evident)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from aval.models.verdict import Verdict

GENESIS_HASH = "0" * 64
"""``prev_hash`` de la primera entrada de una cadena."""


def _canonical_json(data: dict[str, Any]) -> str:
    """JSON determinístico: claves ordenadas, sin espacios.

    Es la base del hash: dos serializaciones del mismo contenido deben dar
    exactamente el mismo string, sin importar el orden de inserción.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class AuditEntry(BaseModel):
    """Un veredicto registrado, ligado al anterior por ``prev_hash``.

    ``entry_hash = H(canonical_json(todos los campos excepto entry_hash))`` donde
    ``H`` es SHA-256, o HMAC-SHA256 si el dev provee una clave local. Como
    ``prev_hash`` está entre los campos hasheados, alterar cualquier entrada
    rompe la cadena de todas las posteriores.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    agent_id: str
    mandate_id: str
    action: dict[str, Any]
    verdict: Verdict
    failed_policy: str | None
    reason: str
    tx_hash: str | None
    prev_hash: str
    entry_hash: str = ""

    def _digest(self, key: bytes | None) -> str:
        payload = self.model_dump(mode="json", exclude={"entry_hash"})
        message = _canonical_json(payload).encode("utf-8")
        if key is not None:
            return hmac.new(key, message, hashlib.sha256).hexdigest()
        return hashlib.sha256(message).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        prev_hash: str,
        timestamp: datetime,
        agent_id: str,
        mandate_id: str,
        action: dict[str, Any],
        verdict: Verdict,
        reason: str,
        failed_policy: str | None = None,
        tx_hash: str | None = None,
        key: bytes | None = None,
    ) -> AuditEntry:
        """Construye una entrada y computa su ``entry_hash`` encadenado."""
        draft = cls(
            timestamp=timestamp,
            agent_id=agent_id,
            mandate_id=mandate_id,
            action=action,
            verdict=verdict,
            failed_policy=failed_policy,
            reason=reason,
            tx_hash=tx_hash,
            prev_hash=prev_hash,
        )
        return draft.model_copy(update={"entry_hash": draft._digest(key)})

    def verify(self, key: bytes | None = None) -> bool:
        """``True`` si ``entry_hash`` corresponde al contenido actual."""
        return hmac.compare_digest(self.entry_hash, self._digest(key))
