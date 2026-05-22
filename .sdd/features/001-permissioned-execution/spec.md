# Ejecución permisionada de movimientos de dinero

Feature ID: 001
Status: specified
Last updated: 2026-05-22

## Problem

Hoy un desarrollador que construye un agente de IA capaz de mover dinero no tiene forma confiable de acotar lo que el agente puede hacer. Las instrucciones en lenguaje natural ("nunca transfieras más de X") no son enforcement: el agente puede ser persuadido por una inyección en datos que procesa, malinterpretar una herramienta, o simplemente equivocarse — y el costo es capital real perdido. Existen casos documentados de agentes que vaciaron fondos o ejecutaron acciones destructivas porque nada externo al modelo los frenó. El desarrollador necesita una barrera técnica, fuera del razonamiento del agente, que garantice que ninguna acción que mueva dinero se ejecute si viola reglas que él definió explícitamente.

## Users

El **desarrollador del agente** (persona primaria de la Constitution): construye un agente que opera sobre rails de dinero on-chain y quiere integrarlo con su flujo existente para protegerse de que el agente exceda su autoridad. Beneficiario secundario futuro: quien aporta el capital (allocator), que más adelante consumirá el registro auditable que esta feature genera.

## Desired outcome

El desarrollador declara, una sola vez y de forma explícita, las reglas bajo las que su agente puede mover dinero (un "mandato"). A partir de ahí, cada vez que el agente intenta una acción que mueve dinero, esa acción se evalúa contra el mandato *antes* de ejecutarse: si lo respeta, procede; si lo viola, se bloquea con una razón legible; si es sensible pero permitida, se pausa para aprobación humana. Todo queda registrado de forma que no se pueda alterar sin dejar rastro. Integrar esta protección no requiere reescribir la lógica del agente — solo envolverlo.

## Functional requirements

1. **FR-1 — Definición de mandato.** El desarrollador puede declarar un mandato que asocia un agente a un conjunto de reglas, con una fecha de expiración y la indicación de quién otorga la autoridad.
2. **FR-2 — Reglas de gasto.** El mandato soporta límites de monto por transacción y por período (p. ej. diario) por activo.
3. **FR-3 — Allowlists.** El mandato soporta listas blancas de: contratos/destinos invocables, destinatarios de fondos, activos manejables, y tipos de acción permitidos.
4. **FR-4 — Reglas temporales.** El mandato soporta una franja horaria permitida y un límite de cantidad de acciones por período.
5. **FR-5 — Identificación de acciones de dinero.** El sistema reconoce, entre todas las acciones que intenta el agente, cuáles mueven dinero, y extrae de cada una sus parámetros relevantes (activo, monto, destino, tipo de acción, red).
6. **FR-6 — Evaluación default-deny por conjunción.** Una acción de dinero se autoriza solo si pasa todas las reglas aplicables del mandato; si ninguna la autoriza o alguna la rechaza, se deniega.
7. **FR-7 — Tres veredictos.** Cada evaluación produce uno de tres resultados: autorizar, denegar, o escalar a aprobación humana.
8. **FR-8 — Escalamiento a humano.** Cuando una acción se escala, el sistema solicita aprobación a una persona y procede o bloquea según la respuesta; debe existir un mecanismo de aprobación funcional listo para usar sin configuración adicional.
9. **FR-9 — Veredicto explicable.** Todo veredicto incluye una razón legible y la regla específica que lo determinó, y esa razón se devuelve al agente cuando se deniega, para que pueda corregir.
10. **FR-10 — Registro auditable e inalterable.** Cada evaluación se registra en un trail append-only encadenado de modo que alterar o borrar una entrada sea detectable.
11. **FR-11 — Pass-through de acciones no financieras.** Las acciones del agente que no mueven dinero no son afectadas por el sistema y se ejecutan normalmente.
12. **FR-12 — Integración sin reescritura.** El desarrollador puede aplicar el enforcement envolviendo su agente existente, sin modificar la lógica interna del agente.
13. **FR-13 — Revocación y expiración.** Un mandato expirado o revocado hace que toda acción de dinero se deniegue.

## Non-goals

- No custodia llaves ni firma transacciones (no es una wallet ni un signer).
- No mueve dinero por sí mismo; solo autoriza o bloquea.
- No analiza ni intenta detectar prompts maliciosos o la intención del modelo.
- No provee identidad verificable del agente ni reputación/track record (fases posteriores).
- No soporta dinero fiat ni redes que no sean del tipo on-chain objetivo del MVP.
- No publica el registro en un sistema externo ni lo cruza con datos on-chain reales en esta feature (niveles de verificabilidad superiores son hitos posteriores).
- No provee enforcement garantizado fuera del punto de integración del agente (un proxy independiente es fase posterior).

## Edge cases

- **Acción de dinero no parseable:** una acción marcada como financiera cuyos parámetros no pueden resolverse se deniega por defecto (fail-closed), nunca se deja pasar en silencio. Configurable a escalamiento por tipo de acción.
- **Monto exactamente en el límite:** debe definirse si el límite es inclusivo o exclusivo y aplicarse consistentemente.
- **Acumulado que cruza el umbral:** una acción que individualmente respeta el límite por transacción pero que sumada al gasto previo del período lo excede, se deniega.
- **Acción en el filo de la franja horaria:** comportamiento determinístico en los bordes exactos de la ventana temporal.
- **Mandato expirado mientras el agente opera:** la expiración se evalúa al momento de cada acción, no al inicio.
- **Acción hacia un contrato permitido pero con parámetros ofuscados/no reconocidos:** se escala o deniega según configuración, nunca se autoriza a ciegas.
- **Fallo al registrar en el audit trail:** si no se puede dejar rastro, la acción se deniega (registrar es parte del camino crítico).
- **Error inesperado durante la evaluación:** se deniega y se registra el error; nunca resulta en autorización accidental.

## Acceptance criteria

- **AC-1:** Dado un mandato con límite de 5.000 por transacción, cuando el agente intenta una transferencia de 4.000 dentro de las demás reglas, entonces la acción se autoriza y queda una entrada en el audit trail.
- **AC-2:** Dado el mismo mandato, cuando el agente intenta una transferencia de 6.000, entonces la acción se deniega con una razón que indica el límite por transacción excedido, y la transferencia no se ejecuta.
- **AC-3:** Dado un mandato con allowlist de destinatarios, cuando el agente intenta enviar fondos a un destino fuera de la lista, entonces la acción se deniega indicando destino no permitido.
- **AC-4:** Dado un mandato con límite diario de 20.000 y un gasto previo de 18.000 en el día, cuando el agente intenta una transferencia de 4.000, entonces la acción se deniega por exceder el límite del período.
- **AC-5:** Dado un mandato que marca como sensibles las acciones sobre cierto umbral, cuando el agente intenta una acción sobre ese umbral, entonces la acción se escala a aprobación humana y solo procede si la persona aprueba.
- **AC-6:** Dada una acción del agente que no mueve dinero (p. ej. una consulta de información), cuando el agente la ejecuta, entonces el sistema no interfiere y la acción corre normalmente.
- **AC-7:** Dado un audit trail con varias entradas, cuando se altera el contenido de una entrada intermedia, entonces la verificación de integridad de la cadena detecta la manipulación.
- **AC-8:** Dada una acción financiera cuyos parámetros no pueden resolverse, cuando el agente la intenta, entonces se deniega por defecto sin ejecutarse.
- **AC-9:** Dado un mandato expirado, cuando el agente intenta cualquier acción de dinero, entonces se deniega indicando mandato expirado.
- **AC-10:** Dado un agente envuelto con aval, cuando el desarrollador lo integra, entonces no necesita modificar la lógica interna del agente para que el enforcement aplique.

## Integration

> Primera feature del proyecto — sin features previas que integrar.

- Affected existing features: ninguna.
- Shared interfaces touched: define las interfaces base del proyecto (`Mandate`, `ProposedAction`, `Decision`, `PolicyResult`, audit trail, punto de integración del adaptador) que features futuras consumirán.
- Breaking changes: n/a.

## Open questions

_(ninguna pendiente — todo resuelto en la sesión de brainstorming)_
