# Co-autorización endurecida: clave custodiada y umbral M-de-N

Feature ID: 003
Status: specified
Last updated: 2026-05-23

## Problem

La co-autorización de la feature 002 demostró el enforcement no-evitable, pero para
operar con valor real tiene tres debilidades de producción: (1) la clave con la que
aval firma vive en configuración en texto plano y en el mismo proceso que el resto
del demo, así que quien acceda a ese entorno puede firmar a voluntad; (2) cualquiera
que alcance el punto de co-autorización puede pedir firmas, no hay autenticación del
solicitante; y (3) hay **un único** co-autorizador: si se cae, los fondos quedan
trabados, y si se compromete, se pierde la garantía. Para confiar capital real, la
co-autorización tiene que custodiar su clave de forma que no se exponga, atender solo
a solicitantes autenticados, y **no depender de un único firmante**.

## Users

El **desarrollador del agente** (persona primaria), que ahora quiere desplegar la
capa de co-autorización de forma que resista la pérdida o el compromiso de un nodo y
no exponga la clave de firma. Beneficiario secundario: quien aporta el capital, cuya
confianza depende de que ni un operador interno ni un nodo comprometido puedan, por
sí solos, mover los fondos.

## Desired outcome

La co-autorización deja de ser un único proceso con la clave en texto plano y pasa a
ser **uno o varios co-autorizadores independientes**, cada uno con su clave custodiada
en un backend seguro del que la clave nunca sale, que atienden solo a solicitantes
autenticados. Mover dinero requiere la concurrencia del agente **más M co-autorizaciones
de N** posibles: ningún co-autorizador solo —ni comprometido, ni un operador con acceso
a uno— puede mover fondos, y la caída de alguno no congela la operación mientras queden
al menos M disponibles. Todo el enforcement de las features 001/002 (mandato, fail-closed,
frescura, audit) se mantiene intacto.

## Functional requirements

1. **FR-1 — Clave custodiada.** La clave de firma de cada co-autorizador reside en un
   backend de gestión de claves; **no aparece en texto plano** en configuración, logs ni
   en el proceso del agente, y la firma se produce **sin que la clave salga del backend**.
2. **FR-2 — Backend de claves intercambiable.** El mecanismo de firma está detrás de una
   abstracción; se soporta al menos un backend de producción seguro y una opción local
   cifrada para desarrollo, intercambiables sin tocar la lógica de decisión.
3. **FR-3 — Co-autorizador como servicio independiente.** Cada co-autorizador corre como
   un servicio separado, fuera del proceso del agente.
4. **FR-4 — Autenticación del solicitante.** El co-autorizador atiende solo a solicitantes
   autenticados; una solicitud sin credencial válida se rechaza sin evaluar ni firmar.
5. **FR-5 — Umbral M-de-N.** El sistema soporta N co-autorizadores independientes; una acción
   de dinero se ejecuta solo con la concurrencia del agente **más M co-autorizaciones**.
6. **FR-6 — Evaluación independiente.** Cada co-autorizador evalúa el mandato por su cuenta;
   no confía ni delega en la decisión de otro.
7. **FR-7 — Fail-closed por umbral.** Si menos de M co-autorizadores autorizan o están
   disponibles, ninguna acción se ejecuta. Comprometer menos de M co-autorizadores no
   permite mover fondos.
8. **FR-8 — Tolerancia a fallos.** Mientras queden al menos M co-autorizadores disponibles,
   una acción válida se ejecuta aunque otros estén caídos.
9. **FR-9 — Observabilidad.** Cada co-autorizador registra sus decisiones de forma observable,
   sin exponer la clave ni secretos.
10. **FR-10 — Continuidad del enforcement.** Cada co-autorización sigue respetando el mandato,
    el fail-closed, la frescura y el audit trail de las features 001/002.

## Non-goals

- **No** usa firma conjunta criptográfica (MPC/TSS): el umbral se logra con la multi-firma
  nativa de la cuenta custodia (varios owners, umbral M+1).
- **No** incluye recuperación ante pérdida de claves ni timelock (feature posterior).
- **No** incluye rotación automática de claves ni revocación de un co-autorizador en caliente
  (futuro).
- **No** resuelve gestión multi-organización / multi-mandato a escala (futuro).
- **No** fija la red: se sigue validando primero en entorno de prueba; la red es decisión de
  despliegue.

## Edge cases

- **Un co-autorizador caído con ≥ M disponibles:** la acción válida se ejecuta igual.
- **Menos de M disponibles:** fail-closed, no se ejecuta nada.
- **Un co-autorizador comprometido que firma una acción fuera del mandato:** su firma sola no
  alcanza el umbral; los M honestos no la autorizan.
- **Solicitante no autenticado:** rechazado antes de evaluar o firmar.
- **Backend de claves no disponible:** el co-autorizador no puede firmar → no autoriza →
  fail-closed.
- **Timeout/latencia de un co-autorizador:** se trata como no disponible (no bloquea
  indefinidamente).
- **Firma del backend en formato no estándar:** se normaliza al formato que la cuenta custodia
  exige, o la ejecución falla sin mover fondos (nunca una firma inválida aceptada).
- **Discrepancia entre co-autorizadores:** si no se reúnen M autorizaciones, no se ejecuta.

## Acceptance criteria

- **AC-1:** Dada una configuración de N co-autorizadores con umbral M, cuando una acción válida
  reúne el agente + M co-autorizaciones, entonces se ejecuta.
- **AC-2:** Dada la misma configuración, cuando solo se reúnen M-1 co-autorizaciones, entonces
  la acción **no** se ejecuta.
- **AC-3:** Dado un co-autorizador, cuando recibe una solicitud sin credencial válida, entonces
  la rechaza sin evaluar ni firmar.
- **AC-4:** Dada la operación normal, entonces la clave de firma nunca aparece en texto plano en
  configuración ni en logs, y la firma se produce vía el backend seguro.
- **AC-5:** Dado un co-autorizador comprometido que intenta autorizar una acción que viola el
  mandato, cuando se evalúa con umbral M (M honestos), entonces la acción no se ejecuta.
- **AC-6:** Dado un co-autorizador caído pero ≥ M disponibles, cuando se intenta una acción
  válida, entonces se ejecuta.
- **AC-7:** Dada una firma producida por el backend de claves, cuando se verifica, entonces
  recupera correctamente la identidad del co-autorizador y es válida para la cuenta custodia.
- **AC-8:** Dada cualquier decisión, entonces queda registrada de forma observable sin exponer
  la clave ni secretos.

## Integration

- **Affected existing features:** 002 (co-autorización) y, transitivamente, 001 (core).
- **Shared interfaces touched:**
  - El componente que firma (hoy recibe una clave en texto) pasa a usar una **abstracción de
    firma** con backend custodiado — cambio de interfaz interna del co-autorizador.
  - El servicio de co-autorización gana **autenticación del solicitante**.
  - El lado del agente pasa de consultar **un** co-autorizador a consultar **varios** y reunir M
    co-autorizaciones — cambio en el orquestador de ejecución de la 002.
  - La creación de la cuenta custodia pasa de 2 owners a **N+1 owners con umbral M+1**.
- **Breaking changes:** cambian, internamente, el constructor del co-autorizador (clave → backend
  de firma) y el orquestador del agente (un co-autorizador → lista con umbral). Los tests de la
  002 se actualizan en consecuencia; el contrato de decisión/mandato/audit no cambia.

## Open questions

_(ninguna pendiente — decidido en brainstorming: multi-owner nativo de la cuenta custodia,
backend de claves de producción real, evaluación independiente por nodo, fail-closed por umbral.)_
