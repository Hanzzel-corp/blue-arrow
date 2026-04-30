# Architecture

> 🌐 [Versión en Español → ARCHITECTURE.md](ARCHITECTURE.md)

## Overview

The system follows a modular process-based architecture:

- `runtime` (Node.js) discovers modules and routes messages
- Each module runs in its own process
- Communication contracts via ports + JSON Lines
- Topology declared in `blueprints/system.v0.json`

## Components

- `runtime/main.js`: Startup, module validation, bus bootstrap
- `runtime/registry.js`: Discovery of `manifest.json`
- `runtime/bus.js`: Port connections between modules
- `runtime/transforms.js`: Message normalization between modules

## Blueprint

`blueprints/system.v0.json` defines:
- `modules`: Modules that must exist and start
- `connections`: Wiring from `moduleA:port.out` to `moduleB:port.in`

This definition avoids coupling through direct imports.

## Message Contract (v2)

General format emitted by modules:

```json
{
  "module": "module.id",
  "port": "event.out",
  "trace_id": "uuid-trace-123",
  "meta": {
    "source": "cli|telegram|internal",
    "timestamp": "2026-01-01T00:00:00Z",
    "chat_id": 123456789,
    "task_id": "task_123"
  },
  "payload": {}
}
```

**⚠️ RULE**: `trace_id` and `meta` must be at the **top level**, NOT inside the payload.

Recommendations:
- Ports with clear semantics (`command.in`, `result.out`, `event.out`)
- `trace_id` mandatory for complete traceability
- `meta.source`, `meta.timestamp` mandatory
- Avoid implicit undocumented fields

## Main Flow

```
interface -> planner -> agent -> safety/approval -> router -> workers
                                     \-> supervisor (closes task)
workers:result.out -> verifier -> supervisor (close with verification)
workers:result.out -> memory/ui/interface (observation, doesn't close)
```

**Single closure pattern**: `supervisor.main` is the only module with authority to close tasks. Workers inform, observers listen.

## Workers

- `worker.python.desktop`: Application and terminal actions
- `worker.python.system`: Resources and filesystem searches
- `worker.python.browser`: Web navigation/actions via Playwright

## Module Lifecycle

1. **Discovery**: Runtime scans `modules/` for `manifest.json`
2. **Validation**: Checks required ports and dependencies
3. **Startup**: Spawns module process
4. **Connection**: Wires ports according to blueprint
5. **Execution**: Routes messages through the bus
6. **Shutdown**: Graceful termination on SIGINT/SIGTERM

## Resilience Features

| Feature | Description |
|---------|-------------|
| **Graceful Shutdown** | Ordered module shutdown on SIGINT/SIGTERM |
| **Auto-restart** | Automatic restart with backoff (max 3 attempts) |
| **Backpressure** | Flow control to prevent OOM in buffers |
| **Circuit Breaker** | Protection against persistent failure patterns |
| **Health Checks** | Resource, dependency and module monitoring |
| **Contract Versioning** | Semantic versioning of message contracts |

## Tier Classification

### Core Tier (🔴)
Modules whose failure brings down or critically degrades the system:
- `interface.*` - User interfaces
- `planner.main` - Task planning
- `agent.main` - Intent interpretation
- `safety.guard.main` - Safety validation
- `router.main` - Action routing
- `supervisor.main` - Task lifecycle
- `worker.*` - Execution workers
- `memory.*` - Persistence

### Satellite Tier (🛰️)
Modules whose failure reduces features but keeps main flow intact:
- `gamification.main` - RPG features
- `ai.assistant.main` - AI conversation
- `verifier.engine.main` - Post-execution verification
- `phase.engine.main` - State machine (in transition)

## Execution Profiles

### Minimal
Only essential for headless operation:
```json
["interface.main", "planner.main", "agent.main", "safety.guard.main",
 "router.main", "supervisor.main", "worker.python.*", "memory.log.main"]
```

### Standard
Daily use with UI:
```json
[...minimal, "interface.telegram", "approval.main", "ui.state.main"]
```

### Full
Complete experience with AI and gamification:
```json
[...standard, "gamification.main", "ai.*", "telegram.menu.main",
 "guide.main", "phase.engine.main", "verifier.engine.main"]
```

## Persistence

State persistence in `logs/`:
- Session memory
- Event traces
- UI state and app sessions
- Gamification progress

## Design Decisions

- No cross-imports between domain modules
- Integration via declared ports
- Centralized orchestration in runtime
- Extensibility through new modules/manifests and wiring in blueprint

## State-Driven Migration

The system is transitioning from token-based to state-driven:

```
Token-based:              State-driven:
text → tokens → intent    signal → state → transition
     ↓                           ↓
  action                    action → new_state → verify
```

**Key difference**: Instead of interpreting ambiguous text, the system processes structured signals in state context (deterministic, verifiable).

See [PHASE_ENGINE_SUMMARY.md](PHASE_ENGINE_SUMMARY.md) for transition status.

---

For development setup, see [DEVELOPMENT_EN.md](DEVELOPMENT_EN.md)  
For message contracts, see [PORT_CONTRACTS.md](PORT_CONTRACTS.md)
