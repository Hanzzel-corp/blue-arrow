/**
 * ⚠️ CONCEPTUAL EXAMPLES ONLY
 *
 * These examples illustrate the target state-driven / signal-based model.
 * They do NOT necessarily match 1:1 the current canonical action names,
 * port names, or runtime wiring used in the operational documentation.
 *
 * Action names used here (e.g. `desktop.launch`, `browser.open`) are also illustrative
 * and may differ from the current canonical action naming.
 *
 * Use them as conceptual reference for transitions, phases and signals.
 * For current canonical contracts and action naming, see:
 * - PORT_CONTRACTS.md
 * - TASK_CLOSURE_GOVERNANCE.md
 * - PHASE_ENGINE_SUMMARY.md
 */

/**
 * Phase Engine Integration Examples
 * 
 * This file demonstrates how the new state-based system works
 * with concrete examples for common use cases.
 */

// ============================================================================
// EXAMPLE 1: Open Terminal
// ============================================================================

// BEFORE (Text-based):
// User: "abrir terminal"
// → normalizeText("abrir terminal") → ["abrir", "terminal"]
// → includes("abrir") && includes("terminal") → detect intent
// → build plan with text matching

// AFTER (State-based with Signals):
const example1_terminal = {
  // Step 1: User command arrives as signal
  input_signal: {
    type: "user_command",
    payload: {
      raw_text: "abrir terminal",
      intent: "open_application",
      params: { app_id: "terminal" },
      confidence: 0.95
    },
    meta: {
      source: "agent.main",
      timestamp: "2026-04-06T21:30:00Z",
      correlation_id: "sig_123456"
    }
  },

  // Step 2: Phase Engine processes state transition
  state_transition: {
    from: "idle",
    signal: "user_command",
    to: "intent_detected",
    actions: ["validate_intent"]
  },

  // Step 3: Intent validation (confidence > 0.7)
  validation_result: {
    valid: true,
    confidence: 0.95,
    intent: "open_application"
  },

  // Step 4: Transition to planning
  planning_transition: {
    from: "intent_detected",
    signal: "intent_validated",
    to: "planning",
    actions: ["start_planning"]
  },

  // Step 5: Planner emits structured plan signal
  plan_signal: {
    type: "plan_ready",
    payload: {
      plan_id: "plan_789",
      intent: "open_application",
      steps: [
        {
          action: "desktop.launch",
          target: "terminal",
          params: { command: "gnome-terminal" }
        }
      ],
      risk_level: "low",
      requires_approval: false,
      params: { app_id: "terminal" }
    },
    meta: {
      source: "planner.main",
      timestamp: "2026-04-06T21:30:01Z",
      correlation_id: "sig_789"
    }
  },

  // Step 6: Low risk → auto-approve → executing
  execution_transition: {
    from: "planning",
    signal: "plan_ready",
    condition: "risk_level === 'low'",
    to: "executing",
    actions: ["auto_approve", "proceed_with_execution"]
  },

  // Step 7: Router emits action to worker
  action_signal: {
    type: "worker_action",
    payload: {
      action: "desktop.launch",
      target: "terminal",
      params: { command: "gnome-terminal" }
    },
    meta: {
      source: "router.main",
      timestamp: "2026-04-06T21:30:02Z"
    }
  },

  // Step 8: Worker executes and returns result
  worker_result: {
    type: "worker_result",
    payload: {
      success: true,
      action: "desktop.launch",
      result: { pid: 12345, window_id: "0x1234" }
    },
    meta: {
      source: "worker.python.desktop",
      timestamp: "2026-04-06T21:30:03Z"
    }
  },

  // Step 9: Transition to verifying
  verification_transition: {
    from: "executing",
    signal: "worker_result",
    to: "verifying",
    actions: ["start_verification"]
  },

  // Step 10: Execution Verifier checks result
  verification_signal: {
    type: "verification_complete",
    payload: {
      success: true,
      plan_id: "plan_789",
      verification: {
        process_detected: true,
        window_detected: true,
        verification_method: "process_exists"
      }
    },
    meta: {
      source: "verifier.engine.main",
      timestamp: "2026-04-06T21:30:04Z"
    }
  },

  // Step 11: Success → completed
  completion_transition: {
    from: "verifying",
    signal: "verification_complete",
    condition: "success === true",
    to: "completed",
    actions: ["emit_success", "update_stats"]
  },

  // Step 12: Final success signal
  completion_signal: {
    type: "task_completed",
    payload: {
      plan_id: "plan_789",
      intent: "open_application",
      result: { success: true, app_id: "terminal", window_id: "0x1234" }
    },
    meta: {
      source: "phase.engine.main",
      timestamp: "2026-04-06T21:30:05Z"
    }
  }
};

// ============================================================================
// EXAMPLE 2: Open Browser + Search (Multi-step)
// ============================================================================

const example2_browser_search = {
  // Input: Combined intent with multiple actions
  input_signal: {
    type: "user_command",
    payload: {
      raw_text: "abrir chrome y buscar typescript",
      intent: "open_browser_search",
      params: { 
        browser: "chrome",
        query: "typescript"
      },
      confidence: 0.88
    }
  },

  // Planner generates multi-step plan
  plan_signal: {
    type: "plan_ready",
    payload: {
      plan_id: "plan_790",
      intent: "open_browser_search",
      steps: [
        { action: "browser.open", target: "chrome" },
        { action: "browser.search", query: "typescript" }
      ],
      risk_level: "low",
      requires_approval: false,
      params: { browser: "chrome", query: "typescript" }
    }
  },

  // Execution with multiple steps
  execution_flow: [
    { step: 0, action: "browser.open", status: "success" },
    { step: 1, action: "browser.search", status: "success" }
  ],

  // Verification for each step
  verification_results: [
    { step: 0, verified: true, method: "window_exists" },
    { step: 1, verified: true, method: "url_contains_query" }
  ]
};

// ============================================================================
// EXAMPLE 3: High-Risk Operation with Approval
// ============================================================================

const example3_with_approval = {
  // User requests system-level operation
  input_signal: {
    type: "user_command",
    payload: {
      raw_text: "eliminar archivo system32",
      intent: "file_delete",
      params: { path: "/system32" },
      confidence: 0.92
    }
  },

  // Planner detects high risk
  plan_signal: {
    type: "plan_ready",
    payload: {
      plan_id: "plan_791",
      intent: "file_delete",
      steps: [
        { action: "file.delete", path: "/system32", recursive: true }
      ],
      risk_level: "high",  // ← HIGH RISK
      requires_approval: true,  // ← REQUIRES APPROVAL
      params: { path: "/system32" }
    }
  },

  // Transition: planning → awaiting_approval (not executing)
  approval_transition: {
    from: "planning",
    signal: "plan_ready",
    condition: "risk_level !== 'low'",
    to: "awaiting_approval",
    actions: ["request_approval"]
  },

  // Approval request signal
  approval_request: {
    type: "approval_request",
    payload: {
      plan_id: "plan_791",
      risk_level: "high",
      description: "Eliminar directorio system32",
      consequences: ["system_instability", "data_loss"]
    },
    meta: { source: "approval.main" }
  },

  // User approves
  user_approval: {
    type: "approval",
    payload: {
      plan_id: "plan_791",
      response: "approved",  // or "rejected"
      user_id: 1781005414,
      timestamp: "2026-04-06T21:35:00Z"
    }
  },

  // Transition: awaiting_approval → executing
  execution_transition: {
    from: "awaiting_approval",
    signal: "approval",
    condition: "response === 'approved'",
    to: "executing",
    actions: ["proceed_with_execution"]
  },

  // If rejected:
  rejection_transition: {
    from: "awaiting_approval",
    signal: "approval",
    condition: "response === 'rejected'",
    to: "idle",
    actions: ["clear_context", "notify_cancelled"]
  }
};

// ============================================================================
// EXAMPLE 4: Error and Retry
// ============================================================================

const example4_error_retry = {
  // Initial execution attempt
  execution_attempt: {
    step: 0,
    action: "desktop.launch",
    target: "nonexistent_app"
  },

  // Worker returns error
  error_result: {
    type: "worker_result",
    payload: {
      success: false,
      action: "desktop.launch",
      error: "application_not_found",
      error_details: { app_id: "nonexistent_app" }
    }
  },

  // Transition to verifying (always verify, even on error)
  verification_transition: {
    from: "executing",
    signal: "worker_result",
    to: "verifying",
    actions: ["start_verification"]
  },

  // Verification detects failure
  verification_signal: {
    type: "verification_complete",
    payload: {
      success: false,
      plan_id: "plan_792",
      error: "application_not_found",
      retry_count: 0,
      max_retries: 3
    }
  },

  // Transition: verifying → failed (with retry possibility)
  failure_transition: {
    from: "verifying",
    signal: "verification_complete",
    condition: "success === false && retry_count < max_retries",
    to: "failed",
    actions: ["increment_retry", "retry_planning"]
  },

  // Retry: failed → planning (with updated params)
  retry_planning: {
    type: "plan_ready",
    payload: {
      plan_id: "plan_792_retry_1",
      intent: "open_application",
      steps: [
        { 
          action: "desktop.launch", 
          target: "fallback_app",  // ← Updated with fallback
          params: { fallback: true }
        }
      ],
      retry_count: 1,
      risk_level: "low",
      requires_approval: false
    }
  },

  // Retry loop continues until success or max retries
  final_failure: {
    condition: "retry_count >= max_retries",
    transition: {
      from: "verifying",
      to: "failed",
      actions: ["emit_failure", "clear_context", "suggest_alternatives"]
    },
    failure_signal: {
      type: "task_failed",
      payload: {
        plan_id: "plan_792",
        error: "max_retries_exceeded",
        attempts: 3,
        final_error: "application_not_found"
      }
    }
  }
};

// ============================================================================
// State Machine Diagram
// ============================================================================

/*

┌─────────┐    user_command     ┌─────────────────┐
│  IDLE   │ ──────────────────▶ │ INTENT_DETECTED │
└─────────┘                     └─────────────────┘
     ▲                                    │
     │                                    │ intent_validated
     │                                    ▼
     │                           ┌─────────────────┐
     │                           │    PLANNING     │
     │                           └─────────────────┘
     │                                    │
     │         ┌────────────────────────┼────────────────────────┐
         │         │                        │                        │
     │         │ plan_ready               │ plan_ready             │ plan_ready
     │         │ (risk=low)               │ (risk=medium)          │ (risk=high)
     │         ▼                        ▼                        ▼
     │    ┌─────────┐              ┌─────────────┐          ┌─────────────┐
     └────│EXECUTING│              │AWAITING_APPR│          │AWAITING_APPR│
          └─────────┘              └─────────────┘          └─────────────┘
               │                          │                        │
               │ worker_result            │ approval               │ approval
               ▼                          │ (approved)             │ (rejected)
          ┌─────────┐                    ▼                        ▼
          │VERIFYING│◄────────────────┌─────────┐             ┌─────────┐
          └─────────┘                   │EXECUTING│             │  IDLE   │
               │                      └─────────┘             │ (reset) │
               │ verification_complete  │                    └─────────┘
               │    ┌───────────────────┘
               │    │
               ▼    ▼
          ┌─────────┐     retry < max     ┌─────────┐
          │COMPLETED│◄────────────────────▶│ FAILED  │
          └─────────┘                     └─────────┘
               │                              │
               │                              │ retry >= max
               ▼                              ▼
          [reset state]                   [emit failure]
                                        [clear context]

*/

// ============================================================================
// Export examples for testing
// ============================================================================

module.exports = {
  example1_terminal,
  example2_browser_search,
  example3_with_approval,
  example4_error_retry
};
