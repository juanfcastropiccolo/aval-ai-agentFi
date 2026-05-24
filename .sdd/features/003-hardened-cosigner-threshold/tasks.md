# Tasks: Co-autorización endurecida — clave custodiada y umbral M-de-N

Feature ID: 003
Status: tasked
Last updated: 2026-05-23

> Orden estricto: Setup → Data → Feature work → Testing → Polish. Cada tarea es ~1 commit / PR chico.
> Reusa el core de 001/002. Los cambios a interfaces de la 002 son internos: las tareas que los tocan
> deben dejar la suite de 002 verde (actualizándola donde haga falta).

## Setup

- [x] 1. **Extra `aval[kms]` + scaffolding** — agregar extra `aval[kms]` (`boto3`) en `pyproject.toml`.
  **Done when:** `pip install -e ".[kms,safe,service,dev]"` instala y `python -c "import boto3"` corre.

## Data

- [x] 2. **Abstracción `Signer` + `LocalKeystoreSigner`** — `aval/execution/signer.py`: ABC `Signer`
  (`address`, `sign_hash(digest) -> bytes` 65B r‖s‖v) y `LocalKeystoreSigner` (keystore JSON v3 cifrado,
  passphrase del entorno). **Done when:** unit tests: encrypt/decrypt round-trip y firma que recupera a
  `signer.address`; la clave no aparece en texto plano. *(FR-1, FR-2, AC-4, AC-7)*
- [x] 3. **`KmsSigner` (AWS KMS)** — `aval/execution/signer.py`: deriva address de la pubkey del KMS
  (DER SPKI → pubkey sin comprimir → keccak); `sign_hash` llama `kms.sign(DIGEST)`, decodifica DER→(r,s),
  normaliza low-s (EIP-2) y recupera `v∈{27,28}` por prueba contra la address. **Done when:** unit tests
  con un fake-KMS respaldado por una clave secp256k1 real verifican derivación de address + firma
  recuperable a esa address + low-s. *(FR-1, AC-7)*
- [x] 4. **Refactor `Authorizer`: clave → `Signer`** — `Authorizer` recibe un `Signer` (su `address` =
  `signer.address`; firma vía `signer.sign_hash`). **Done when:** unit tests del Authorizer pasan con un
  `Signer` y la **suite de la 002 queda verde** (actualizada al nuevo constructor). *(FR-1, FR-10)*

## Feature work

- [x] 5. **Autenticación del servicio** — `service.py`: dependencia que exige `Authorization: Bearer <token>`
  (comparación en tiempo constante) en `/authorize` y `/executed`; `CosignerClient` envía su token.
  **Done when:** integration test: 401 sin token / con token inválido, 200 con token válido. *(FR-4, AC-3)*
- [x] 6. **Orquestador de umbral M-de-N** — generalizar el executor: de un co-autorizador a una **lista de
  endpoints + `threshold_m`**; consulta los N en paralelo (con timeout), reúne M co-firmas de respuestas
  ALLOW, combina con la del agente (`combine_signatures`) y ejecuta. **Done when:** unit tests con cosigners
  mockeados: junta M y arma la combinación; con M-1 ALLOW → fail-closed (no ejecuta); con un nodo caído pero
  ≥ M → ejecuta. *(FR-5, FR-7, FR-8, AC-1, AC-2, AC-6)*
- [x] 7. **Independencia y resistencia a nodo malicioso** — cada nodo evalúa el mandato por su cuenta (ya lo
  hace el Authorizer); verificar que una co-firma de un nodo que autoriza algo fuera del mandato **no** basta
  para alcanzar el umbral si los M honestos no autorizan. **Done when:** unit/integration test con un nodo
  "malicioso" (autoriza todo) + M honestos: una acción que viola el mandato no reúne M ALLOW → no se ejecuta.
  *(FR-6, AC-5)*
- [x] 8. **Despliegue del Safe con N+1 owners / umbral M+1** — generalizar el helper de creación del Safe a una
  lista de owners y threshold parametrizable. **Done when:** unit/e2e (EVM in-process) despliega un Safe con
  `N+1` owners y threshold `M+1` y verifica owners/threshold. *(FR-5)*
- [x] 9. **Observabilidad** — logging estructurado de cada decisión (veredicto, reason_code, agente, hash) **sin
  secretos**, y endpoint `/health`. **Done when:** test que verifica que el log de una decisión no contiene la
  clave ni el token, e incluye veredicto+código. *(FR-9, AC-8)*
- [x] 10. **Entrypoint del co-autorizador corrible** — un binario/servicio parametrizable por config (backend de
  `Signer`, registro de mandatos, token de auth) levantable con `uvicorn`. **Done when:** se puede levantar un
  nodo desde config y responde `/health`. *(FR-3)*

## Testing

- [x] 11. **Integración M-de-N por HTTP** — N nodos (cada uno `TestClient` con su token y su `Signer`); el
  orquestador reúne M y arma la ejecución; auth enforced; un nodo que deniega o está caído con ≥ M restantes →
  igual reúne M. **Done when:** todos los escenarios pasan. *(AC-1, AC-2, AC-3, AC-6)*
- [x] 12. **E2E umbral on-chain (EVM in-process)** — Safe con `N+1` owners / threshold `M+1`; el orquestador con
  agente + M co-firmas **ejecuta**; con solo M-1 **revierte** (prueba de no-evitabilidad del umbral). Variante con
  `KmsSigner` (fake-KMS) para validar que la firma estilo-KMS es **aceptada on-chain**. **Done when:** ejecución a
  M+1 firmas pasa, a M revierte, y la variante KMS ejecuta. *(AC-1, AC-2, AC-5, AC-7)*

## Polish

- [x] 13. **Docs de despliegue** — sección en el README: configurar N nodos co-autorizadores, KMS vs keystore
  cifrado, tokens de auth, umbral M-de-N, y límites (sin rotación de claves, sin recuperación → feature 005).
  **Done when:** un dev puede configurar y levantar un set de N nodos siguiendo el README. *(FR-3, FR-9)*

## Traceability

| Task | FR | AC |
|------|----|----|
| 2  | FR-1, FR-2 | AC-4, AC-7 |
| 3  | FR-1 | AC-7 |
| 4  | FR-1, FR-10 | AC-4 |
| 5  | FR-4 | AC-3 |
| 6  | FR-5, FR-7, FR-8 | AC-1, AC-2, AC-6 |
| 7  | FR-6 | AC-5 |
| 8  | FR-5 | AC-1 |
| 9  | FR-9 | AC-8 |
| 10 | FR-3 | AC-3 |
| 11 | FR-4, FR-5, FR-8 | AC-1, AC-2, AC-3, AC-6 |
| 12 | FR-5, FR-7 | AC-1, AC-2, AC-5, AC-7 |
| 13 | FR-3, FR-9 | AC-8 |
