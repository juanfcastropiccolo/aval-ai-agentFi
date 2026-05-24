"""Entrypoint de un nodo co-autorizador: arma el servicio desde config y backend de clave.

Un nodo aval es un servicio independiente. La clave se elige por entorno
(``AVAL_SIGNER`` = ``kms`` | ``keystore`` | ``raw``); el mandato se provee
programáticamente (es un objeto de dominio). Patrón de despliegue::

    # mi_nodo.py
    from aval.execution.node import build_node_app, signer_from_env
    from aval.models import Mandate
    app = build_node_app(signer_from_env(), {SAFE: Mandate(...)}, auth_token="...")
    # uvicorn mi_nodo:app
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI

from aval.core.audit import AuditStore, InMemoryAuditStore, JsonlAuditStore
from aval.core.engine import Engine
from aval.core.resolver import EVMResolver, TokenInfo
from aval.core.state import InMemoryStateStore, StateStore
from aval.core.state_sqlite import SqliteStateStore
from aval.execution.authorizer import Authorizer
from aval.execution.decode import SAFE_TX_TOOL
from aval.execution.service import create_app
from aval.execution.signer import KmsSigner, LocalKeystoreSigner, RawKeySigner, Signer
from aval.models import Mandate


def signer_from_env(env: Mapping[str, str] | None = None) -> Signer:
    """Construye el ``Signer`` del nodo según ``AVAL_SIGNER`` (kms | keystore | raw)."""
    env = env if env is not None else os.environ
    kind = env.get("AVAL_SIGNER", "keystore").lower()
    if kind == "kms":
        import boto3

        return KmsSigner(env["AVAL_KMS_KEY_ID"], boto3.client("kms"))
    if kind == "keystore":
        keystore = json.loads(Path(env["AVAL_KEYSTORE_PATH"]).read_text())
        return LocalKeystoreSigner(keystore, env["AVAL_KEYSTORE_PASSPHRASE"])
    if kind == "raw":  # solo dev
        return RawKeySigner(env["AVAL_PRIVATE_KEY"])
    raise ValueError(f"AVAL_SIGNER desconocido: {kind!r} (usá kms | keystore | raw)")


def build_node_app(
    signer: Signer,
    mandates: dict[str, Mandate],
    *,
    auth_token: str | None = None,
    tokens: dict[str, TokenInfo] | None = None,
    default_chain: str = "ethereum",
    audit_path: str | None = None,
    state_path: str | None = None,
) -> FastAPI:
    """Arma la app FastAPI de un nodo co-autorizador con su ``Signer`` y mandatos."""
    resolver = EVMResolver.from_tool_names(
        {SAFE_TX_TOOL}, tokens=tokens or {}, default_chain=default_chain
    )
    audit: AuditStore = JsonlAuditStore(audit_path) if audit_path else InMemoryAuditStore()
    state: StateStore = SqliteStateStore(state_path) if state_path else InMemoryStateStore()
    authorizer = Authorizer(Engine(resolver, audit_store=audit, state_store=state), signer)
    return create_app(authorizer, mandates, auth_token=auth_token)
