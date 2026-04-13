const MODULE_ID = "supervisor.main";

const running = new Map();
const taskTimeouts = new Map();
const processedTasks = new Set();
const taskLifecycle = new Map();

const VALID_TRANSITIONS = {
  awaiting_approval: ["running", "error"],
  running: ["awaiting_approval", "verifying", "completed", "timeout_soft", "timeout_hard", "error"],
  verifying: ["completed", "error"],
  completed: [],
  error: [],
  timeout_soft: ["completed", "error"],
  timeout_hard: []
};

const ACTION_TIMEOUTS = {
  "ai.query": 30000,
  "ai.analyze_intent": 15000,
  "ai.generate_code": 30000,
  "ai.explain_error": 20000,
  "ai.analyze_project": 35000,
  "open_application": 30000,
  "terminal.write_command": 10000,
  "browser.open_url": 8000,
  "browser.search": 10000,
  "system.search_file": 5000,
  "monitor_resources": 5000,
  "default": 15000
};

function now() {
  return Date.now();
}

function safeIsoNow() {
  return new Date().toISOString();
}

function generateTraceId() {
  return `sv_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

function emit(port, payload = {}) {
  const traceId = payload?.trace_id || generateTraceId();
  const meta = payload?.meta || {
    source: "internal",
    timestamp: safeIsoNow(),
    module: MODULE_ID
  };

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

function mergeMeta(topMeta = {}, payloadMeta = {}) {
  return {
    ...(topMeta || {}),
    ...(payloadMeta || {})
  };
}

function taskKey(payload = {}, meta = {}) {
  return payload?.task_id || payload?.plan_id || payload?.command_id || meta?.task_id || meta?.plan_id || null;
}

function buildMeta(payload = {}, envelopeMeta = {}) {
  const merged = mergeMeta(envelopeMeta, payload?.meta || {});
  return {
    ...merged,
    source: payload?.source || merged?.source || null,
    chat_id: payload?.chat_id || merged?.chat_id || null,
    task_id: payload?.task_id || payload?.plan_id || merged?.task_id || merged?.plan_id || null,
    plan_id: payload?.plan_id || payload?.task_id || merged?.plan_id || merged?.task_id || null,
    module: MODULE_ID,
    timestamp: safeIsoNow()
  };
}

function canTransition(fromStatus, toStatus) {
  const validTargets = VALID_TRANSITIONS[fromStatus] || [];
  return validTargets.includes(toStatus);
}

function transitionTask(taskId, newStatus, context = {}, traceId = null, meta = {}) {
  const lifecycle = taskLifecycle.get(taskId);

  if (!lifecycle) {
    taskLifecycle.set(taskId, {
      status: newStatus,
      history: [{ from: null, to: newStatus, at: now(), context }],
      created_at: now(),
      updated_at: now()
    });
    return { success: true, transition: { from: null, to: newStatus } };
  }

  const currentStatus = lifecycle.status;

  if (currentStatus === newStatus) {
    return { success: false, reason: "already_in_state" };
  }

  if (!canTransition(currentStatus, newStatus)) {
    emit("event.out", {
      level: "error",
      type: "supervisor_invalid_transition_blocked",
      task_id: taskId,
      from: currentStatus,
      to: newStatus,
      valid_transitions: VALID_TRANSITIONS[currentStatus] || [],
      message: `Invalid transition: ${currentStatus} → ${newStatus}`,
      trace_id: traceId || generateTraceId(),
      meta
    });
    return { success: false, reason: "invalid_transition" };
  }

  lifecycle.history.push({
    from: currentStatus,
    to: newStatus,
    at: now(),
    context
  });
  lifecycle.status = newStatus;
  lifecycle.updated_at = now();

  emit("event.out", {
    level: "debug",
    type: "supervisor_task_transition",
    task_id: taskId,
    from: currentStatus,
    to: newStatus,
    history_count: lifecycle.history.length,
    trace_id: traceId || generateTraceId(),
    meta
  });

  return { success: true, transition: { from: currentStatus, to: newStatus } };
}

function getTimeoutForAction(action) {
  return ACTION_TIMEOUTS[action] || ACTION_TIMEOUTS.default;
}

function clearTaskTimeout(taskId) {
  const timer = taskTimeouts.get(taskId);
  if (timer) {
    clearTimeout(timer);
    taskTimeouts.delete(taskId);
  }
}

function completeTask(taskId) {
  clearTaskTimeout(taskId);
  running.delete(taskId);
}

function emitFinalResult(taskId, status, meta = {}, extra = {}, traceId = null) {
  emit("result.out", {
    task_id: taskId,
    plan_id: taskId,
    status,
    meta,
    trace_id: traceId || generateTraceId(),
    ...extra
  });
}

function startTask(taskId, meta = {}, action = null, isResume = false, traceId = null) {
  if (!taskId) return;

  clearTaskTimeout(taskId);

  const timeoutMs = getTimeoutForAction(action);
  const finalTraceId = traceId || generateTraceId();

  const timer = setTimeout(() => {
    transitionTask(
      taskId,
      "timeout_hard",
      { timeout_ms: timeoutMs },
      finalTraceId,
      meta
    );

    emit("event.out", {
      level: "error",
      type: "supervisor_task_timeout",
      task_id: taskId,
      status: "timeout",
      timeout_ms: timeoutMs,
      meta,
      trace_id: finalTraceId
    });

    emitFinalResult(taskId, "timeout", meta, {
      error: "Task timeout",
      timeout_ms: timeoutMs
    }, finalTraceId);

    completeTask(taskId);
  }, timeoutMs);

  taskTimeouts.set(taskId, timer);

  emit("event.out", {
    level: "info",
    type: isResume ? "supervisor_task_resumed" : "supervisor_task_started",
    task_id: taskId,
    status: "running",
    timeout_ms: timeoutMs,
    meta,
    is_resume: isResume,
    trace_id: finalTraceId
  });
}

function startTracking(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const meta = buildMeta(payload, envelopeMeta);
  const key = taskKey(payload, meta);
  const traceId = incomingTraceId || generateTraceId();

  if (!key) {
    emit("event.out", {
      level: "error",
      type: "supervisor_invalid_plan_ignored",
      message: "plan.in sin task_id, plan_id ni command_id",
      payload,
      trace_id: traceId,
      meta
    });
    return;
  }

  const existing = running.get(key);
  if (existing) {
    emit("event.out", {
      level: "warn",
      type: "supervisor_task_duplicate_start_blocked",
      task_id: key,
      message: "Task already tracked, ignoring duplicate plan.in",
      trace_id: traceId,
      meta
    });
    return;
  }

  const firstAction =
    Array.isArray(payload?.steps) && payload.steps.length > 0
      ? payload.steps[0]?.action || null
      : null;

  running.set(key, {
    started_at: now(),
    source: meta.source,
    chat_id: meta.chat_id,
    status: "running",
    last_update: now(),
    action: firstAction,
    payload,
    trace_id: traceId,
    meta
  });

  transitionTask(
    key,
    "running",
    {
      source: meta.source,
      chat_id: meta.chat_id,
      action: firstAction
    },
    traceId,
    meta
  );

  startTask(key, meta, firstAction, false, traceId);
}

function touchTracking(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const meta = buildMeta(payload, envelopeMeta);
  const key = taskKey(payload, meta);
  if (!key || !running.has(key)) return;

  const item = running.get(key);
  const prevStatus = item.status;
  const traceId = incomingTraceId || item.trace_id || generateTraceId();
  const effectiveMeta = {
    ...item.meta,
    ...meta
  };

  if (payload?.type === "approval_requested") {
    const transition = transitionTask(
      key,
      "awaiting_approval",
      {
        source: item.source || null,
        chat_id: item.chat_id || null
      },
      traceId,
      effectiveMeta
    );

    if (transition.success || transition.reason === "already_in_state") {
      item.status = "awaiting_approval";
      item.last_update = now();
      item.meta = effectiveMeta;
      running.set(key, item);
      clearTaskTimeout(key);
    }
  } else if (payload?.type === "approval_approved") {
    if (item.status === "running") {
      item.last_update = now();
      item.meta = effectiveMeta;
      running.set(key, item);

      startTask(
        key,
        effectiveMeta,
        item.action || null,
        true,
        traceId
      );
    } else {
      const transition = transitionTask(
        key,
        "running",
        {
          source: item.source || null,
          chat_id: item.chat_id || null
        },
        traceId,
        effectiveMeta
      );

      if (transition.success || transition.reason === "already_in_state") {
        item.status = "running";
        item.last_update = now();
        item.meta = effectiveMeta;
        running.set(key, item);

        startTask(
          key,
          effectiveMeta,
          item.action || null,
          true,
          traceId
        );
      }
    }
  } else if (payload?.type === "approval_rejected") {
    const transition = transitionTask(
      key,
      "error",
      {
        source: item.source || null,
        chat_id: item.chat_id || null,
        reason: "approval_rejected"
      },
      traceId,
      effectiveMeta
    );

    if (transition.success || transition.reason === "already_in_state") {
      item.status = "error";
      item.last_update = now();
      item.meta = effectiveMeta;
      running.set(key, item);
      completeTask(key);
    }
  } else {
    item.last_update = now();
    item.meta = effectiveMeta;
    running.set(key, item);
  }

  if (item.status !== prevStatus) {
    emit("event.out", {
      level: item.status === "error" ? "error" : "info",
      type: "supervisor_task_status_changed",
      task_id: key,
      previous_status: prevStatus,
      status: item.status,
      meta: effectiveMeta,
      trace_id: traceId
    });
  }
}

function cleanupProcessedTasks() {
  if (processedTasks.size <= 1000) return;

  const iterator = processedTasks.values();
  for (let i = 0; i < 100; i += 1) {
    const oldKey = iterator.next().value;
    if (!oldKey) break;
    processedTasks.delete(oldKey);
  }
}

function handleResult(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const mergedMeta = buildMeta(payload, envelopeMeta);
  const taskId = payload?.task_id || mergedMeta?.task_id;

  if (!taskId) {
    emit("event.out", {
      level: "error",
      type: "supervisor_result_without_task_id",
      message: "result.in sin task_id",
      payload,
      trace_id: incomingTraceId || generateTraceId(),
      meta: mergedMeta
    });
    return;
  }

  const traceId = incomingTraceId || generateTraceId();
  const lifecycle = taskLifecycle.get(taskId);
  const terminalStates = new Set(["completed", "error", "timeout_hard"]);

  if (lifecycle && terminalStates.has(lifecycle.status)) {
    emit("event.out", {
      level: "warn",
      type: "supervisor_late_result_ignored",
      task_id: taskId,
      current_status: lifecycle.status,
      incoming_status: payload?.status || "unknown",
      message: "Late result ignored because task is already in terminal state",
      trace_id: traceId,
      meta: mergedMeta
    });
    return;
  }

  const resultKey = `${taskId}:${payload?.step_id || "final"}`;
  if (processedTasks.has(resultKey)) {
    emit("event.out", {
      level: "warn",
      type: "supervisor_duplicate_result_blocked",
      task_id: taskId,
      message: "Result already processed, ignoring duplicate",
      trace_id: traceId,
      meta: mergedMeta
    });
    return;
  }

  processedTasks.add(resultKey);
  cleanupProcessedTasks();

  const tracked = running.get(taskId);
  const meta = {
    ...(tracked?.meta || {}),
    ...mergedMeta,
    source: mergedMeta?.source || tracked?.source || null,
    chat_id: mergedMeta?.chat_id || tracked?.chat_id || null,
    module: MODULE_ID,
    timestamp: safeIsoNow()
  };

  const verification = payload?.result?._verification || payload?.verification;
  const hasVerification = !!verification;

  if (hasVerification) {
    const confidence = verification.confidence || 0;
    const executiveState = verification.executive_state || "unknown";
    const classification = verification.classification || {};

    const eventMap = {
      success_verified: "supervisor_task_verified",
      success_high_confidence: "supervisor_task_high_confidence",
      success_partial: "supervisor_task_partial",
      success_weak: "supervisor_task_weak",
      success_unverified: "supervisor_task_unverified",
      error_confirmed: "supervisor_task_failed_verified",
      error_timeout: "supervisor_task_timeout"
    };

    const eventType = eventMap[executiveState] || "supervisor_task_unknown";
    const level = executiveState.startsWith("success") ? "info" : "error";

    const transition = transitionTask(
      taskId,
      level === "info" ? "completed" : "error",
      {
        confidence,
        executive_state: executiveState
      },
      traceId,
      meta
    );

    if (transition.success) {
      emit("event.out", {
        level,
        type: eventType,
        task_id: taskId,
        status: executiveState,
        confidence,
        user_message: classification.user_message,
        evidence_summary: verification.level,
        meta,
        trace_id: traceId
      });

      emitFinalResult(taskId, payload.status, meta, {
        result: payload.result,
        verification: {
          confidence,
          executive_state: executiveState,
          level: verification.level
        }
      }, traceId);

      completeTask(taskId);
    }

    return;
  }

  if (payload.status === "success") {
    const transition = transitionTask(taskId, "completed", { status: "success" }, traceId, meta);
    if (transition.success) {
      emit("event.out", {
        level: "info",
        type: "supervisor_task_success",
        task_id: taskId,
        status: "success",
        meta,
        trace_id: traceId
      });

      emitFinalResult(taskId, "success", meta, {
        result: payload.result
      }, traceId);

      completeTask(taskId);
    }
    return;
  }

  if (payload.status === "error") {
    const transition = transitionTask(taskId, "error", { status: "error" }, traceId, meta);
    if (transition.success) {
      emit("event.out", {
        level: "error",
        type: "supervisor_task_error",
        task_id: taskId,
        status: "error",
        meta,
        trace_id: traceId
      });

      emitFinalResult(taskId, "error", meta, {
        error: payload?.error || null,
        result: payload.result
      }, traceId);

      completeTask(taskId);
    }
    return;
  }

  if (payload.status === "timeout") {
    const transition = transitionTask(taskId, "timeout_hard", { status: "timeout" }, traceId, meta);
    if (transition.success) {
      emit("event.out", {
        level: "error",
        type: "supervisor_task_timeout",
        task_id: taskId,
        status: "timeout",
        meta,
        trace_id: traceId
      });

      emitFinalResult(taskId, "timeout", meta, {
        error: payload?.error || "Task timeout",
        timeout_ms: payload?.timeout_ms || null,
        result: payload.result
      }, traceId);

      completeTask(taskId);
    }
    return;
  }

  emit("event.out", {
    level: "warn",
    type: "supervisor_unknown_result_status",
    task_id: taskId,
    status: payload?.status || null,
    meta,
    trace_id: traceId
  });
}

process.stdin.setEncoding("utf8");

let buffer = "";
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  const lines = buffer.split("\n");
  buffer = lines.pop();

  for (const line of lines) {
    if (!line.trim()) continue;

    try {
      const msg = JSON.parse(line);
      const { port, payload = {} } = msg;
      const envelopeMeta = msg?.meta || {};
      const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();

      if (port === "plan.in") {
        startTracking(payload, envelopeMeta, traceId);
      } else if (port === "event.in") {
        touchTracking(payload, envelopeMeta, traceId);
      } else if (port === "result.in") {
        handleResult(payload, envelopeMeta, traceId);
      }
    } catch (err) {
      emit("event.out", {
        level: "error",
        type: "supervisor_parse_error",
        error: String(err),
        trace_id: generateTraceId(),
        meta: {
          source: "internal",
          module: MODULE_ID,
          timestamp: safeIsoNow()
        }
      });
    }
  }
});