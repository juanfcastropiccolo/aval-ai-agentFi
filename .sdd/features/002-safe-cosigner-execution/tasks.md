# Tasks: Ejecución real de transferencias vía co-autorización no-evitable

Feature ID: 002
Status: tasked
Last updated: 2026-05-23

> Orden estricto: Setup → Data → Feature work → Testing → Polish. Cada tarea es ~1 commit / PR chico.
> Reusa el core de la feature 001 sin reimplementarlo. Los cambios a modelos de la 001 son aditivos: las tareas que los tocan deben dejar la suite de la 001 verde.

## Setup

- [x] 1. **Extras y layout de ejecución** — agregar extras `aval[safe]` (`web3`, `safe-eth-py`, `eth-account`) y `aval[service]` (`fastapi`, `uvicorn`, `httpx`) en `pyproject.toml`; crear el paquete `aval/execution/` con `__init__.py`. **Done when:** `pip install -e ".[safe,service,adk,dev]"` instala sin error y `python -c "import aval.execution"` corre.

## Data

- [x] 2. **`ReasonCode` + `reason_code` aditivo** — `ReasonCode` (StrEnum) en `aval/models`; agregar `reason_code` a `PolicyResult` y `Decision` con default retro-compatible; cada política y cada borde del Engine (deny/escalate/unresolvable/expired/revoked/audit-fail/eval-error) setea su código. **Done when:** unit tests verifican el código por política y la **suite de la feature 001 sigue verde**. *(FR-8, AC-9)*
- [x] 3. **`SqliteStateStore`** — implementación de `StateStore` sobre `sqlite3` (archivo local), misma semántica que `InMemoryStateStore`. **Done when:** pasa los mismos tests de contrato (acumulado, conteo, aislamiento por agente) **y** un test de persistencia: reabrir el archivo conserva el acumulado. *(AC-8)*
- [x] 4. **Modelos de SafeTx** — `SafeTxRequest` (`safe_address`, `chain_id`, `to`, `value`, `data`, `operation`, `nonce`, gas, `safe_tx_hash`) y `AuthorizationResponse` (`decision`, `aval_signature`) en `aval/execution/models.py`. **Done when:** validan/serializan a JSON; round-trip verde.

## Feature work

- [x] 5. **Constructor + hash de SafeTx** — `aval/execution/safe_tx.py`: arma una SafeTx desde una transferencia (nativa: `to`=destino, `value`>0, `data`=0x; ERC-20: `to`=token, `data`=transfer calldata) y computa el hash EIP-712 vía `safe-eth-py`. **Done when:** unit test produce un hash determinístico que coincide con el de `safe-eth-py` para vectores conocidos. *(FR-1)*
- [x] 6. **Decodificador SafeTx → `ProposedAction`** — reusa el `EVMResolver` de la 001 sobre el `data` de la SafeTx; `operation != 0` (delegatecall) y patrones por lote/MultiSend → **fail-closed** (UNRESOLVABLE/deny). **Done when:** unit tests cubren transfer ERC-20, transferencia nativa, `operation=1` y lote → fail-closed. *(FR-4, AC-7)*
- [x] 7. **Authorizer (núcleo del co-signer)** — `aval/execution/authorizer.py`: dado `SafeTxRequest` + mandato, decodifica (tarea 6) → `Engine.evaluate` (core 001) → audita la autorización → si ALLOW firma el `safe_tx_hash` con la llave de aval (`eth-account`); si no, devuelve `Decision` con `reason_code`. **Done when:** unit tests: ALLOW devuelve una firma válida sobre el hash; DENY no firma y trae código+razón; expira/revoca → deny. *(FR-2, FR-5, FR-9)*
- [x] 8. **Servicio co-signer HTTP (proceso aislado)** — `aval/execution/service.py` (FastAPI): `POST /authorize` que envuelve al Authorizer; la **llave de aval vive solo acá**. Cliente `httpx` en `aval/execution/cosigner_client.py`. **Done when:** integration test levanta el servicio y verifica ALLOW→firma / DENY→`{code,reason}` por HTTP. *(FR-3)*
- [x] 9. **Freshness: binding a nonce + ventana** — el Authorizer ata la autorización al `nonce` del Safe y a una ventana wall-clock corta; trackea autorizaciones pendientes por nonce. **Done when:** unit tests: una firma para nonce N no valida para una SafeTx con nonce N+1; una autorización fuera de la ventana se considera stale. *(FR-5, AC-5, AC-6)*
- [x] 10. **Capa de cadena (RPC)** — `aval/execution/chain.py` (`web3.py`): leer el `nonce` actual del Safe, construir y enviar `execTransaction(to,value,data,operation,…,signatures)`, esperar el receipt y devolver el tx hash. **Done when:** unit test con `web3` mockeado arma el `execTransaction` correcto (signatures ordenadas por owner) y parsea el receipt. *(FR-1, FR-11)*
- [x] 11. **Tool ADK `transfer_funds`** — `aval/adapters/adk.py` (extra `adk`): tool `transfer_funds(recipient, amount, token)` que arma la SafeTx (tarea 5), firma con la llave del agente, pide la 2ª firma al co-signer (tarea 8), y ejecuta vía la capa de cadena (tarea 10); ante DENY o co-signer caído, no ejecuta y devuelve la razón. **Done when:** integration test con cadena y co-signer mockeados: camino ALLOW ejecuta y devuelve tx hash; DENY no ejecuta y trae razón+código; co-signer inalcanzable → no ejecuta (fail-closed). *(FR-6, FR-10, AC-2, AC-4)*
- [x] 12. **Doble entrada de audit (autorización + ejecución)** — registrar una entrada al **autorizar** (sin tx hash) y otra al **ejecutar** (con el tx hash on-chain), ligadas por el `safe_tx_hash`. **Done when:** integration test muestra las dos entradas enlazadas y la cadena de hash íntegra. *(FR-9, AC-9)*

## Testing

- [x] 13. **Prueba de no-evitabilidad** — verificar que el Safe **no ejecuta con una sola firma**: a nivel integración, contra un EVM in-process (eth-tester) con un Safe 2-de-2 desplegado, `execTransaction` con 1 firma revierte y con 2 firmas (agente + aval) ejecuta. Valida además que nuestro `compute_safe_tx_hash` coincide con el hash del contrato Safe. **Done when:** el test rojo si una sola firma alcanzara; verde con el rechazo y la ejecución a 2 firmas. *(FR-2, FR-3, AC-3)*
- [x] 14. **E2E (local con plata ficticia + Sepolia real)** — ✅ e2e local sobre EVM in-process (`tests/e2e/test_local_fakemoney_e2e.py`: AC-1/2/8). ✅ **e2e real en Sepolia**: Safe 2-de-2 desplegado (`0x36fDCe4e773Bff2916050638E537Bc292Bb6AC8E`), fondeado, y transferencia válida **ejecutada on-chain** vía el flujo de aval (tx `0xb757…158d` y, vía agente ADK+Gemini en lenguaje natural, tx `0xe069…707e`); destino no permitido y monto excedido → sin tx. Demos: `examples/safe_transfer_demo.py` (local) y `examples/adk_sepolia_agent.py` (Sepolia, lenguaje natural). *(AC-1, AC-2, AC-8)*

## Polish

- [x] 15. **Ejemplo + docs de setup** — `examples/adk_safe_transfer.py` corrible y una sección en el README: cómo desplegar el Safe 2-de-2, conseguir RPC y fondos de faucet, correr el co-signer y el agente. Documentar límites: llave de aval no grado producción, ventana de freshness, sin lotes, sin swaps/DeFi. **Done when:** un dev puede ir de cero a un transfer en Sepolia siguiendo el README. *(FR-6)*

## Traceability

| Task | FR | AC |
|------|----|----|
| 2  | FR-8 | AC-9 |
| 3  | FR (estado persistente) | AC-8 |
| 4  | FR-1, FR-4 | — |
| 5  | FR-1 | AC-1 |
| 6  | FR-4 | AC-7 |
| 7  | FR-2, FR-5, FR-9 | AC-2, AC-9 |
| 8  | FR-3 | AC-3, AC-4 |
| 9  | FR-5 | AC-5, AC-6 |
| 10 | FR-1, FR-11 | AC-1, AC-6 |
| 11 | FR-6, FR-10 | AC-2, AC-4 |
| 12 | FR-9 | AC-9 |
| 13 | FR-2, FR-3 | AC-3 |
| 14 | FR-1, FR-6 | AC-1, AC-2, AC-8 |
| 15 | FR-6 | AC-1 |
