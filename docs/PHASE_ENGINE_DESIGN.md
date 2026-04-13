> **⚠️ DISEÑO OBJETIVO DEL PHASE ENGINE**
>
> Este documento describe el **diseño completo objetivo** del sistema de fases/state machine.
> - NO debe interpretarse como descripción exacta del wiring operativo actual
> - La implementación real está en transición por fases
> - Para el estado actual de coexistencia y migración, ver `PHASE_ENGINE_SUMMARY.md` 
>
> **Rol de este documento**: especificación técnica completa del modelo state-driven, señales, fases y reglas de transición.

# Phase/State Engine Architecture for blueprint-v0

## Overview
Target architecture that will replace text-based parsing with a deterministic state machine:
```
state + signal → transition → new_state → actions
```

## Core Components

### 1. Global State Structure
```json
{
  "version": "1.0",
  "timestamp": "ISO8601",
  "session_id": "sess_<timestamp>",
  "phase": {
    "current": "idle",
    "previous": null,
    "history": []
  },
  "context": {
    "user": { "id", "chat_id", "session_data" },
    "active_app": { "id", "type", "state" },
    "active_web": { "url", "title", "state" },
    "task": { "intent", "params", "plan", "status" }
  },
  "signals": {
    "pending": [],
    "last_processed": null
  },
  "memory": {
    "short_term": {},
    "session": { "commands_count", "success_rate" }
  }
}
```

### 2. Phase Definitions

| Phase | Description | Valid Transitions |
|-------|-------------|-------------------|
| `idle` | Waiting for input | intent_detected |
| `intent_detected` | User command received | planning, awaiting_clarification |
| `planning` | Generating execution plan | plan_ready, error |
| `plan_ready` | Plan created, pending validation | awaiting_approval, executing (auto) |
| `awaiting_approval` | Waiting for user confirmation | executing, cancelled |
| `executing` | Running plan steps | verifying, error, timeout |
| `verifying` | Checking execution results | completed, failed, retry |
| `completed` | Task finished successfully | idle (reset) |
| `failed` | Task failed | retry, abort |

### 3. Signal Types

```typescript
type Signal = {
  type: "user_command" | "worker_result" | "approval" | 
        "timeout" | "error" | "intent_validated" | 
        "plan_ready" | "verification_complete",
  payload: {
    intent?: string;
    params?: Record<string, any>;
    result?: any;
    error?: string;
    confidence?: number;  // 0.0 - 1.0
  },
  meta: {
    source: string;
    timestamp: string;
    correlation_id: string;
  }
}
```

### 4. Transition Rules

```javascript
const TRANSITION_RULES = [
  // Phase: idle
  {
    from: "idle",
    signal: "user_command",
    condition: (signal) => signal.payload.confidence > 0.7,
    to: "intent_detected",
    actions: ["validate_intent", "update_context"]
  },
  {
    from: "idle",
    signal: "user_command",
    condition: (signal) => signal.payload.confidence <= 0.7,
    to: "awaiting_clarification",
    actions: ["request_clarification"]
  },
  
  // Phase: intent_detected
  {
    from: "intent_detected",
    signal: "intent_validated",
    condition: () => true,
    to: "planning",
    actions: ["start_planning"]
  },
  
  // Phase: planning
  {
    from: "planning",
    signal: "plan_ready",
    condition: (signal, state) => signal.payload.plan.risk_level === "low",
    to: "executing",
    actions: ["auto_approve", "proceed_with_execution"]
  },
  {
    from: "planning",
    signal: "plan_ready",
    condition: (signal, state) => signal.payload.plan.risk_level !== "low",
    to: "awaiting_approval",
    actions: ["request_approval"]
  },
  
  // Phase: awaiting_approval
  {
    from: "awaiting_approval",
    signal: "approval",
    condition: (signal) => signal.payload.response === "approved",
    to: "executing",
    actions: ["proceed_with_execution"]
  },
  {
    from: "awaiting_approval",
    signal: "approval",
    condition: (signal) => signal.payload.response === "rejected",
    to: "idle",
    actions: ["clear_context", "notify_cancelled"]
  },
  
  // Phase: executing
  {
    from: "executing",
    signal: "worker_result",
    condition: () => true,
    to: "verifying",
    actions: ["start_verification"]
  },
  {
    from: "executing",
    signal: "timeout",
    condition: () => true,
    to: "failed",
    actions: ["handle_timeout"]
  },
  
  // Phase: verifying
  {
    from: "verifying",
    signal: "verification_complete",
    condition: (signal) => signal.payload.success,
    to: "completed",
    actions: ["emit_success", "update_stats"]
  },
  {
    from: "verifying",
    signal: "verification_complete",
    condition: (signal) => !signal.payload.success && state.context.task.retry_count < 3,
    to: "failed",
    actions: ["increment_retry", "retry_planning"]
  },
  {
    from: "verifying",
    signal: "verification_complete",
    condition: (signal) => !signal.payload.success && state.context.task.retry_count >= 3,
    to: "failed",
    actions: ["emit_failure", "clear_context"]
  },
  
  // Global transitions
  {
    from: "*",
    signal: "system_reset",
    to: "idle",
    actions: ["force_reset"]
  },
  {
    from: "*",
    signal: "emergency_stop",
    to: "idle",
    actions: ["emergency_cleanup"]
  }
];
```

## Migration Strategy

### Phase 1: Coexistence (Current)
- Keep existing text parsing in planner
- Add phase engine as parallel module
- Emit signals alongside existing events

### Phase 2: Signal Integration
- Refactor planner to emit structured signals instead of plans
- Agent consumes signals, not just text
- Phase engine orchestrates flow

### Phase 3: Remove Text Parsing
- Eliminate normalizeText, tokenize from planner
- Intent detection becomes signal generation
- All decisions based on state + signals

### Phase 4: Full State-Driven
- Complete removal of string matching
- All modules communicate via signals
- Deterministic, auditable flow

## Implementation Files

### Modified:
- `modules/agent/main.js` - Consume signals, emit commands
- `modules/planner/main.js` - Generate signals, no tokenization
- `modules/phase-engine/main.js` - Already exists, enhance

### New Ports Required:
- `signal.in` / `signal.out` - Phase engine communication
- `state.in` / `state.out` - State updates

## Example Flow: "abrir terminal"

### Old (Text-Based):
```
text → tokens ["abrir", "terminal"] → 
includes("abrir") && includes("terminal") → 
intent: "open_terminal" → plan → execute
```

### New (State-Based):
```
signal: {
  type: "user_command",
  payload: {
    intent: "open_terminal",  // Generated by ai-intent
    params: { app_id: "terminal" },
    confidence: 0.95
  }
} →
state: idle + signal → transition → intent_detected →
validate → planning → plan_ready → 
risk=low → executing → verifying → completed
```

## Verification Integration

Each phase transition can be verified:
```javascript
{
  from: "executing",
  to: "verifying", 
  verification: {
    type: "worker_result",
    required_signals: ["result.out"],
    timeout_ms: 30000
  }
}
```
