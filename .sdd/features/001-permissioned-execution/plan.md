# Plan: Ejecución permisionada de movimientos de dinero

Feature ID: 001
Status: planned
Last updated: 2026-05-22

## Chosen stack

- **Lenguaje:** Python 3.11+ (match types, `StrEnum`, mejor typing).
- **Modelos / validación:** Pydantic v2 — `Mandate`, `ProposedAction`, `Decision`, `PolicyResult`, `AuditEntry`. Da validación declarativa y serialización JSON gratis (clave para el esquema compatible-AP2 y para el audit trail).
- **Decodificación de calldata EVM:** `eth-abi` + `eth-utils` (function selectors, decode de args ERC-20 y de routers conocidos). `web3.py` **no** se usa como dependencia runtime obligatoria del core para no arrastrar un proveedor RPC; solo `eth-abi`/`eth-utils` que son livianas y puras.
- **Normalización de montos:** decimales de token vía un registro estático de tokens conocidos del MVP (USDC=6, USDT=6, WETH=18) declarado por el dev en el mandato; sin llamadas RPC.
- **Audit trail:** archivo JSONL local con **hash chain SHA-256** (cada entrada incluye `prev_hash` y `entry_hash`); firma opcional HMAC con clave local del dev. Backend detrás de una interfaz `AuditStore` (impl. `JsonlAuditStore` en el MVP).
- **StateStore:** interfaz `StateStore` con impl. `InMemoryStateStore` (dict) para acumulados de gasto y conteo de acciones por período.
- **Adaptadores:** `google-adk` (vía `before_tool_callback` / Plugin) y `langchain`/`langgraph` (vía middleware `wrap_tool_call`), ambos como **extras opcionales** (`pip install aval[adk]`, `aval[langchain]`) — el core no depende de ningún framework.
- **Escalamiento humano default:** `ConsoleHumanReviewer` (prompt bloqueante por stdin), detrás de la interfaz `HumanReviewer`.
- **Tooling:** `ruff` (format + lint, línea 100), `mypy --strict` sobre `aval/core` y `aval/policies`, `pytest` + `pytest-cov`. Empaquetado con `pyproject.toml` (hatchling).

Alineado con la Constitution (Python 3.11+, in-process, sin DB, agnóstico con adaptadores ADK+LangChain). Sin divergencias que requieran entrada en el decision log.

## Architecture overview

El core es una pipeline síncrona de tres etapas sin conocimiento de framework: el **EVM Resolver** convierte una tool call cruda `(tool_name, args)` en una `ProposedAction` normalizada (o decide pass-through / fail-closed); el **Policy Engine** evalúa esa acción contra el `Mandate` activo aplicando cada `Policy` por conjunción y produce un `Decision`; el **Audit Trail** persiste el veredicto encadenado por hash antes de devolverlo. Los **adaptadores** son shims delgados que enganchan el hook nativo de cada framework, llaman a `Engine.evaluate(...)` y mapean los tres veredictos (ALLOW/DENY/ESCALATE) al idioma del framework. El estado con memoria (gasto por período, conteo de acciones) vive en un `StateStore` pluggable que el Policy Engine consulta y actualiza solo cuando una acción se autoriza.

```
adapter (adk | langchain)
   │  (tool_name, args, mandate, ctx)
   ▼
Engine.evaluate()
   ├─ 1. Resolver.resolve(tool_name, args) ─► ProposedAction | PASS_THROUGH | UNRESOLVABLE
   │        PASS_THROUGH  → Decision.allow (no es dinero)
   │        UNRESOLVABLE  → Decision.deny  (fail-closed)
   ├─ 2. PolicyEngine.evaluate(action, mandate, state)
   │        ∀ policy: policy.evaluate(action, state) → PolicyResult
   │        conjunción → Decision{ALLOW|DENY|ESCALATE, reason, failed_policy}
   │        si ESCALATE → HumanReviewer.review() → ALLOW|DENY
   │        si ALLOW   → state.commit(action)   (suma gasto / cuenta acción)
   ├─ 3. AuditStore.record(entry)  ─► entry_hash   (fail-closed si falla)
   ▼
Decision  ─► adapter mapea (ejecutar | bloquear con reason | pausa ya resuelta)
```

## Data model

Entidades (Pydantic v2), formas principales:

- **`Mandate`**: `agent_id: str`, `granted_by: str`, `chains: list[str]`, `policies: list[Policy]`, `token_decimals: dict[str,int]`, `expires_at: datetime`, `revocable: bool`, `revoked: bool = False`. Método `is_active(now) -> bool`.
- **`Policy`** (base abstracta) con `evaluate(action, state) -> PolicyResult`. Subclases: `SpendLimit(token, per_tx, per_day)`, `AllowedTargets(contracts: set[str])`, `AllowedTokens(tokens: set[str])`, `AllowedMethods(methods: set[str])`, `RecipientAllowlist(recipients: set[str])`, `TimeWindow(start, end, tz)`, `RateLimit(max_actions, per)`. Cada subclase declara qué dimensión de `ProposedAction` aplica; si la dimensión no aplica a la acción, devuelve `PolicyResult.not_applicable()`.
- **`ProposedAction`**: `rail: str = "evm"`, `chain: str`, `token: str | None`, `amount: Decimal | None` (normalizado por decimales), `recipient: str | None`, `target_contract: str | None`, `method: str | None`, `selector: str | None`, `raw: dict`. Construida por el Resolver.
- **`PolicyResult`**: `passed: bool`, `verdict: Verdict`, `reason: str`, `policy_name: str`. `Verdict ∈ {ALLOW, DENY, ESCALATE}`; `not_applicable` = passed con verdict ALLOW neutro.
- **`Decision`**: `verdict: Verdict`, `reason: str`, `failed_policy: str | None`, `action: ProposedAction | None`, `entry_hash: str | None`, `timestamp: datetime`. Helpers `is_allow/is_deny/is_escalate`.
- **`AuditEntry`**: `timestamp`, `agent_id`, `mandate_id`, `action: dict`, `verdict`, `failed_policy`, `reason`, `tx_hash: str | None`, `prev_hash: str`, `entry_hash: str`. `entry_hash = sha256(canonical_json(todo menos entry_hash) + prev_hash)`.
- **`StateStore`** (interfaz): `get_spend(agent_id, token, window) -> Decimal`, `get_action_count(agent_id, window) -> int`, `commit(action)`. Impl. in-memory con buckets por (agent_id, ventana).

Selector → método: tabla estática de selectores conocidos (`a9059cbb`→`transfer`, `095ea7b3`→`approve`, `23b872dd`→`transferFrom`, selectores de swap de routers DEX comunes). Selector desconocido hacia un tool financiero ⇒ UNRESOLVABLE ⇒ fail-closed.

## External dependencies

- **`eth-abi`, `eth-utils`** (runtime, core): decode de calldata y selectores. Puras, sin red. Riesgo bajo.
- **`pydantic` v2** (runtime, core): modelos/validación.
- **`google-adk`** (extra `[adk]`): hook `before_tool_callback` / Plugin. API de callbacks estable en la línea actual; aislada en el adaptador.
- **`langchain` / `langgraph`** (extra `[langchain]`): middleware `wrap_tool_call` (estable desde 1.0). Aislada en el adaptador.
- **dev:** `pytest`, `pytest-cov`, `ruff`, `mypy`, `hatchling`.
- **Sin dependencias de red, RPC, ni servicios externos en el MVP.** Anclaje EAS y proveedores de data on-chain (Dune/The Graph) son hitos posteriores (niveles 2/3 de verificabilidad), con sus interfaces (`AuditStore`, un futuro `AnchorBackend`) ya previstas.

## Trade-offs considered

- **Pydantic v2 vs dataclasses puros:** elegido Pydantic por validación declarativa y serialización JSON canónica (necesaria para hash chain y esquema AP2). Dataclasses rechazado: tendríamos que escribir validación y serialización a mano, justo en los modelos de dominio donde un error cuesta dinero.
- **`eth-abi` solo vs `web3.py` completo:** elegido `eth-abi`/`eth-utils`. `web3.py` rechazado como dep runtime del core porque arrastra proveedores RPC y peso que no necesitamos (no hacemos llamadas a la cadena en el MVP); se podrá sumar en un extra si un futuro resolver necesita ABIs on-chain.
- **Decimales por registro estático vs lookup RPC on-chain:** elegido registro estático declarado en el mandato. RPC rechazado para el MVP: agrega latencia, una dependencia de red y un punto de fallo en el camino crítico de cada acción; con fail-closed, un RPC caído bloquearía todo. El registro estático cubre los tokens del MVP; ampliable después.
- **Audit: hash chain en JSONL vs Merkle tree vs base de datos append-only:** elegido hash chain en JSONL. Merkle tree rechazado por ahora (su valor real aparece en el nivel 2, batching para anclaje EAS — se sumará entonces). DB append-only rechazada por la Constitution (sin DB en MVP) y por simplicidad. El hash chain ya satisface "alteración detectable" (AC-7).
- **Evaluación síncrona vs asíncrona:** core síncrono; los adaptardores async (ADK/LangChain pueden invocar tools async) envuelven la llamada síncrona. Core async rechazado: la lógica de decisión es CPU-bound y sin I/O en el MVP; sync es más simple de testear y razonar. Si un backend futuro (EAS) necesita I/O, se aísla en el AuditStore.
- **Registro declarativo de tools financieros vs autodetección:** elegido declarativo (el dev marca qué tools mueven dinero y cómo extraer params). Autodetección rechazada: adivinar qué tool mueve dinero es frágil y violaría fail-closed (un falso negativo deja pasar dinero sin control). Declarativo es explícito y auditable.
- **Firma del audit: hash chain solo vs HMAC vs firma asimétrica:** MVP usa hash chain (tamper-evident) con HMAC opcional. Firma asimétrica rechazada por ahora: su valor (no-repudio verificable por terceros) pertenece al nivel 2/allocator; sumarla ahora es complejidad sin consumidor.

## Risks

- **Drift de la API de hooks de los frameworks** (ADK callbacks, LangChain middleware): mitigación — aislar todo en el adaptador, contrato `Engine.evaluate` estable, tests de integración con agentes de juguete que fallan si el hook cambia.
- **Cobertura de decodificación de calldata:** selectores desconocidos van a fail-closed (correcto para seguridad) pero pueden frustrar al dev con denegaciones legítimas. Mitigación — tabla de selectores extensible por el dev y razón explícita ("selector no reconocido") que orienta a registrarlo.
- **Normalización de montos / decimales:** un decimal mal configurado hace que los límites se evalúen mal (riesgo de dinero). Mitigación — validación del registro de decimales en el `Mandate`, tests de borde con USDC(6)/WETH(18), y fail-closed si falta el decimal de un token con `SpendLimit`.
- **StateStore in-memory pierde acumulados al reiniciar:** los límites por período se resetean si el proceso cae. Mitigación — documentado como limitación explícita del MVP; interfaz `StateStore` lista para impl. persistente. No bloquea el MVP (un dev corre el agente en un proceso vivo).
- **Mismatch sync/async en adaptadores:** mitigación — el adaptador detecta contexto async y usa el puente adecuado; cubierto por tests de integración en ambos modos.

## Test plan

- **Unit (`tests/unit/`):** una suite por política (`SpendLimit`, allowlists, `TimeWindow`, `RateLimit`) con bordes obligatorios (límite exacto inclusivo/exclusivo, acumulado que cruza umbral, ventana en el filo, mandato expirado/revocado). Resolver: decode de calldata real (transfer/approve/transferFrom, value nativo, swap de router conocido) y casos UNRESOLVABLE/PASS_THROUGH. Audit: integridad de hash chain (detección de manipulación de entrada intermedia, AC-7). `mypy --strict` verde sobre core y policies.
- **Integration (`tests/integration/`):** Engine end-to-end con `Mandate` real recorriendo AC-1..AC-9; adaptadores ADK y LangChain con agentes de juguete que verifican que DENY **realmente** impide la ejecución del tool (no solo devuelve un mensaje) y que pass-through no interfiere (AC-6, AC-10).
- **E2E (`tests/e2e/`):** un agente de ejemplo con un mandato realista ejecutando los 4 escenarios (allow / deny por límite por tx / deny por destino / escalate con `ConsoleHumanReviewer` mockeado) y verificando las entradas resultantes en el audit trail.
- **Coverage:** sin número rígido (Constitution); Policy Engine y Resolver como zonas no negociables — toda rama de decisión cubierta.
