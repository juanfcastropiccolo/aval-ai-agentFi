# Project Constitution — aval

> Immutable-ish principles that govern how this project is built. Changes require a decision log entry.

## Purpose

aval es una librería framework-agnóstica que da a los agentes de IA una **capa de confianza para manejar dinero**: enforcement de permisos acotados, verificable y auditable. El usuario primario es el **desarrollador del agente**, que la integra para que su agente no pueda exceder un mandato explícito ni ser drenado por prompt injection. El north star: responder, de forma demostrable y portable entre frameworks, *"¿en quién puedo confiar con mi capital?"* — empezando por el lado de la oferta (devs) y habilitando después la demanda (allocators).

## Core principles

1. **Default-deny, siempre fail-closed** — ante cualquier ambigüedad, error o acción no resoluble, se deniega. *Por qué:* en finanzas un falso permiso cuesta dinero real; un falso bloqueo solo cuesta un reintento.
2. **Enforcement externo al razonamiento del LLM** — aval opera en la capa de *acción*, no intenta detectar prompts maliciosos. *Por qué:* el prompt injection es inganable; lo único confiable es bloquear la acción que viola el mandato, sin importar qué convenció al modelo.
3. **Core agnóstico, adaptadores delgados** — toda la lógica de decisión vive en un core sin conocimiento de ningún framework; los frameworks se enganchan con shims que no deciden nada. *Por qué:* es lo que hace la capa universalmente reutilizable y lo que prueban Langfuse/OpenTelemetry como patrón ganador.
4. **Construir sobre estándares, no reinventarlos** — el modelo de datos se alinea a estándares emergentes (mandatos compatibles-AP2, atestaciones EAS, identidad ERC-8004) en vez de inventar formatos propios. *Por qué:* la interoperabilidad es el moat; un formato propietario mata la adopción.
5. **Toda decisión es auditable y explicable** — cada veredicto se registra en un trail append-only encadenado por hash, con razón legible. *Por qué:* el audit trail de hoy es el track record verificable de mañana ("the bridge is data"), y la explicabilidad permite que el agente corrija.
6. **Fricción mínima para el dev** — integrar aval debe ser `pip install` + envolver el agente, sin reescribir su lógica. *Por qué:* el usuario primario es el dev; si la adopción no es trivial, la señal de confianza nunca se genera.
7. **Alcance acotado y honesto** — aval gobierna movimiento de dinero; hace pass-through limpio de todo lo demás. *Por qué:* una capa de seguridad que pretende cubrir todo no cubre nada bien.

## Tech stack

- **Language(s):** Python 3.11+
- **Runtime(s):** proceso del agente (in-process, sin servidor en el MVP)
- **Framework(s):** agnóstico por diseño; adaptadores para Google ADK y LangChain/LangGraph
- **Database(s):** ninguna en el MVP — StateStore in-memory (pluggable a Redis/DB después); audit trail en archivo local encadenado
- **Infrastructure:** ninguna en el MVP; rails objetivo crypto/EVM (decodificación de calldata, anclaje futuro a EAS)

## Code style

- Formatting: `ruff format` (línea 100)
- Linting: `ruff` (con type-checking vía `mypy` en strict para el core)
- Naming: `snake_case` para funciones/módulos, `PascalCase` para clases; nombres de dominio explícitos (`Mandate`, `ProposedAction`, `Decision`, `PolicyResult`)
- File organization: paquete `aval/` con `core/` (resolver, policy engine, audit), `policies/` (una clase por archivo), `adapters/` (uno por framework), `models/` (Pydantic)

## Testing strategy

- **Unit:** lógica de negocio en `core/` y cada política en `policies/` — pytest. Casos borde obligatorios (límite exacto, acumulado cruzando umbral, ventana en el filo, mandato expirado).
- **Integration:** decodificación de calldata real en el Resolver; integridad de la hash chain del audit; adaptadores con agentes de juguete que verifican que DENY bloquea de verdad.
- **E2E:** un agente con un Mandato real ejecutando los 4 escenarios del spec (allow / deny por límite / deny por destino / escalate).
- **Coverage target:** none como número rígido — se testea lo que importa, con el Policy Engine y el Resolver como zonas de cobertura no negociable (es donde se pierde dinero).

## Boundaries — what this project does NOT do

- **No es una wallet ni un signer** — no custodia llaves ni firma transacciones; se integra sobre wallets existentes.
- **No es un rail de pagos** — no mueve dinero; autoriza o bloquea que el agente lo mueva.
- **No detecta prompts maliciosos** — no hace análisis de prompts ni de intención del LLM.
- **No hace identidad ni reputación en el MVP** — esas primitivas (ERC-8004/DID, track record) son fases posteriores.
- **No soporta fiat ni cadenas no-EVM en el MVP.**
- **No incluye signing proxy, servidor MCP, ni enforcement onchain en el MVP** — están en el roadmap, fuera del primer build.

## Decision log

| Date | Decision | Reason | Affected features |
|------|----------|--------|-------------------|
| 2026-05-22 | Wedge = ejecución permisionada in-loop; identidad y reputación a fases posteriores | Valor inmediato para el dev; genera el audit trail que alimenta el track record | 001 |
| 2026-05-22 | Mandato evaluado in-process con esquema compatible-AP2 (no VC firmada ni onchain aún) | MVP rápido y demostrable sin encerrar el diseño futuro | 001 |
| 2026-05-22 | Crypto/EVM primero | Encaja con la tesis AgentFi y con la auditabilidad onchain | 001 |
| 2026-05-22 | Commits manuales — aval nunca corre git add/commit/push | El usuario controla qué entra al historial | n/a |
| 2026-05-23 | Feature 002 = aval como co-firmante no-evitable de un Safe 2-de-2 (off-chain co-signer, fail-closed, Sepolia primero) | Enforcement no-evitable para plata real sin que aval custodie ni mueva fondos | 002 |
| 2026-05-23 | Adoptar del análisis CT+FP: la co-firma como freshness proof (deadline corto + binding al nonce) y reason_codes estructurados; concurrencia (reserve/settle), proof bundles, threshold M-de-N y Mandate-como-token-firmado quedan en roadmap | Cierra la ventana firma↔ejecución y mejora explicabilidad; el resto alinea con la tesis de track-record y estándares (AP2/ERC-8004) | 002, roadmap |
| 2026-05-23 | Feature 003: threshold M-de-N vía multi-owner nativo del Safe; clave de cada co-autorizador en KMS (AWS de referencia) detrás de una abstracción `Signer`; auth por bearer token | Quita el SPOF y la clave en texto plano para acercarse a mainnet; el KMS es dependencia de *despliegue* del co-autorizador, no del core (que sigue agnóstico) | 003 |
