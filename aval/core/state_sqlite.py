"""`StateStore` persistente sobre SQLite (archivo local, sin servidor).

Misma semántica que `InMemoryStateStore`, pero los acumulados sobreviven a un
reinicio del proceso (necesario cuando el co-signer es un servicio de larga vida).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from aval.core.state import Period, StateStore, bucket_key
from aval.models.action import ProposedAction


class SqliteStateStore(StateStore):
    """Persiste gasto y conteo de acciones por agente y ventana en SQLite."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        # check_same_thread=False: el co-signer evalúa en el thread del servicio web,
        # distinto del que creó la conexión. sqlite serializa el acceso por conexión.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS spend (
                   agent_id TEXT, token TEXT, period TEXT, bucket TEXT,
                   amount TEXT NOT NULL,
                   PRIMARY KEY (agent_id, token, period, bucket))"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS action_count (
                   agent_id TEXT, period TEXT, bucket TEXT,
                   n INTEGER NOT NULL,
                   PRIMARY KEY (agent_id, period, bucket))"""
        )
        self._conn.commit()

    def get_spend(self, agent_id: str, token: str, period: Period, now: datetime) -> Decimal:
        row = self._conn.execute(
            "SELECT amount FROM spend WHERE agent_id=? AND token=? AND period=? AND bucket=?",
            (agent_id, token, period.value, bucket_key(period, now)),
        ).fetchone()
        return Decimal(row[0]) if row else Decimal(0)

    def get_action_count(self, agent_id: str, period: Period, now: datetime) -> int:
        row = self._conn.execute(
            "SELECT n FROM action_count WHERE agent_id=? AND period=? AND bucket=?",
            (agent_id, period.value, bucket_key(period, now)),
        ).fetchone()
        return int(row[0]) if row else 0

    def commit(self, agent_id: str, action: ProposedAction, now: datetime) -> None:
        for period in Period:
            bucket = bucket_key(period, now)
            self._conn.execute(
                """INSERT INTO action_count (agent_id, period, bucket, n)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT(agent_id, period, bucket)
                   DO UPDATE SET n = n + 1""",
                (agent_id, period.value, bucket),
            )
            if action.token is not None and action.amount is not None:
                prior = self.get_spend(agent_id, action.token, period, now)
                self._conn.execute(
                    """INSERT INTO spend (agent_id, token, period, bucket, amount)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(agent_id, token, period, bucket)
                       DO UPDATE SET amount = excluded.amount""",
                    (agent_id, action.token, period.value, bucket, str(prior + action.amount)),
                )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
