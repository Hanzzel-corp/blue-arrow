/**
 * Phase Engine - Observer Mode
 *
 * Versión alineada al runtime real de blueprint-v0.
 * No intenta orquestar ni conducir el flujo principal.
 * Solo observa señales reales del sistema, resume fase y emite state.out/event.out.
 */

import readline from "readline";

const MODULE_ID = "phase.engine.main";
const MAX_HISTORY = 100;

function safeIsoNow() {
  return new Date().toISOString();
}

function buildTopMeta(meta = {}) {
  return {
    source: "internal",
    timestamp: safeIsoNow(),
    module: MODULE_ID,
    ...(meta || {})
  };
}

class StateStore {
  constructor() {
    this.state = {
      version: "1.0",
      timestamp: safeIsoNow(),
      session_id: `sess_${Date.now()}`,
      phase: {
        current: "idle",
        previous: null,
        history: []
      },
      context: {
        task_id: null,
        plan_id: null,
        source: null,
        chat_id: null,
        last_signal_type: null,
        last_signal_payload: null
      },
      memory: {
        session: {
          observed_signals: 0,
          transitions: 0
        }
      }
    };
  }

  getFullState() {
    return JSON.parse(JSON.stringify(this.state));
  }

  getCurrentPhase() {
    return this.state.phase.current;
  }

  updateContext(patch = {}) {
    this.state.context = {
      ...this.state.context,
      ...patch
    };
    this.state.timestamp = safeIsoNow();
  }

  observeSignal(signal) {
    this.state.memory.session.observed_signals += 1;
    this.state.context.last_signal_type = signal?.type || null;
    this.state.context.last_signal_payload = signal?.payload || {};
    this.state.timestamp = safeIsoNow();
  }

  transitionTo(newPhase, signal) {
    const current = this.state.phase.current;

    if (!newPhase || newPhase === current) {
      return null;
    }

    this.state.phase.previous = current;
    this.state.phase.current = newPhase;
    this.state.phase.history.push({
      from: current,
      to: newPhase,
      trigger: signal?.type || "unknown",
      at: safeIsoNow()
    });

    if (this.state.phase.history.length > MAX_HISTORY) {
      this.state.phase.history = this.state.phase.history.slice(-MAX_HISTORY);
    }

    this.state.memory.session.transitions += 1;
    this.state.timestamp = safeIsoNow();

    return { from: current, to: newPhase };
  }

  reset() {
    const fresh = new StateStore();
    this.state = fresh.state;
  }
}

class PhaseEngine {
  constructor() {
    this.stateStore = new StateStore();
  }

  generateTraceId() {
    return `${MODULE_ID}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  emit(port, payload = {}) {
    const traceId = payload?.trace_id || this.generateTraceId();
    const meta = buildTopMeta(payload?.meta || {});
    const { trace_id: _trace, meta: _meta, ...cleanPayload } = payload || {};

    process.stdout.write(
      JSON.stringify({
        module: MODULE_ID,
        port,
        trace_id: traceId,
        meta,
        payload: cleanPayload
      }) + "\n"
    );
  }

  emitEvent(level, text, extra = {}, traceId = null, meta = {}) {
    this.emit(
      "event.out",
      {
        level,
        text,
        timestamp: safeIsoNow(),
        ...extra,
        trace_id: traceId || this.generateTraceId(),
        meta: buildTopMeta(meta)
      }
    );
  }

  emitStateUpdate(reason = "state_updated", traceId = null, meta = {}) {
    this.emit(
      "state.out",
      {
        reason,
        ...this.stateStore.getFullState(),
        trace_id: traceId || this.generateTraceId(),
        meta: buildTopMeta(meta)
      }
    );
  }

  normalizeIncomingSignal(rawPayload, envelopeMeta = {}, incomingTraceId = null) {
    const candidate =
      rawPayload?.signal && typeof rawPayload.signal === "object"
        ? rawPayload.signal
        : rawPayload;

    if (!candidate || typeof candidate !== "object") {
      return null;
    }

    const type = candidate.type;
    if (!type || typeof type !== "string") {
      return null;
    }

    const payload =
      candidate.payload && typeof candidate.payload === "object"
        ? candidate.payload
        : {};

    const signalMeta = {
      ...(envelopeMeta || {}),
      ...((candidate.meta && typeof candidate.meta === "object") ? candidate.meta : {})
    };

    return {
      ...candidate,
      payload,
      meta: signalMeta,
      trace_id: candidate.trace_id || incomingTraceId || this.generateTraceId()
    };
  }

  deriveObservedPhase(signal) {
    const type = signal?.type;
    const payload = signal?.payload || {};

    if (type === "system_reset" || type === "emergency_stop") {
      return "idle";
    }

    if (type === "confirm_required" || type === "approval_requested") {
      return "awaiting_approval";
    }

    if (type === "approved" || type === "approval_response") {
      if (payload.response === "approved" || type === "approved") {
        return "approved";
      }
      if (payload.response === "rejected") {
        return "failed";
      }
    }

    if (type === "blocked" || type === "invalid_plan") {
      return "failed";
    }

    if (type === "planning_request") {
      return "planning";
    }

    if (type === "plan_ready") {
      return "plan_ready";
    }

    if (type === "execute" || type === "router_action_routed") {
      return "executing";
    }

    if (type === "worker_result") {
      if (payload.status === "success") return "verifying";
      if (payload.status === "error") return "failed";
    }

    if (type === "verification_result") {
      if (payload.verified === true) return "completed";
      if (payload.verified === false) return "failed";
    }

    if (type === "timeout") {
      return "failed";
    }

    return null;
  }

  extractContext(signal) {
    const payload = signal?.payload || {};
    const report = payload?.report || {};
    const meta =
      signal?.meta ||
      payload?.meta ||
      report?.meta ||
      payload?.result?.meta ||
      {};

    return {
      task_id: payload?.task_id || meta?.task_id || null,
      plan_id: payload?.plan_id || report?.plan_id || meta?.plan_id || null,
      source: meta?.source || null,
      chat_id: meta?.chat_id || null
    };
  }

  processSignal(signal) {
    const traceId = signal?.trace_id || this.generateTraceId();
    const signalMeta = buildTopMeta(signal?.meta || {});

    this.stateStore.observeSignal(signal);

    const context = this.extractContext(signal);
    this.stateStore.updateContext(context);

    const nextPhase = this.deriveObservedPhase(signal);

    this.emitEvent(
      "debug",
      `Observed signal ${signal.type}`,
      {
        type: "phase_signal_observed",
        signal: signal.type,
        current_phase: this.stateStore.getCurrentPhase(),
        derived_phase: nextPhase
      },
      traceId,
      signalMeta
    );

    if (signal.type === "system_reset") {
      this.stateStore.reset();
      this.emitEvent(
        "info",
        "Phase state reset",
        {
          type: "phase_reset"
        },
        traceId,
        signalMeta
      );
      this.emitStateUpdate("system_reset", traceId, signalMeta);
      return;
    }

    if (!nextPhase) {
      this.emitStateUpdate("signal_observed", traceId, signalMeta);
      return;
    }

    const transition = this.stateStore.transitionTo(nextPhase, signal);

    if (transition) {
      this.emitEvent(
        "info",
        `Observed phase transition: ${transition.from} → ${transition.to}`,
        {
          type: "phase_transition",
          from: transition.from,
          to: transition.to,
          trigger: signal.type
        },
        traceId,
        signalMeta
      );
      this.emitStateUpdate("phase_transition", traceId, signalMeta);
      return;
    }

    this.emitStateUpdate("phase_unchanged", traceId, signalMeta);
  }
}

async function main() {
  const engine = new PhaseEngine();

  engine.emitEvent(
    "info",
    "Phase Engine iniciado en modo observador",
    {
      module: MODULE_ID,
      version: "1.0.0",
      mode: "observer",
      initial_phase: "idle"
    }
  );

  const rl = readline.createInterface({
    input: process.stdin,
    terminal: false,
    crlfDelay: Infinity
  });

  for await (const line of rl) {
    if (!line.trim()) continue;

    try {
      const msg = JSON.parse(line);

      if (msg.port !== "signal.in") {
        continue;
      }

      const incomingTraceId = msg?.trace_id || msg?.payload?.trace_id || engine.generateTraceId();
      const envelopeMeta = msg?.meta || {};
      const signal = engine.normalizeIncomingSignal(msg.payload, envelopeMeta, incomingTraceId);

      if (!signal) {
        engine.emitEvent(
          "warn",
          "Received signal.in without valid signal type",
          {
            type: "phase_invalid_signal"
          },
          incomingTraceId,
          envelopeMeta
        );
        continue;
      }

      engine.processSignal(signal);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);

      if (err instanceof SyntaxError) {
        engine.emitEvent(
          "error",
          `Invalid JSON: ${message}`,
          {
            type: "phase_invalid_json"
          }
        );
      } else {
        engine.emitEvent(
          "error",
          `Processing error: ${message}`,
          {
            type: "phase_processing_error"
          }
        );
      }
    }
  }
}

main().catch((err) => {
  console.error("Fatal error in Phase Engine:", err);
  process.exit(1);
});