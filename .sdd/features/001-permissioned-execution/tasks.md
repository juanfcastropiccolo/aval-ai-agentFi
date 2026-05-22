# Tasks: Ejecución permisionada de movimientos de dinero

Feature ID: 001
Status: tasked
Last updated: 2026-05-22

> Orden estricto: Setup → Data → Feature work → Testing → Polish. Cada tarea es ~1 commit / PR chico.
> Convención de tests: cada tarea de Feature work se entrega con sus tests unitarios; la sección Testing agrega los niveles integración y e2e que cruzan componentes.

## Setup

- [x] 1. **Bootstrap del paquete** — crear `pyproject.toml` (hatchling), layout `aval/{models,core,policies,adapters}/` con `__init__.py`, deps runtime del core (`pydantic>=2`, `eth-abi`, `eth-utils`) y extras `[adk]`/`[langchain]`/`[dev]`. **Done when:** `pip install -e .[dev]` instala sin error y `python -c "import aval"` corre.
- [x] 2. **Tooling** — configurar `ruff` (format + lint, línea 100), `mypy --strict` apuntando a `aval/core` y `aval/policies`, `pytest` + `pytest-cov`. **Done when:** `ruff check .`, `mypy aval/core aval/policies` y `pytest` corren sobre el repo vacío sin error (0 tests passing).

## Data

- [x] 3. **Enums y modelos base de dominio** — `Verdict (StrEnum: ALLOW|DENY|ESCALATE)`, `ProposedAction`, `PolicyResult` (con helpers `not_applicable()`), `Decision` (helpers `is_allow/is_deny/is_escalate`) en `aval/models/`. **Done when:** los modelos validan/serializan a JSON y `mypy --strict` pasa; test de round-trip JSON verde.
- [x] 4. **Modelo `Mandate`** — `agent_id`, `granted_by`, `chains`, `policies`, `token_decimals`, `expires_at`, `revocable`, `revoked`, más `is_active(now) -> bool`. Validación del registro de decimales. **Done when:** unit tests de `is_active` (activo / expirado / revocado) y de validación de decimales pasan. *(FR-1, FR-13)*
- [x] 5. **`StateStore` interface + `InMemoryStateStore`** — `get_spend(agent_id, token, window)`, `get_action_count(agent_id, window)`, `commit(action)` con buckets por `(agent_id, ventana)`. **Done when:** unit test que acumula gasto y conteo por ventana y verifica aislamiento entre agentes pasa.
- [x] 6. **`AuditEntry` + hashing canónico** — modelo con `prev_hash`/`entry_hash`; `entry_hash = sha256(canonical_json(entry sin entry_hash) + prev_hash)`; HMAC opcional con clave local. **Done when:** unit test verifica determinismo del hash y que cambiar cualquier campo cambia el `entry_hash`.

## Feature work

- [x] 7. **EVM Resolver** — `aval/core/resolver.py`: tabla estática de selectores (`a9059cbb`→transfer, `095ea7b3`→approve, `23b872dd`→transferFrom, swaps de routers DEX comunes), decode de calldata vía `eth-abi`, normalización de monto por `token_decimals`. Devuelve `ProposedAction` | `PASS_THROUGH` | `UNRESOLVABLE`. Tabla extensible por el dev. **Done when:** unit tests cubren transfer/approve/transferFrom, value nativo, swap conocido, selector desconocido (UNRESOLVABLE) y tool no-financiero (PASS_THROUGH). *(FR-5, FR-11)*
- [x] 8. **Política `SpendLimit`** — `per_tx` y `per_day` por token, consulta `StateStore` para acumulado. Límite inclusivo/exclusivo definido y consistente; fail-closed si falta el decimal del token. **Done when:** unit tests de borde (monto en el límite exacto, acumulado que cruza el umbral) pasan. *(FR-2)*
- [x] 9. **Políticas de allowlist** — `AllowedTargets`, `RecipientAllowlist`, `AllowedTokens`, `AllowedMethods` (una clase por archivo en `aval/policies/`); cada una devuelve `not_applicable()` cuando la dimensión no aplica a la acción. **Done when:** unit tests de dentro/fuera de lista y de no-aplicabilidad por política pasan. *(FR-3)*
- [x] 10. **Políticas temporales** — `TimeWindow(start, end, tz)` con comportamiento determinístico en los bordes exactos, y `RateLimit(max_actions, per)` apoyada en `StateStore`. **Done when:** unit tests de ventana (dentro, fuera, en el filo) y de conteo de acciones por período pasan. *(FR-4)*
- [x] 11. **Policy Engine (conjunción default-deny)** — `aval/core/policy_engine.py`: evalúa todas las políticas aplicables del mandato; autoriza solo si todas pasan; produce `Decision{verdict, reason, failed_policy}`. **Done when:** unit tests de conjunción (todas pasan → ALLOW; una falla → DENY con `failed_policy`; una escala → ESCALATE) pasan. *(FR-6, FR-7, FR-9)*
- [x] 12. **`HumanReviewer` interface + `ConsoleHumanReviewer`** — interfaz `review(action, decision) -> ALLOW|DENY` y una impl. por stdin lista para usar sin configuración. **Done when:** unit test con stdin mockeado (aprobar → ALLOW, rechazar → DENY) pasa. *(FR-8)*
- [x] 13. **`AuditStore` interface + `JsonlAuditStore`** — append-only en JSONL con hash chain encadenado; `record(entry) -> entry_hash` y `verify() -> bool` que detecta manipulación de cualquier entrada. **Done when:** unit tests de append correcto y de detección de manipulación de una entrada intermedia pasan. *(FR-10)*
- [x] 14. **`Engine.evaluate()` (orquestación)** — `aval/core/engine.py`: pipeline Resolver → PolicyEngine → (HumanReviewer si ESCALATE) → `state.commit` solo si ALLOW → `AuditStore.record` (fail-closed si falla el registro). PASS_THROUGH → allow; UNRESOLVABLE/expirado/revocado/error → deny y registrado. **Done when:** integration test del pipeline recorre allow / deny / escalate / pass-through / unresolvable y cada uno deja la entrada de audit esperada. *(FR-6, FR-7, FR-8, FR-13, edge cases fail-closed)*
- [x] 15. **Adaptador ADK** — `aval/adapters/adk.py` (extra `[adk]`): hook `before_tool_callback`/Plugin que llama a `Engine.evaluate`, mapea ALLOW→ejecutar, DENY→bloquear devolviendo la `reason` al agente, ESCALATE→pausa ya resuelta. Maneja contexto async. **Done when:** integration test con agente de juguete ADK verifica que DENY **impide** la ejecución del tool y que la `reason` llega al agente. *(FR-9, FR-12)*
- [x] 16. **Adaptador LangChain/LangGraph** — `aval/adapters/langchain.py` (extra `[langchain]`): middleware `wrap_tool_call` con el mismo mapeo de veredictos y puente sync/async. **Done when:** integration test con agente de juguete LangChain verifica que DENY bloquea de verdad y pass-through no interfiere. *(FR-9, FR-12)*

## Testing

- [x] 17. **Suite de aceptación end-to-end del Engine** — un `Mandate` realista recorriendo AC-1..AC-9 contra `Engine.evaluate` (sin framework). **Done when:** los 9 escenarios pasan y verifican veredicto + razón + entrada de audit. *(AC-1..AC-9)*
- [x] 18. **Integridad del audit trail** — test dedicado que altera una entrada intermedia del JSONL y verifica que `verify()` detecta la manipulación. **Done when:** test rojo si la cadena no detectara el cambio; verde con la detección. *(AC-7)*
- [x] 19. **E2E con agente de ejemplo** — un agente de ejemplo con mandato realista corriendo los 4 escenarios (allow / deny por límite por tx / deny por destino / escalate con `ConsoleHumanReviewer` mockeado) y verificando el audit trail resultante. **Done when:** el script e2e pasa en CI sin intervención manual. *(AC-1, AC-2, AC-3, AC-5, AC-10)*

## Polish

- [x] 20. **README + límites del MVP** — quickstart (`pip install aval[...]` + envolver el agente), ejemplo mínimo de mandato, y documentación explícita de las limitaciones (StateStore in-memory se resetea al reiniciar, sin RPC, sin onchain anchoring). **Done when:** un dev puede integrar aval siguiendo solo el README. *(FR-12)*

## Traceability

| Task | FR | AC |
|------|----|----|
| 4  | FR-1, FR-13 | AC-9 |
| 5  | FR-2, FR-4 (soporte estado) | AC-4 |
| 6  | FR-10 | AC-7 |
| 7  | FR-5, FR-11 | AC-6, AC-8 |
| 8  | FR-2 | AC-1, AC-2, AC-4 |
| 9  | FR-3 | AC-3 |
| 10 | FR-4 | AC-5 (umbral temporal/rate) |
| 11 | FR-6, FR-7, FR-9 | AC-2, AC-5 |
| 12 | FR-8 | AC-5 |
| 13 | FR-10 | AC-7 |
| 14 | FR-6, FR-7, FR-8, FR-13 | AC-1, AC-5, AC-8, AC-9 |
| 15 | FR-9, FR-12 | AC-10 |
| 16 | FR-9, FR-12 | AC-6, AC-10 |
| 17 | FR-6, FR-7 | AC-1..AC-9 |
| 18 | FR-10 | AC-7 |
| 19 | FR-8, FR-12 | AC-1, AC-2, AC-3, AC-5, AC-10 |
| 20 | FR-12 | AC-10 |
