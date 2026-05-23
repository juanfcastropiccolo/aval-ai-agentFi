"""Agente ADK (Gemini) que transfiere en Sepolia, gateado por aval.

Le hablás en lenguaje natural ("transferí 0.005 ETH a 0x…") y el agente usa el tool
`transfer_funds`. El tool arma la SafeTx, pide la co-firma al servicio de aval y solo
ejecuta si aval autoriza. Sin la co-firma de aval, ninguna transferencia se ejecuta.

Requiere en `.env`: SEPOLIA_RPC_URL, SAFE_ADDRESS, AGENT_PRIVATE_KEY, AVAL_PRIVATE_KEY,
GEMINI_API_KEY. Ejecutá: python -m examples.adk_sepolia_agent
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from eth_account import Account
from web3 import Web3


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in Path(".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.split("#")[0].strip()
    return env


def main() -> None:
    env = _load_env()
    # ADK/genai leen la API key del entorno.
    os.environ["GOOGLE_API_KEY"] = env["GEMINI_API_KEY"]
    os.environ["GEMINI_API_KEY"] = env["GEMINI_API_KEY"]
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

    from fastapi.testclient import TestClient
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner

    from aval.adapters.adk import make_transfer_tool
    from aval.core.engine import Engine
    from aval.core.resolver import EVMResolver
    from aval.execution.authorizer import Authorizer
    from aval.execution.chain import SafeChain
    from aval.execution.cosigner_client import CosignerClient
    from aval.execution.decode import SAFE_TX_TOOL
    from aval.execution.service import create_app
    from aval.execution.transfer_executor import SafeTransferExecutor, TokenSpec
    from aval.models import Mandate
    from aval.policies import AllowedMethods, RecipientAllowlist, SpendLimit

    w3 = Web3(Web3.HTTPProvider(env["SEPOLIA_RPC_URL"]))
    safe = Web3.to_checksum_address(env["SAFE_ADDRESS"])
    chain_id = w3.eth.chain_id

    alice = Account.create()  # destino permitido por el mandato
    mallory = Account.create()  # destino NO permitido

    mandate = Mandate(
        agent_id="trading-agent",
        granted_by="cfo@startup.eth",
        policies=[
            SpendLimit(token="ETH", per_tx=Decimal("0.1")),
            RecipientAllowlist(recipients={alice.address.lower()}),
            AllowedMethods(methods={"transfer_native"}),
        ],
        token_decimals={"ETH": 18},
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )

    # Co-signer de aval como servicio (acá in-process; en prod, proceso separado).
    resolver = EVMResolver.from_tool_names({SAFE_TX_TOOL}, tokens={}, default_chain=str(chain_id))
    authorizer = Authorizer(Engine(resolver), env["AVAL_PRIVATE_KEY"])
    cosigner = CosignerClient(client=TestClient(create_app(authorizer, {safe: mandate})))

    executor = SafeTransferExecutor(
        safe_address=safe,
        chain_id=chain_id,
        agent_private_key=env["AGENT_PRIVATE_KEY"],
        chain=SafeChain(w3, safe),
        cosigner=cosigner,
        tokens={"ETH": TokenSpec(None, 18)},
    )

    agent = LlmAgent(
        name="treasury_agent",
        model="gemini-2.5-flash",
        instruction=(
            "Sos un asistente de tesorería. Cuando el usuario pida transferir fondos, "
            "usá la herramienta transfer_funds(recipient, amount, token). Después de usarla, "
            "informá claramente al usuario si la transferencia se ejecutó (con el tx_hash) o "
            "si fue bloqueada, citando la razón. No inventes resultados."
        ),
        tools=[make_transfer_tool(executor)],
    )
    runner = InMemoryRunner(agent)

    def ask(prompt: str) -> None:
        print("\n" + "=" * 68)
        print(f"👤 Usuario: {prompt}")
        events = asyncio.run(runner.run_debug(prompt, quiet=True))
        for ev in events:
            if ev.content and ev.content.parts:
                for part in ev.content.parts:
                    if getattr(part, "text", None):
                        print(f"🤖 Agente: {part.text.strip()}")

    ask(f"Transferí 0.005 ETH a la dirección {alice.address}")
    ask(f"Ahora transferí 0.005 ETH a {mallory.address}")


if __name__ == "__main__":
    main()
