# Plan: Co-autorización endurecida — clave custodiada y umbral M-de-N

Feature ID: 003
Status: planned
Last updated: 2026-05-23

## Chosen stack

- **Abstracción de firma:** interfaz `Signer` (`aval/execution/signer.py`) con `address: str` y
  `sign_hash(digest: bytes) -> bytes` (firma de 65 bytes r‖s‖v, el formato que ya consume
  `combine_signatures`). El `Authorizer` deja de recibir una private key en texto y recibe un `Signer`.
- **Backend de producción — AWS KMS** (`KmsSigner`): clave `ECC_SECG_P256K1` en KMS; se firma con
  `kms.sign(MessageType=DIGEST, SigningAlgorithm=ECDSA_SHA_256)` — **la clave nunca sale del KMS**.
  La address se deriva una vez de la pubkey del KMS (`kms.get_public_key`, DER SPKI → pubkey
  sin comprimir → keccak). Elegido por ser el backend mejor documentado para firma secp256k1 de
  Ethereum; aislado tras `Signer`, así que GCP KMS / HSM se agregan después sin tocar el core.
- **Backend de desarrollo — `LocalKeystoreSigner`:** keystore JSON v3 cifrado (vía
  `eth_account.Account.encrypt/decrypt`), passphrase desde el entorno/secret. Corre sin nube y
  saca la clave del `.env` en texto plano.
- **Autenticación del servicio:** bearer token por nodo (header `Authorization: Bearer <token>`),
  comparado en tiempo constante en una dependencia de FastAPI. Simple y suficiente para
  servicio-a-servicio en el MVP; mTLS queda como endurecimiento posterior.
- **Umbral M-de-N:** multi-firma **nativa del Safe** — la cuenta se crea con `N+1` owners
  (agente + N nodos aval) y threshold `M+1`. El orquestador del agente consulta los N nodos (en
  paralelo, con timeout), reúne M co-firmas de las respuestas ALLOW, combina con la del agente y
  ejecuta. Reusa `combine_signatures` (ordena por owner) tal cual.
- **Tooling:** se mantiene Python 3.11+, `ruff`, `mypy --strict` sobre core/policies/models, `pytest`.

Honra la Constitution (core off-chain agnóstico; el KMS y la auth viven en la capa `execution`,
no en el core). El uso de un servicio de nube (KMS) es una dependencia de *despliegue* del
co-autorizador, no del core — se registra en el decision log.

## Architecture overview

Se generaliza el co-autorizador único de la 002 a **N nodos independientes**, cada uno con su
`Signer` custodiado y su token de auth; y el orquestador del agente pasa de 1 a M co-firmas.

```
Agente: arma SafeTx, firma (1)
   │  pide /authorize (Bearer token) en paralelo a los N nodos
   ▼
┌ nodo aval #i (servicio separado) ───────────────────────────┐
│  auth ✓ → decode → Engine.evaluate (mandato, 001/002)        │
│  ALLOW → Signer.sign_hash (KMS: la clave no sale) → firma     │
└───────────────────────────────────────────────────────────────┘
   │  reúne M firmas ALLOW  (si < M → fail-closed, no ejecuta)
   ▼
combine_signatures([agente, aval_1…aval_M])  →  execTransaction (threshold M+1 alcanzado) → ⛓️
```

`Signer` aísla el "cómo se firma": el `Authorizer` y el resto del flujo no saben si detrás hay un
KMS o un keystore. El orquestador `ThresholdExecutor` generaliza a `SafeTransferExecutor`.

## Data model

- **`Signer`** (ABC): `address: str`, `sign_hash(digest: bytes) -> bytes`.
  - `LocalKeystoreSigner(keystore_json, passphrase)`.
  - `KmsSigner(key_id, kms_client)`: deriva address al construir; `sign_hash` → DER→(r,s), normaliza
    `s` a low-s (EIP-2), recupera `v∈{27,28}` probando cuál recupera la address conocida.
- **`Authorizer`**: pasa de `aval_private_key: str` a `signer: Signer` (su `address` = `signer.address`).
- **Config de nodo co-autorizador:** `{ signer_backend, mandate_registry, auth_token }`.
- **Config del agente:** lista de `CosignerEndpoint{ url, auth_token }` + `threshold_m: int`.
- **`AuthResult` interno del orquestador:** firma + identidad del firmante por nodo, para combinar.
- Sin cambios en `Mandate`, `Decision`, `AuditEntry`, `ProposedAction`.

## External dependencies

- **`boto3`** (extra nuevo `aval[kms]`): cliente AWS KMS (`sign`, `get_public_key`). Solo en `KmsSigner`.
- **`eth-keys` / `eth-utils`** (ya presentes): derivación de address y recuperación de `v`.
- Parsing DER mínimo de la firma/pubkey ECDSA: hecho a mano (estructura simple) o con `asn1crypto`
  si conviene; sin dependencia pesada nueva.
- **dev/test:** un *fake* de cliente KMS respaldado por una clave secp256k1 local real (firma como
  firmaría KMS) para ejercitar la conversión DER→r/s/v y la derivación de address **sin cuenta AWS**.
- **Infra que provee el dev (run real):** una cuenta de nube con N claves `ECC_SECG_P256K1` en KMS y
  credenciales; igual que Sepolia, se suma cuando se hace el run real.

## Trade-offs considered

- **AWS KMS vs GCP KMS vs HSM local:** elegido AWS KMS como backend de referencia (mejor documentado
  para secp256k1/Ethereum). Rechazados *por ahora* GCP/HSM, pero la interfaz `Signer` los habilita sin
  tocar el core. Riesgo de lock-in mitigado por la abstracción.
- **KMS real vs solo keystore cifrado:** se construyen **ambos** (KMS para prod, keystore para dev),
  porque el keystore permite correr y testear todo localmente sin nube, y el KMS es el objetivo de
  producción. La conversión de firma KMS se valida con un fake respaldado por crypto real.
- **Bearer token vs mTLS para auth:** elegido bearer token (simple, suficiente service-to-service).
  mTLS rechazado por ahora (más operación de certificados); queda como endurecimiento.
- **Multi-owner nativo del Safe vs MPC/TSS:** elegido nativo (ya decidido en spec): reusa el multisig
  battle-tested y `combine_signatures`. MPC rechazado por complejidad/riesgo.
- **Consultar nodos en paralelo vs secuencial:** paralelo con timeout por nodo — menor latencia y
  tolerancia a un nodo lento/caído; fail-closed si no se juntan M a tiempo. Secuencial rechazado por
  latencia (M·RTT) y peor tolerancia.
- **Evaluación independiente por nodo vs decisión compartida:** independiente (cada nodo corre el
  mandato) — sin confianza compartida; un nodo comprometido no contamina a los demás. Cuesta evaluar
  N veces, aceptable.
- **Recuperación de `v` por prueba vs cálculo directo:** se prueba `v=27/28` y se elige el que recupera
  la address (KMS no devuelve `v`). Es el patrón estándar para firmas de KMS.

## Risks

- **Conversión de la firma de KMS al formato de Ethereum** (DER→r,s; low-s EIP-2; recuperación de `v`):
  es el riesgo técnico principal — un error produce una firma que el Safe rechaza. Mitigación: unit
  tests que verifican que la firma recupera la address derivada, y un test de integración donde un Safe
  real (EVM in-process) **acepta** la firma producida por la ruta KMS (con el fake KMS).
- **Derivación de address desde la pubkey de KMS** (DER SPKI → pubkey sin comprimir → keccak):
  un parseo mal hecho da otra address. Mitigación: test contra una clave conocida.
- **Disponibilidad/latencia de KMS con M llamadas:** mitigación — paralelizar, timeout por nodo,
  fail-closed; documentar el costo por firma.
- **Gestión del token de auth y de la passphrase del keystore:** secretos de despliegue; documentar que
  no van al repo (van por entorno/secretos). El keystore local es solo para dev.
- **Complejidad operativa de N nodos:** mitigación — un solo binario de servicio parametrizable por
  config; documentación de despliegue; los tests cubren N=3/M=2 como caso de referencia.
- **Compatibilidad con la 002:** cambian firmas internas (Authorizer, executor). Mitigación — actualizar
  los tests de la 002 en la misma feature; el contrato de decisión/mandato/audit no cambia.

## Test plan

- **Unit (`tests/unit/`):** `LocalKeystoreSigner` (encrypt/decrypt + firma que recupera a su address);
  `KmsSigner` con fake-KMS respaldado por crypto real (derivación de address, DER→r/s/v, low-s,
  recuperación de `v`, firma recuperable); dependencia de auth (token válido/ inválido/ausente);
  lógica de umbral del orquestador (junta M, falla con M-1, ignora un nodo caído) con cosigners mockeados.
  `mypy --strict` verde sobre core/policies/models.
- **Integration (`tests/integration/`):** servicio endurecido por HTTP — 401 sin token, 200 con token;
  flujo M-de-N con N nodos (cada uno `TestClient`) reuniendo M firmas; un nodo que deniega o está caído
  con ≥ M restantes → igual reúne M.
- **E2E (`tests/e2e/`, EVM in-process):** Safe con `N+1` owners y threshold `M+1`; el orquestador reúne
  agente + M co-firmas y `execTransaction` **ejecuta**; con solo M-1 co-firmas **revierte** (prueba la
  no-evitabilidad del umbral). Variante con `KmsSigner` (fake) para validar que la firma estilo-KMS es
  aceptada on-chain.
- **E2E real (detrás de flag, requiere infra):** nodos con AWS KMS real sobre Sepolia. Salteado sin credenciales.
