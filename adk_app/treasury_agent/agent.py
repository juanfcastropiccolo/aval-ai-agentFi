"""Agente de tesorería para `adk web`, gateado por aval sobre un Safe 2-de-2 en Sepolia.

`adk web` descubre este módulo y sirve un chat en el navegador. Pedile en lenguaje
natural "transferí 0.005 ETH a 0x…": el tool arma la SafeTx, aval co-firma solo si
respeta el mandato, y recién entonces se ejecuta en Sepolia.

Config en `.env` (raíz del repo): SEPOLIA_RPC_URL, SAFE_ADDRESS, AGENT_PRIVATE_KEY,
AVAL_PRIVATE_KEY, GEMINI_API_KEY, ALLOWED_RECIPIENT.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# La raíz del repo (donde vive el paquete `aval` y el `.env`). `adk web` importa
# este módulo sin el repo en sys.path, así que lo agregamos explícitamente antes
# de importar `aval` (no dependemos de cómo quedó instalado el editable).
_REPO_ROOT: Path | None = None
for _parent in Path(__file__).resolve().parents:
    if (_parent / "aval").is_dir() and (_parent / "pyproject.toml").exists():
        _REPO_ROOT = _parent
        break
if _REPO_ROOT is None:
    raise FileNotFoundError("No se encontró la raíz del repo (carpeta con aval/ y pyproject.toml)")
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from google.adk.agents import LlmAgent  # noqa: E402
from web3 import Web3  # noqa: E402

from aval.adapters.adk import make_transfer_tool  # noqa: E402
from aval.core.engine import Engine  # noqa: E402
from aval.core.resolver import EVMResolver  # noqa: E402
from aval.execution.authorizer import Authorizer  # noqa: E402
from aval.execution.chain import SafeChain  # noqa: E402
from aval.execution.cosigner_client import CosignerClient  # noqa: E402
from aval.execution.decode import SAFE_TX_TOOL  # noqa: E402
from aval.execution.service import create_app  # noqa: E402
from aval.execution.transfer_executor import SafeTransferExecutor, TokenSpec  # noqa: E402
from aval.models import Mandate  # noqa: E402
from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit  # noqa: E402


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    candidate = _REPO_ROOT / ".env"  # type: ignore[operator]
    if not candidate.exists():
        raise FileNotFoundError("No se encontró .env en la raíz del repo")
    for line in candidate.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.split("#")[0].strip()
    return env


_env = _load_env()
os.environ["GOOGLE_API_KEY"] = _env["GEMINI_API_KEY"]
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

_w3 = Web3(Web3.HTTPProvider(_env["SEPOLIA_RPC_URL"]))
_safe = Web3.to_checksum_address(_env["SAFE_ADDRESS"])
_chain_id = _w3.eth.chain_id
ALLOWED_RECIPIENT = Web3.to_checksum_address(_env["ALLOWED_RECIPIENT"])

# Mandato: hasta 0.1 ETH/tx, solo al destino permitido, solo transferencias nativas.
_mandate = Mandate(
    agent_id="treasury-agent",
    granted_by="cfo@startup.eth",
    policies=[
        SpendLimit(token="ETH", per_tx=Decimal("0.1"), per_day=Decimal("0.5")),
        RecipientAllowlist(recipients={ALLOWED_RECIPIENT.lower()}),
        AllowedMethods(methods={"transfer_native"}),
    ],
    token_decimals={"ETH": 18},
    expires_at=datetime.now(UTC) + timedelta(days=30),
)

# Co-signer de aval. En este demo corre in-process; en producción es un servicio
# separado (su create_app ya está listo para uvicorn) para aislar la llave de aval.
_resolver = EVMResolver.from_tool_names({SAFE_TX_TOOL}, tokens={}, default_chain=str(_chain_id))
_authorizer = Authorizer(Engine(_resolver), _env["AVAL_PRIVATE_KEY"])
_cosigner = CosignerClient(client=TestClient(create_app(_authorizer, {_safe: _mandate})))

_executor = SafeTransferExecutor(
    safe_address=_safe,
    chain_id=_chain_id,
    agent_private_key=_env["AGENT_PRIVATE_KEY"],
    chain=SafeChain(_w3, _safe),
    cosigner=_cosigner,
    tokens={"ETH": TokenSpec(None, 18)},
)

root_agent = LlmAgent(
    name="treasury_agent",
    model="gemini-2.5-flash",
    instruction=(
        "Sos un asistente de tesorería que mueve fondos desde un Safe en Sepolia, "
        "protegido por aval. Cuando el usuario pida transferir, usá la herramienta "
        "transfer_funds(recipient, amount, token). El token por defecto es 'ETH'. "
        "Después de usar la herramienta, informá si la transferencia se ejecutó (mostrá "
        "el tx_hash y un link a https://sepolia.etherscan.io/tx/<hash>) o si aval la "
        "bloqueó, citando la razón exacta. No inventes resultados ni hashes. "
        f"El único destino autorizado por el mandato es {ALLOWED_RECIPIENT}."
    ),
    tools=[make_transfer_tool(_executor)],
)
