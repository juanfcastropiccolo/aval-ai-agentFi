# aval

**Capa de confianza framework-agnóstica para agentes de IA que manejan dinero.**

Un agente que puede mover dinero no debería depender de instrucciones en lenguaje
natural ("nunca transfieras más de X") para no exceder su autoridad: una inyección
de prompt, una herramienta mal interpretada o un simple error pueden costar capital
real. `aval` pone una **barrera técnica fuera del razonamiento del modelo**: cada
acción que mueve dinero se evalúa contra un **mandato** explícito *antes* de
ejecutarse. Si lo respeta, procede; si lo viola, se bloquea con una razón legible;
si es sensible, se escala a una persona. Todo queda en un **audit trail
inalterable**.

aval **no** es una wallet ni un signer, no mueve dinero y no intenta detectar
prompts maliciosos: opera en la capa de *acción*, que es lo único confiable.

## Instalación

```bash
pip install aval                 # core
pip install "aval[adk]"          # + adaptador Google ADK
pip install "aval[langchain]"    # + adaptador LangChain / LangGraph
```

Requiere Python 3.11+.

## Quickstart

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from aval import (
    AllowedMethods, Engine, EVMResolver, Mandate,
    RecipientAllowlist, SpendLimit, TokenInfo,
)

USDC = "0xA0b8...".lower()
ALICE = "0xC0ff...".lower()

# 1. El resolver sabe qué tools mueven dinero y qué tokens conoce (declarativo).
resolver = EVMResolver.from_tool_names(
    {"send_tx"},                       # tools financieros del agente
    tokens={USDC: TokenInfo("USDC", 6)},
)
engine = Engine(resolver)              # audit en memoria por defecto

# 2. El dev declara el mandato una sola vez.
mandate = Mandate(
    agent_id="trading-agent",
    granted_by="dev@example.com",
    chains=["ethereum"],
    policies=[
        SpendLimit(token="USDC", per_tx=Decimal("5000"), per_day=Decimal("20000")),
        RecipientAllowlist(recipients={ALICE}),
        AllowedMethods(methods={"transfer"}),
    ],
    token_decimals={"USDC": 6},
    expires_at=datetime.now(UTC) + timedelta(days=30),
)

# 3. Antes de ejecutar cualquier tool call, se evalúa.
decision = engine.evaluate("send_tx", {"to": USDC, "data": "0x..."}, mandate)
if decision.is_allow:
    ...  # ejecutar el tool
else:
    ...  # bloquear; decision.reason explica por qué
```

## Integración con frameworks (sin reescribir el agente)

**Google ADK** — engancha el `before_tool_callback`:

```python
from aval.adapters.adk import make_before_tool_callback

agent = LlmAgent(
    ...,
    before_tool_callback=make_before_tool_callback(engine, mandate),
)
# DENY ⇒ el tool no se ejecuta y la razón vuelve al modelo.
```

**LangChain / LangGraph** — agrega el middleware:

```python
from aval.adapters.langchain import AvalMiddleware

agent = create_agent(model, tools=[...], middleware=[AvalMiddleware(engine, mandate)])
```

Ver `examples/example_agent.py` para una demo completa de los 4 escenarios
(allow / deny por límite / deny por destino / escalate):

```bash
python -m examples.example_agent
```

## Políticas disponibles

| Política | Gobierna |
|----------|----------|
| `SpendLimit(token, per_tx, per_day)` | monto por transacción y acumulado diario |
| `RecipientAllowlist(recipients)` | destinatarios de fondos permitidos |
| `AllowedTargets(contracts)` | contratos/destinos invocables |
| `AllowedTokens(tokens)` | activos manejables |
| `AllowedMethods(methods)` | tipos de acción (`transfer`, `approve`, …) |
| `TimeWindow(start, end, tz)` | franja horaria permitida |
| `RateLimit(max_actions, per)` | cantidad de acciones por período |

La evaluación es **default-deny por conjunción**: una acción se autoriza solo si
*todas* las políticas aplicables pasan y *al menos una* la autoriza afirmativamente.

## Audit trail

Cada veredicto se registra en un trail append-only encadenado por hash SHA-256
(con HMAC opcional). Alterar cualquier entrada rompe la cadena:

```python
from aval import JsonlAuditStore

engine = Engine(resolver, audit_store=JsonlAuditStore("trail.aval.jsonl"))
...
assert engine.audit.verify()   # False si alguien manipuló el archivo
```

## Garantías de diseño (fail-closed)

aval **deniega** —nunca autoriza a ciegas— ante cualquiera de estos casos:

- una acción financiera cuyo calldata o token no puede resolverse;
- un mandato expirado o revocado;
- un fallo al escribir el audit trail (registrar es parte del camino crítico);
- cualquier error inesperado durante la evaluación.

Las acciones que **no** mueven dinero hacen pass-through limpio, sin interferencia.

## Limitaciones del MVP

- **Estado en memoria.** `InMemoryStateStore` acumula gasto y conteo de acciones
  por proceso: **se resetea si el proceso reinicia**. La interfaz `StateStore` está
  lista para una implementación persistente (Redis/DB).
- **Sin RPC ni red.** Los decimales de tokens se declaran en el resolver/mandato;
  no hay lookups on-chain. Tokens o selectores desconocidos → fail-closed.
- **Solo EVM.** No soporta fiat ni cadenas no-EVM.
- **Sin anclaje on-chain.** El audit es tamper-evident localmente; el anclaje a EAS
  y la verificabilidad por terceros son hitos posteriores.
- **Enforcement en el punto de integración.** aval protege donde envuelve al agente;
  un proxy de firma independiente es fase posterior.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest                       # tests
ruff check . && ruff format .
mypy aval/core aval/policies aval/models
```
