# Ejecución real de transferencias vía co-autorización no-evitable

Feature ID: 002
Status: specified
Last updated: 2026-05-23

## Problem

Hoy aval **decide** (autoriza o bloquea) pero no participa de la ejecución, y su decisión vive en el punto de integración del agente (un callback). Eso tiene dos consecuencias para mover dinero de verdad: (1) el agente no puede *ejecutar* una transferencia cuando se le pide — aval solo opina; y (2) si el agente pudiera invocar al firmante directamente, saltearía a aval por completo. Para confiarle capital a un agente, el desarrollador necesita que **ninguna transferencia pueda ejecutarse sin que aval la haya autorizado** — no como convención, sino como imposibilidad técnica — y que, cuando la autoriza, la transferencia efectivamente se ejecute sobre el riel de dinero.

## Users

El **desarrollador del agente** (persona primaria): quiere montar un agente con el que pueda interactuar en lenguaje natural ("transferí X a Y") y que ejecute transferencias reales, con la garantía de que el agente no puede exceder el mandato ni ser drenado por una inyección, ni siquiera salteándose a aval. Beneficiario secundario: quien aporta el capital, que confía en esa garantía de no-evitabilidad y en el registro que produce.

## Desired outcome

El desarrollador le pide al agente, en lenguaje natural, que transfiera fondos. La acción se evalúa contra el mandato (reusando el enforcement de la feature 001) y: si lo respeta, **se ejecuta on-chain** y el agente devuelve una confirmación; si lo viola, no se ejecuta y el agente explica por qué. La propiedad central: existe una **co-autorización de aval que es precondición técnica de la ejecución** — la cuenta que custodia los fondos requiere tanto la intención del agente como la autorización de aval, de modo que sin aval el dinero no se mueve. aval nunca custodia los fondos ni los mueve por sí mismo: solo co-autoriza.

## Functional requirements

1. **FR-1 — Ejecución real de transferencias.** Una transferencia autorizada (de activo nativo o de un token) se ejecuta efectivamente sobre el riel de dinero y devuelve una referencia de confirmación verificable.
2. **FR-2 — Co-autorización no-evitable.** La autorización de aval es una **precondición técnica** de la ejecución: la cuenta custodia requiere la concurrencia de la intención del agente y la autorización de aval. Sin la autorización de aval, ninguna transferencia puede ejecutarse.
3. **FR-3 — Aislamiento de la autoridad de aval.** La capacidad de aval para co-autorizar reside en un dominio de confianza separado, fuera del alcance del agente. El agente no posee, ni puede obtener, lo necesario para mover fondos por su cuenta.
4. **FR-4 — Evaluación sobre la verdad de fondo.** aval evalúa la operación que *realmente* se va a ejecutar (sus parámetros efectivos), no una descripción que el agente provea. La co-autorización vale solo para esa operación específica.
5. **FR-5 — Autorización fresca y acotada.** La autorización de aval es de corta vigencia y está atada a la operación específica y a su contexto de ejecución, de modo que no pueda reutilizarse para otra operación ni quedar válida indefinidamente (anti-replay y anti-stale).
6. **FR-6 — Interacción en lenguaje natural.** El desarrollador expresa la transferencia en lenguaje natural a un agente, que la traduce en una acción de dinero concreta sometida a la co-autorización.
7. **FR-7 — Reuso del enforcement existente.** La decisión de autorizar/bloquear/escalar usa el mandato y el motor de políticas de la feature 001, sin reimplementarlos.
8. **FR-8 — Veredicto con código y razón.** Cada decisión incluye, además de la razón legible, un **código estructurado** (máquina-legible) que identifica la regla o causa, para que el agente y la analítica puedan actuar sobre él.
9. **FR-9 — Registro de ejecución.** Cada acción (autorizada, bloqueada o escalada) se registra en el audit trail; las autorizadas que se ejecutan registran además su referencia de confirmación on-chain.
10. **FR-10 — Fail-closed ante indisponibilidad.** Si el dominio que co-autoriza está inalcanzable o no autoriza, no ocurre ninguna ejecución (los fondos quedan seguros aunque la operación no avance).
11. **FR-11 — No-doble-ejecución.** Una misma operación autorizada no puede ejecutarse dos veces.

## Non-goals

- **No** cubre swaps ni operaciones DeFi (lending, staking) — son features posteriores.
- **No** opera con valor real de producción en esta feature: el objetivo es un entorno de prueba sin valor (testnet). El paso a valor real con montos mínimos es posterior.
- **No** incluye un mecanismo de recuperación si el co-autorizador se pierde (owner de recuperación / timelock) — para esta feature, fail-closed puro. Recuperación = roadmap de mainnet.
- **No** distribuye la autoridad de co-autorización (esquema threshold M-de-N) — un único co-autorizador en esta feature; el threshold es roadmap.
- **No** maneja operaciones compuestas/por lote: ante un patrón que no se pueda descomponer y evaluar parte por parte, se deniega (fail-closed).
- **No** custodia llaves de producción en almacenamiento endurecido (HSM/KMS) — en testnet alcanza una llave local aislada; endurecer es posterior.
- **No** corrige aún la condición de carrera de acumulados bajo concurrencia (parallel-drain) — registrada en el backlog como ítem propio.

## Edge cases

- **Co-autorizador caído o sin respuesta:** la transferencia no se ejecuta (fail-closed). El agente reporta que no pudo obtener autorización.
- **La operación ejecutada difiere de la descrita por el agente:** la autorización vale solo para la operación efectiva evaluada; una operación distinta no queda autorizada.
- **Mandato que expira/se revoca entre la autorización y la ejecución:** la autorización es de corta vigencia (FR-5); pasado su deadline, deja de ser válida para ejecutar.
- **Reintento o reenvío de una operación ya ejecutada:** no se vuelve a ejecutar (FR-11).
- **Operación por lote con una sub-operación que viola el mandato:** se bloquea la operación completa.
- **Fallo de la ejecución en el riel después de autorizada (p. ej. la transacción revierte):** no constituye una falla de seguridad (no se movieron fondos más allá del costo de red); se registra el resultado.
- **Pérdida de estado del co-autorizador (reinicio):** los acumulados de límites deben sobrevivir reinicios para no resetear los topes (estado persistente).

## Acceptance criteria

- **AC-1:** Dado un agente con un mandato que permite transferir hasta cierto límite a un destino permitido, cuando el desarrollador le pide en lenguaje natural transferir un monto válido a ese destino, entonces la transferencia se ejecuta en el riel, devuelve una referencia de confirmación y queda registrada en el audit trail.
- **AC-2:** Dado el mismo mandato, cuando el desarrollador pide una transferencia que viola una regla (monto, destino, etc.), entonces no se ejecuta ninguna transferencia y el agente comunica la razón y el código de la regla violada.
- **AC-3:** Dada una operación que **no** fue co-autorizada por aval, cuando se intenta ejecutarla directamente sobre la cuenta custodia, entonces la ejecución no es posible (la cuenta requiere técnicamente la autorización de aval).
- **AC-4:** Dado el co-autorizador inalcanzable, cuando el agente intenta una transferencia, entonces no se ejecuta nada (fail-closed) y se reporta la indisponibilidad.
- **AC-5:** Dada una autorización emitida para una operación específica, cuando se intenta usarla para ejecutar una operación distinta, entonces esa otra operación no resulta ejecutable.
- **AC-6:** Dada una autorización ya consumida por una ejecución, cuando se intenta ejecutar la misma operación de nuevo, entonces no se ejecuta una segunda vez.
- **AC-7:** Dada una operación por lote (que el sistema no descompone en esta feature), cuando se evalúa, entonces se bloquea por completo (fail-closed), nunca se autoriza parcialmente.
- **AC-8:** Dado un acumulado de gasto previo registrado, cuando el co-autorizador se reinicia y se intenta una transferencia que excede el límite del período, entonces se deniega (el acumulado sobrevivió al reinicio).
- **AC-9:** Dada cualquier decisión, cuando se produce, entonces incluye un código estructurado además de la razón legible, y la entrada de audit lo refleja.

## Integration

- **Affected existing features:** 001 (Ejecución permisionada). Se reusa el motor de políticas, el modelo de mandato, el resolver de calldata y el audit trail.
- **Shared interfaces touched:**
  - El `Decision` de la 001 gana un **código estructurado** además de la razón (FR-8) — adición compatible.
  - El audit trail registra una **referencia de ejecución** (confirmación on-chain) en las acciones ejecutadas (FR-9) — campo adicional.
  - El resolver de calldata se reusa para decodificar la **operación efectiva** que la cuenta custodia ejecutará (FR-4).
  - Se introduce el concepto de **co-autorización fresca y acotada** (FR-5), que extiende —sin reemplazar— la decisión existente.
- **Breaking changes:** ninguno previsto; las extensiones a `Decision` y al audit son aditivas.

## Open questions

_(ninguna pendiente — decisiones de arquitectura resueltas en brainstorming: co-firmante off-chain, fail-closed puro, testnet primero, alcance solo-transferencias.)_
