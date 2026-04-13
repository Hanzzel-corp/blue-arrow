# Phase Engine Transition Summary

## Overview
This document describes the ongoing transition from text-based parsing to state-driven phase engine architecture in blueprint-v0.

> **Status**: Phase 1 of 4 (Coexistence). Text parsing and signals run in parallel during migration.

## Changes Made

### 1. Design Documentation
- **File**: `docs/PHASE_ENGINE_DESIGN.md`
- **Content**: Complete architecture design including:
  - Global state structure
  - Phase definitions (idle, planning, executing, verifying, completed, failed)
  - Signal type definitions
  - Transition rules
  - Migration strategy

### 2. Agent Module Updates
- **File**: `modules/agent/main.js`
- **Changes**:
  - Added `emitSignal()` function for structured signal emission
  - Added `buildIntentSignal()` for converting commands to signals
  - Signals include: type, payload, meta with correlation_id
  - Maintains backward compatibility with existing command flow

### 3. Planner Module Updates  
- **File**: `modules/planner/main.js`
- **Changes**:
  - Added `emitSignal()` function for plan signals
  - Added `buildPlanSignal()` for emitting structured plan signals
  - Plan signals include: plan_id, intent, steps, risk_level, requires_approval
  - Coexists with existing plan emission during migration

### 4. Blueprint Wiring Updates
- **File**: `blueprints/system.v0.json`
- **Changes**:
  - Added connection: `agent.main:signal.out` → `phase.engine.main:signal.in`
  - Added connection: `planner.main:signal.out` → `phase.engine.main:signal.in`
  - Signal ports integrated with existing phase engine

### 5. Example Implementations
- **File**: `docs/PHASE_ENGINE_EXAMPLES.js`
- **Content**: 4 concrete examples:
  1. Open terminal (simple, low-risk)
  2. Open browser + search (multi-step)
  3. High-risk operation with approval
  4. Error handling with retry

## Architecture Comparison

### Before (Text-Based)
```
text → tokens → intent → plan → execute
```
- normalizeText(), tokenize(), includes() matching
- String parsing and regex
- Ambiguous intent detection
- Language-dependent

### Target State (State-Driven)
```
state + signal → transition → new_state → actions
```
- Structured signals with type/payload/meta
- Deterministic state transitions
- Confidence scoring
- Reduced dependence on language-specific parsing

## Signal Structure

```typescript
{
  type: "user_command" | "plan_ready" | "worker_result" | 
        "verification_complete" | "approval",
  payload: {
    intent?: string;
    params?: Record<string, any>;
    result?: any;
    error?: string;
    confidence?: number;
  },
  meta: {
    source: string;
    timestamp: string;
    correlation_id: string;
  }
}
```

## Phase Definitions

| Phase | Entry Condition | Exit Conditions |
|-------|-----------------|-----------------|
| idle | Initial state | user_command received |
| intent_detected | User command processed | Intent validated |
| planning | Intent validated | Plan generated |
| awaiting_approval | High-risk plan | User approves/rejects |
| executing | Plan approved/LOW risk | Worker completes |
| verifying | Worker result received | Verification complete |
| completed | Verification passed | Reset to idle |
| failed | Verification failed or max retries | Reset or retry |

## Migration Path

### Phase 1: Coexistence ✅ (Current)
- Text parsing continues to work
- Signals emitted in parallel
- No breaking changes

### Phase 2: Signal Integration 🔄 (Next)
- Planner consumes signals from ai-intent
- Phase engine orchestrates flow
- Gradual shift to signal-based

### Phase 3: Text Parsing Removal 📋 (Future)
- Eliminate normalizeText, tokenize
- All modules use signals
- Complete state-driven system

### Phase 4: Full State-Driven 🎯 (Future)
- No string matching anywhere
- 100% deterministic flows
- Full auditability

## Files Modified

1. `docs/PHASE_ENGINE_DESIGN.md` - NEW
2. `docs/PHASE_ENGINE_EXAMPLES.js` - NEW  
3. `modules/agent/main.js` - MODIFIED (added signal functions)
4. `modules/planner/main.js` - MODIFIED (added signal functions)
5. `blueprints/system.v0.json` - MODIFIED (added signal connections)

## Testing Recommendations

1. **Unit Tests**: Test individual signal emission/handling
2. **Integration Tests**: Test full flow: idle → completed
3. **Error Scenarios**: Test retry logic and failure paths
4. **Approval Flows**: Test high-risk operation approvals

## Next Steps

1. Implement signal consumption in phase.engine.main
2. Add state transition handlers
3. Integrate with execution verifier
4. Gradually reduce text parsing dependency
5. Add comprehensive logging for state transitions

## Backward Compatibility

✅ All existing functionality preserved
✅ No breaking changes to existing modules
✅ Text parsing still works during migration
✅ Gradual transition path defined

## Benefits Achieved / Expected

> Some benefits are already visible in Phase 1, while others depend on completing signal consumption and state transition orchestration in `phase.engine.main`.

1. **Determinism**: State + signal = predictable transitions
2. **Auditability**: Every state change logged
3. **Verifiability**: Clear verification points
4. **Extensibility**: Easy to add new states/transitions
5. **Debuggability**: Clear state history and transitions
