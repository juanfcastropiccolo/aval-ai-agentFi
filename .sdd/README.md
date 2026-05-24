# aval — SDD Index

Capa de confianza framework-agnóstica para agentes de IA que manejan dinero (AgentFi).

- **Constitution:** [constitution.md](constitution.md)
- **Design doc (background):** [../docs/superpowers/specs/2026-05-22-aval-design.md](../docs/superpowers/specs/2026-05-22-aval-design.md)

## Features

- [001 — Ejecución permisionada de movimientos de dinero](features/001-permissioned-execution/) — complete (100%)
- [002 — Ejecución real vía co-firma de Safe (agente ADK, transferencias)](features/002-safe-cosigner-execution/) — complete (100%)
- [003 — Co-autorización endurecida: clave custodiada (KMS) y umbral M-de-N](features/003-hardened-cosigner-threshold/) — complete (100%)

## Roadmap / Backlog

Candidatos a features futuras, varios derivados del análisis del doc CT+FP (ver memoria `ctfp-doc-insights`):

- **Fix de concurrencia en `StateStore`** — condición de carrera TOCTOU (parallel-drain): adoptar patrón reserve-on-evaluate / settle-on-execute (`max_concurrency` del CT+FP). _Bug latente del feature 001._
- **Proof Bundles exportables** — evolucionar el audit trail a bundles verificables por terceros (track-record para el allocator; "the bridge is data").
- ~~**Autorizador threshold M-de-N + custodia de clave**~~ → ✅ **feature 003 completa** (multi-owner nativo del Safe + clave en KMS + servicio autenticado).
- **Owner de recuperación con timelock + Guard de deadline on-chain** — feature 005 (mainnet): evitar congelamiento permanente y cerrar duro la ventana de frescura.
- **Mandate como credencial firmada con DIDs** — evolucionar el `Mandate` a un Capability Token portable y firmado (alinea con AP2 / ERC-8004).
- **Settlement hook (Verify+Pay)** — gating de escrow del lado del allocator: liberar fondos solo si el Proof Bundle verifica.
- **Swaps y DeFi** — ampliar selectores y semántica (Uniswap, Aave, Lido) más allá de transferencias.
