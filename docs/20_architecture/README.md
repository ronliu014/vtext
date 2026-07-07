# 20 Architecture

Architecture-level documents describe vtext system design, module boundaries,
API contracts, output contracts, and durable technical decisions.

## Current Documents

- [design.md](./design.md) - overall architecture and module design.
- [architecture.md](./architecture.md) - key architecture decisions and tradeoffs.
- [api.md](./api.md) - REST endpoints, request/response shapes, and SSE events.
- [output-contracts.md](./output-contracts.md) - file layouts and machine-readable
  artifact contracts.

## Layer Responsibility

Use this layer for stable technical contracts and design decisions. Operational
commands and troubleshooting belong in [../60_operations/](../60_operations/).

