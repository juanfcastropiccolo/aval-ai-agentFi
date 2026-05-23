# Plan: Ejecución real de transferencias vía co-autorización no-evitable

Feature ID: 002
Status: planned
Last updated: 2026-05-23

## Chosen stack

- **Cuenta custodia:** **Safe** (smart account) configurada **2-de-2**, owners = {llave del agente, llave de aval}. La no-evitabilidad (FR-2) es la propiedad nativa del threshold: sin la firma de aval no se alcanza el quórum y `execTransaction` no ejecuta.
- **Construcción/hash/firma de SafeTx:** `safe-eth-py` (mantenida por Safe Global) sobre `web3.py` + `eth-account`. Da el hash EIP-712 correcto de la SafeTx y el armado de `execTransaction`. Evita hand-rollear el hashing (un hash mal = firma inválida = dinero trabado).
- **Servicio co-signer (dominio aislado, FR-3):** proceso **separado** (FastAPI + uvicorn) que **tiene la llave de aval** y expone `POST /authorize`. Recibe una SafeTx, decodifica su call interna, corre el `Engine` de la feature 001, y si ALLOW firma el hash y devuelve la firma. El agente nunca tiene la llave de aval.
- **Lado agente:** agente **ADK** (`google-adk`, ya en extras) con un modelo Gemini, y un tool `transfer_funds(recipient, amount, token)` que arma la SafeTx, la firma con la llave del agente, pide la 2ª firma al co-signer, y **transmite** `execTransaction` a la red.
- **Riel / RPC:** **Sepolia** vía `web3.py` contra un endpoint RPC (Alchemy/Infura). Aislado en una capa `chain` — el core sigue sin RPC (honra la Constitution).
- **Estado persistente (FR / edge "reinicio"):** `SqliteStateStore` implementando la interfaz `StateStore` de la 001, sobre `sqlite3` (stdlib, archivo local, sin servidor — coherente con "sin DB servidor en MVP"; la interfaz ya estaba prevista como pluggable).
- **Lenguaje/tooling:** Python 3.11+, `ruff`, `mypy --strict` (sobre core/policies/models; la capa `execution` y `service` quedan fuera del strict por su acoplamiento a libs sin tipos, igual que los adaptadores), `pytest`.

Empaquetado: nuevos extras `aval[safe]` (web3, safe-eth-py, eth-account) y `aval[service]` (fastapi, uvicorn, httpx). El core sigue sin estas dependencias.

## Architecture overview

Dos procesos separados por una frontera de confianza. El **agente** arma y transmite; el **co-signer** decide y firma con la llave de aval. El core de la feature 001 se reusa intacto dentro del co-signer.

```
┌─ Proceso AGENTE (tiene llave del agente) ─┐      ┌─ Servicio CO-SIGNER (tiene llave de aval) ─┐
│ Agente ADK (LLM)                          │      │ POST /authorize {SafeTx, mandate_ref}       │
│  └ tool transfer_funds(to,amount,token)   │      │   1. recompone y valida el hash de la SafeTx│
│      1. arma calldata + SafeTx (nonce)    │ HTTP │   2. Resolver decodifica data → ProposedAction (FR-4)│
│      2. firma con llave AGENTE  (1/2) ─────┼─────►│   3. Engine.evaluate (core 001) → Decision  │
│      3. /authorize → firma aval (2/2)      │      │   4. audita la autorización                 │
│      4. execTransaction(2 firmas) ──► ⛓️   │      │   5. ALLOW→firma el hash; DENY→{code,reason}│
│      5. registra ejecución (tx hash)       │      └─────────────────────────────────────────────┘
└────────────────────────────────────────────┘
```

**Quién transmite:** lo hace el **agente**, no aval (ver trade-offs). aval queda como autorizador puro: nunca toca la cadena ni mueve fondos.

**Verdad de fondo (FR-4):** el co-signer decodifica el campo `data` de la SafeTx (la call real: `transfer` ERC-20 o transferencia nativa con `value`), no lo que el agente "dice". `operation != 0` (delegatecall) y patrones por lote/MultiSend no descomponibles → **fail-closed deny**.

**Freshness (FR-5):** se compone de (a) **binding al nonce** del Safe — la firma vale solo para esa SafeTx y el nonce se consume al ejecutar (anti-replay, anti-doble-ejecución, nativo del Safe); (b) **evaluación al momento de firmar** — aval chequea mandato activo y límites *ahora*; (c) el co-signer trackea autorizaciones pendientes por nonce con una **ventana wall-clock corta**. La expiración *on-chain* dura (un guard que rechace tras un deadline) queda en roadmap.

## Data model

Extensiones a modelos de la 001 (aditivas):
- **`ReasonCode`** (StrEnum) en `aval/models`: `OK`, `SPEND_LIMIT_PER_TX`, `SPEND_LIMIT_DAILY`, `RECIPIENT_NOT_ALLOWED`, `TARGET_NOT_ALLOWED`, `TOKEN_NOT_ALLOWED`, `METHOD_NOT_ALLOWED`, `TIME_WINDOW`, `RATE_LIMIT`, `MANDATE_EXPIRED`, `MANDATE_REVOKED`, `UNRESOLVABLE`, `DEFAULT_DENY`, `HUMAN_REJECTED`, `AUDIT_FAILURE`, `EVAL_ERROR`.
- **`PolicyResult.reason_code`** y **`Decision.reason_code`** (FR-8) — campos nuevos con default, retro-compatibles. Cada política setea su código.

Modelos nuevos (`aval/execution/`):
- **`SafeTxRequest`**: `safe_address`, `chain_id`, `to`, `value`, `data`, `operation`, `nonce`, params de gas, `safe_tx_hash`.
- **`AuthorizationResponse`**: `decision: Decision`, `aval_signature: str | None`.

Persistencia (`SqliteStateStore`): tablas `spend(agent_id, token, period, bucket, amount)` y `action_count(agent_id, period, bucket, n)`, claves primarias compuestas. Misma semántica que `InMemoryStateStore`.

Audit (reuso): el `AuditEntry` ya tiene `tx_hash`. Como el trail es append-only, se registran **dos entradas** ligadas por el `safe_tx_hash` en `action`: una al **autorizar** (sin tx hash) y otra al **ejecutar** (con el tx hash on-chain), satisfaciendo FR-9 sin mutar entradas.

## External dependencies

- **`web3.py`** (extra `safe`): RPC a Sepolia, lectura de nonce del Safe, envío de `execTransaction`, firma con `eth-account`. Aislado en `aval/execution/chain.py`.
- **`safe-eth-py`** (extra `safe`): armado y hash EIP-712 de SafeTx; encode de `execTransaction`.
- **`fastapi` + `uvicorn` + `httpx`** (extra `service`): el servicio co-signer (servidor) y el cliente que el tool del agente usa.
- **`google-adk`** (extra `adk`, ya existe) + un **modelo Gemini** (requiere API key) para el agente del e2e.
- **`sqlite3`** (stdlib): estado persistente. Sin servidor.
- **Infra externa que el dev provee:** un endpoint RPC de Sepolia, un Safe 2-de-2 desplegado y fondeado en Sepolia, y dos llaves de testnet (agente + aval).

## Trade-offs considered

- **Co-signer off-chain vs Safe Guard on-chain:** elegido off-chain (Opción A). El Guard pondría política on-chain (límites diarios, allowlists, rate limits son carísimos/complejos on-chain) y contradice "core off-chain, in-process" de la Constitution. La no-evitabilidad ya la da el threshold 2-de-2. Guard = roadmap si se quiere enforcement on-chain duro.
- **Transmite el agente vs transmite aval:** elegido **agente transmite**. Mantiene a aval como autorizador puro que nunca toca la cadena ni mueve fondos (FR-3). Costo: existe una ventana entre que aval firma y el agente ejecuta (freshness imperfecto). Rechazado "aval relayer": minimiza la ventana pero convierte a aval en transmisor y le suma responsabilidad de gas/red. La ventana se mitiga con nonce + ventana corta; el cierre duro es el guard (roadmap).
- **Freshness por nonce+ventana vs deadline on-chain:** elegido nonce + evaluación al firmar + ventana wall-clock. Una firma de Safe no expira on-chain por sí sola; un deadline duro requiere un guard. Para testnet, nonce-binding (que ya da anti-replay y anti-doble-ejecución) + ventana corta es suficiente y honesto. Deadline on-chain = roadmap.
- **`safe-eth-py` vs hand-roll del hash EIP-712:** elegido `safe-eth-py`. Hand-rollear el dominio EIP-712 y el encoding de SafeTx es propenso a un error silencioso que produce un hash distinto → la firma no validaría on-chain. La lib mantenida por Safe es la fuente de verdad.
- **SQLite vs Redis/Postgres para estado:** elegido SQLite (archivo, stdlib, sin servidor) para el co-signer único del MVP. Redis/Postgres recién cuando haya múltiples instancias o autorizador threshold (roadmap).
- **Servicio HTTP separado vs co-signer in-process:** elegido **proceso separado**. Es *requisito* de la garantía (FR-3): si la llave de aval viviera en el proceso del agente, el enforcement sería evitable. In-process rompería la propiedad central de la feature.
- **`reason_code` como enum nuevo vs parsear el texto:** elegido enum aditivo en `PolicyResult`/`Decision`. Parsear strings es frágil; un código estable es accionable por el agente y la analítica (FR-8).

## Risks

- **Corrección del hash de SafeTx (dominio EIP-712 / chainId):** un mismatch hace que la firma de aval no valide y la tx no ejecute. Mitigación: `safe-eth-py` + un test de integración donde un Safe real en Sepolia **acepta** la firma (la prueba definitiva).
- **Custodia de la llave de aval:** en testnet vive en el entorno del servicio (env/archivo). Mitigación: documentar explícitamente que **no es grado producción**; HSM/KMS = roadmap. Aislada del proceso del agente.
- **Dependencia de modelo/API para el e2e:** el agente ADK necesita un modelo (API key). Mitigación: unit e integración **no** dependen del LLM (se prueban el co-signer y el tool directamente); el e2e con LLM va detrás de un flag con credenciales presentes, salteado en CI.
- **Ventana de freshness (firmado-pero-no-ejecutado):** si el mandato se revoca tras firmar y antes de ejecutar, la SafeTx firmada podría ejecutarse hasta que cambie el nonce. Mitigación: ventana corta + documentación; cierre duro = guard (roadmap).
- **delegatecall / lotes / MultiSend:** vectores para colar una call no evaluada. Mitigación: `operation != 0` y patrones no descomponibles → fail-closed deny.
- **Flakiness de testnet (faucet, RPC, confirmaciones):** el e2e depende de red. Mitigación: reintentos, timeouts y marcarlo como suite aparte fuera de CI.
- **Condición de carrera de acumulados (parallel-drain):** sigue presente (no es objetivo de esta feature). Mitigación: documentada; el `SqliteStateStore` permite añadir reserva/locking después. Anotada en backlog.

## Test plan

- **Unit (`tests/unit/`):** decode de SafeTx → `ProposedAction` (transfer ERC-20, transferencia nativa, `operation=1`/lote → fail-closed); firma de aval produce una firma válida sobre el hash; `SqliteStateStore` cumple el contrato `StateStore` (acumulado, conteo, persistencia tras reabrir el archivo); cada política setea su `reason_code`; `mypy --strict` verde sobre core/policies/models.
- **Integration (`tests/integration/`):** co-signer service ALLOW→devuelve firma / DENY→`{code,reason}` sin firma; **el Safe rechaza ejecutar con una sola firma** (prueba de no-evitabilidad, FR-2/AC-3); el tool ADK arma la SafeTx, obtiene la 2ª firma y construye un `execTransaction` válido; binding de nonce (una firma no sirve para otra SafeTx, AC-5/AC-6); fail-closed con co-signer caído (AC-4); doble entrada de audit (autorización + ejecución, AC-9).
- **E2E (`tests/e2e/`, detrás de flag con RPC+llaves+Safe):** Safe 2-de-2 real en Sepolia, fondeado; el agente ADK recibe "transferí X a Y" → la tx se ejecuta y aparece en el explorador (AC-1); pedido que viola el mandato → sin tx + razón y código (AC-2); reinicio del co-signer y verificación de que el acumulado sobrevive (AC-8).
