# aval — Diseño del MVP

**Fecha:** 2026-05-22
**Estado:** Aprobado (brainstorming) — pendiente de plan de implementación
**Working dir:** `/Users/juanfcastropiccolo/Documents/Personal/proyecto-agentfi`

---

## 1. Resumen y propósito

**aval** es una librería Python framework-agnóstica que provee una **capa de confianza para agentes de IA que manejan dinero** (AgentFi). Responde, del lado del desarrollador, a la pregunta de Pilar Rodríguez: *"¿cómo confiar en que un agente maneje tu capital?"*

El MVP ataca la primera de las tres primitivas de Pilar — **ejecución permisionada** — porque da valor inmediato y egoísta al dev (su agente no puede vaciar la wallet ni ser drenado por prompt injection) y genera el **audit trail** que en fases siguientes se convierte en el track record verificable (el verdadero white space del mercado).

El nombre `aval` viene del español: la garantía/endoso financiero que una parte da por otra — exactamente lo que hace la capa.

### Decisiones de producto (fijadas en brainstorming)
- **Ambición:** producto/startup, con un MVP defendible.
- **Usuario primario:** el **desarrollador del agente** (oferta). Adopción tipo developer-tool: fricción mínima.
- **Wedge:** ejecución permisionada con **enforcement in-loop**.
- **Rails:** **crypto/EVM primero**.
- **Primeros adaptadores:** **Google ADK** y **LangChain/LangGraph**.

---

## 2. Arquitectura general

Un **core de decisión framework-agnóstico** que no conoce ningún framework: recibe una acción propuesta normalizada y devuelve un veredicto. Los frameworks se conectan vía **adaptadores delgados** que traducen su hook nativo de tool-call a una llamada al core y el veredicto de vuelta.

```
Agente del dev (LangChain / ADK / …)
   LLM → tool call: transfer(0xAbc, 5000 USDC)
        │  (hook nativo del framework)
   ADAPTADOR (delgado, ~80–150 LOC)        ← uno por framework
        │  ProposedAction (normalizado)
   CORE DE DECISIÓN (framework-agnóstico)
     1. EVM Resolver  → decodifica calldata (¿mueve dinero? ¿cuánto/adónde?)
     2. Policy Engine → evalúa el Mandato
     3. Audit Trail   → registra + hash
        │  Decision{ALLOW | DENY | ESCALATE}
   ADAPTADOR mapea el veredicto
     ALLOW → ejecuta normal
     DENY  → bloquea (return False / dict / tripwire)
     ESCALATE → human-in-the-loop
```

### Componentes (responsabilidad única, testeables por separado)
1. **EVM Resolver** — convierte una tool call cruda en una `ProposedAction` normalizada (rail, token, monto, destino, selector); decide si la call mueve dinero.
2. **Policy Engine** — evalúa la `ProposedAction` contra el Mandato activo; devuelve un `Decision`. Default-deny, conjunción de políticas.
3. **Audit Trail** — registro append-only firmado de cada decisión, con hash encadenado y anclable onchain.
4. **Adaptadores** — shims por framework (ADK, LangChain) que enganchan el hook y mapean `Decision` al idioma del framework. No deciden nada.

El core es una librería instalable (`pip install aval`), **sin servidor ni red en el MVP**.

---

## 3. El Mandato y el Policy Engine

El **Mandato** es la declaración explícita de las reglas bajo las que el agente puede mover dinero. Diseñado con *forma de datos compatible-AP2* (para que mañana sea una Verifiable Credential firmada sin rehacer el modelo); en el MVP se define en código y se evalúa in-process.

```python
Mandate(
    agent_id="aval:agent:0x1234…",        # identidad del agente (futuro ERC-8004/DID)
    granted_by="0xOwner…",                 # quién otorga la autoridad (chain de autoridad)
    chains=["base", "arbitrum"],           # EVM permitidas
    policies=[
        SpendLimit(token="USDC", per_tx=5_000, per_day=20_000),
        AllowedTargets(contracts=["0xUniV3…", "0xAaveV3…"]),
        AllowedTokens(["USDC", "USDT", "WETH"]),
        AllowedMethods(["transfer", "approve", "swap"]),
        RecipientAllowlist(["0xTreasury…", "0xUniV3…"]),
        TimeWindow(start="09:00", end="21:00", tz="UTC"),
        RateLimit(max_actions=50, per="day"),
    ],
    expires_at="2026-12-31T00:00:00Z",
    revocable=True,
)
```

### Semántica de evaluación (capability-security: default-deny + atenuación)
- **Default-deny:** si ninguna política autoriza explícitamente, se deniega.
- **Conjunción:** la acción debe pasar **todas** las políticas aplicables; una que falle ⇒ `DENY`.
- **Tres veredictos:**
  - `ALLOW` — todo pasa.
  - `DENY` — alguna política la rechaza.
  - `ESCALATE` — permitida pero marcada para aprobación humana (montos sobre umbral, destinos nuevos). Evita desastres tipo Replit/Bankrbot sin frenar todo.
- **Decision explicable:** siempre incluye `reason` y `failed_policy`, para el audit trail y para devolverle al LLM un mensaje accionable.

### Catálogo de políticas del MVP
Cada política es una clase chica que implementa `evaluate(action) -> PolicyResult`, testeable aislada.

| Política | Qué acota | Mapea a (futuro onchain) |
|---|---|---|
| `SpendLimit` | monto por tx y por período | `ERC20TransferAmount` / `ValueLte` |
| `AllowedTargets` | contratos invocables | `AllowedTargetsEnforcer` |
| `AllowedTokens` | tokens manejables | calldata enforcer |
| `AllowedMethods` | selectores de función | `AllowedMethodsEnforcer` |
| `RecipientAllowlist` | destinos de fondos | calldata enforcer |
| `TimeWindow` | franja horaria | `TimestampEnforcer` |
| `RateLimit` | nº de acciones por período | `LimitedCalls` / period enforcer |

El Policy Engine es extensible: una política nueva = una clase nueva, sin tocar el core. El estado con memoria (gasto acumulado, conteo de acciones) vive en un `StateStore` pluggable (in-memory en MVP; Redis/DB después).

---

## 4. Flujo en runtime y el EVM Resolver

Las tool calls no vienen normalizadas: un framework expone `send_transaction({to, value, data})` crudo y otro `swap_tokens(token_in, token_out, amount)` de alto nivel. El Resolver convierte ese caos en una `ProposedAction`.

```
1. El agente emite una tool call  →  el adaptador la captura ANTES de ejecutarla
2. Adaptador entrega {tool_name, args} al Core
3. EVM Resolver clasifica:
     ¿Es un tool financiero? (según registro declarado por el dev)
        ├─ NO  → PASS-THROUGH (no es asunto de aval)
        └─ SÍ  → intenta resolver a ProposedAction
                    ├─ resuelto OK   → al Policy Engine
                    └─ no resoluble  → FAIL-CLOSED: DENY (config: ESCALATE por tool)
4. Policy Engine evalúa el Mandato → Decision
5. Audit Trail registra (acción + decision + regla) y devuelve hash
6. Adaptador mapea Decision al idioma del framework
```

### Cómo el Resolver reconoce y parsea dinero — dos capas
1. **Registro de tools financieros (declarativo, lo da el dev).** Explícito a propósito: no se intenta adivinar mágicamente toda tool.
   ```python
   aval.register_tool("send_transaction", kind="raw_evm")          # decodifica calldata
   aval.register_tool("swap_tokens", kind="structured",
       extract=lambda a: ProposedAction(token=a["token_in"],
                                         amount=a["amount"], ...))
   ```
2. **Decodificación de calldata cruda (ABI).** Para `kind="raw_evm"`: ERC-20 `transfer/approve/transferFrom`, value nativo, routers DEX conocidos. Extrae token, monto, destino, selector.

### Postura de seguridad — fail-closed (innegociable)
- Tool financiero **no parseable** ⇒ **`DENY` duro** por default (configurable a `ESCALATE` por tool).
- Calldata ofuscada hacia un contrato de la allowlist ⇒ `ESCALATE` o `DENY` según config.
- Tool **no registrado como financiero** ⇒ pass-through limpio (aval no se mete con `search_web()` etc.). Scope explícito y acotado.
- **Inyección de prompt:** aval no intenta detectar el prompt malicioso (es inganable). Opera en la capa de *acción*: no importa qué convenció al LLM — si la acción viola el Mandato, se bloquea. Enforcement externo al razonamiento.

---

## 5. Audit Trail y verificabilidad

Cada decisión queda registrada de forma que después se empaquete como track record (fase siguiente). Conexión directa con la tesis "the bridge is data".

```python
AuditEntry(
    timestamp, agent_id, mandate_id,
    proposed_action,            # token, monto, destino, selector, chain
    decision,                   # ALLOW | DENY | ESCALATE
    failed_policy, reason,      # explicabilidad
    tx_hash=None,               # se completa si la acción se ejecutó onchain
    prev_hash,                  # encadenamiento (hash chain)
    entry_hash,                 # hash de esta entrada
)
```

### Tres niveles de verificabilidad (los tres en el plan; escalonados)
1. **Nivel 1 — log firmado + hash chain (PRIMER BUILD).** Cada entrada encadena con la anterior (`prev_hash`); editar/borrar una entrada rompe la cadena. Local, sin costo. Entregado end-to-end en el MVP.
2. **Nivel 2 — ancla onchain (EAS) (HITO SIGUIENTE).** Publicar `entry_hash` o un Merkle root de un batch como atestación en Ethereum Attestation Service. Verificable por cualquiera sin confiar en nosotros. Interfaz prevista en el MVP.
3. **Nivel 3 — proof-of-behavior (HITO SIGUIENTE).** Cruzar las acciones ejecutadas con data onchain real (Dune/The Graph/Allium) para confirmar que lo autorizado por aval es lo que pasó en cadena. Fuente de las métricas de track record. Interfaz prevista en el MVP.

### Decisión de diseño
El Audit Trail tiene interfaz propia (`record(entry) -> hash`) y backend pluggable (`LocalJsonlStore` en MVP; S3/DB + EAS anchor después). **Registrar es parte del path crítico: si el audit falla, la decisión falla (fail-closed).**

---

## 6. Adaptadores (ADK + LangChain)

Shims delgados (~80–150 LOC). Toda la lógica vive en el core; los adaptadores no deciden.

### Google ADK — `before_tool_callback` (o Plugin para registro global)
```python
def aval_callback(tool, args, tool_context):
    decision = core.evaluate(tool.name, args)
    if decision.is_allow:
        return None                        # ADK ejecuta el tool normal
    if decision.is_deny:
        return {"error": decision.reason}  # short-circuit: el dict reemplaza el resultado
    if decision.is_escalate:
        return human_review(decision)      # pausa para aprobación
```

### LangChain / LangGraph — middleware `wrap_tool_call`
```python
def aval_middleware(request, handler):
    decision = core.evaluate(request.tool_name, request.args)
    if decision.is_allow:
        return handler(request)            # ejecuta normal
    if decision.is_deny:
        return ToolMessage(decision.reason)  # short-circuit, nunca llama handler
    if decision.is_escalate:
        return human_review(decision)
```

### Contrato común del adaptador
Traducir `(tool_name, args)` → `core.evaluate(...)` → `Decision`, y mapear los tres veredictos a las tres acciones idiomáticas (ejecutar / short-circuit con razón / pausar). Sumar OpenAI Agents SDK o CrewAI después = otro shim del mismo molde, sin tocar el core.

### human_review
aval trae una **implementación default** (prompt por consola, bloqueante) lista para usar. La interfaz queda pluggable para reemplazar por webhook/Slack/etc. aval define la interfaz; el dev puede sustituir la implementación.

---

## 7. Manejo de errores

Todo **fail-closed** (principio rector):
- Resolver no parsea un tool financiero → `DENY`.
- Audit Trail no puede registrar → la decisión falla (no se autoriza sin dejar rastro).
- Excepción inesperada en el Policy Engine → `DENY` + log del error (nunca `ALLOW` por accidente).
- Mandato expirado o revocado → `DENY` con razón explícita.
- Los errores siempre devuelven un `reason` legible que el adaptador pasa al LLM, para que el agente corrija en vez de colgarse.

---

## 8. Testing (TDD, una unidad a la vez)
- **Policy Engine:** unit tests por cada política. Bordes: monto exacto en el límite, acumulado que cruza el umbral, ventana horaria en el filo, mandato expirado.
- **EVM Resolver:** decodificación de calldata real (ERC-20 transfer/approve, value nativo, router DEX) y casos fail-closed (calldata ofuscada, tool no resoluble).
- **Audit Trail:** integridad de la hash chain (detectar manipulación de una entrada intermedia).
- **Adaptadores:** integración con agentes de juguete en ADK y LangChain; verificar que `DENY` realmente bloquea la ejecución.
- **End-to-end:** un agente con un Mandato real intenta (a) transferencia válida → pasa y queda en el audit; (b) excede el límite → bloqueada; (c) destino no permitido → bloqueada; (d) escalamiento → pausa.

---

## 9. Alcance

### Dentro del MVP (primer build)
- Core: EVM Resolver + Policy Engine (7 políticas) + Audit Trail Nivel 1 (hash chain firmado).
- Modelo de Mandato compatible-AP2 (definido en código).
- Adaptadores ADK + LangChain.
- `human_review` default por consola.
- StateStore in-memory.

### Fuera del MVP (en el plan como fases siguientes)
- Audit Nivel 2 (ancla EAS) y Nivel 3 (proof-of-behavior con data onchain) — interfaces previstas en el MVP.
- Signing proxy / gateway (fase allocator, garantía dura independiente del agente).
- Mandatos como VCs firmadas; identidad ERC-8004/DID; reputación / track record.
- Enforcement onchain (ERC-7579 / delegation caveats).
- Servidor MCP; adaptadores OpenAI Agents SDK / CrewAI; StateStore persistente (Redis/DB).
- Soporte fiat / non-EVM.

---

## 10. Contexto de investigación
Diseño fundamentado en una investigación de 5 agentes paralelos (mayo 2026). Hallazgos clave:
- Todos los frameworks convergen en un hook de intercepción pre-ejecución de tool calls → asiento natural de la capa de políticas.
- Patrón probado (Langfuse/OpenTelemetry): core agnóstico + adaptadores delgados.
- Construir sobre estándares existentes (AP2, A2A, x402, ERC-8004/EAS, ERC-7579), no reinventarlos.
- White space: capa neutral de permisos+reputación+guardrails portable entre wallets/rails/frameworks. No construir wallet (comoditizada) ni rail (x402 ganó).
- Problemas abiertos más duros: registries de reputación casi vacías; identidad ≠ accountability legal; las instrucciones en lenguaje natural no son enforcement (Replit, Bankrbot $200k, Freysa).

Detalle en la memoria del proyecto: `[[agentfi-trust-layer-project]]`, `[[agentfi-source-article]]`.
