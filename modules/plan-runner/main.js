import readline from "readline";

const MODULE_ID = "plan.runner.main";
const STEP_TIMEOUT_MS = 30000;

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const runningPlans = new Map();

function generateTraceId() {
  return `runner_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

function safeIsoNow() {
  return new Date().toISOString();
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

function ensureUrl(raw) {
  const trimmed = String(raw || "").trim();
  if (!trimmed) return trimmed;
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

function buildPlanMeta(plan) {
  return {
    ...(plan.meta || {}),
    source: plan.meta?.source || "unknown",
    chat_id: plan.meta?.chat_id || null,
    module: MODULE_ID,
    timestamp: safeIsoNow()
  };
}

function buildStepMeta(plan, step) {
  return {
    ...buildPlanMeta(plan),
    runner_task_id: plan.task_id,
    task_id: plan.task_id,
    plan_id: plan.task_id,
    step_id: step.step_id,
    planned: true,
    original_command: plan.original_command || "",
    plan_kind: plan.kind || null
  };
}

function armStepTimeout(plan) {
  clearStepTimeout(plan);

  plan.step_timeout = setTimeout(() => {
    const step = plan.steps[plan.current_step_index];
    if (!step) return;

    const traceId = plan.trace_id || generateTraceId();
    const meta = buildPlanMeta(plan);

    emit("event.out", {
      level: "error",
      type: "plan_runner_step_timeout",
      task_id: plan.task_id,
      step_id: step.step_id,
      action: step.action,
      timeout_ms: STEP_TIMEOUT_MS,
      kind: plan.kind,
      meta,
      trace_id: traceId
    });

    emit("event.out", {
      level: "error",
      type: "plan_runner_failed",
      task_id: plan.task_id,
      failed_step_id: step.step_id,
      failed_action: step.action,
      reason: "step_timeout",
      kind: plan.kind,
      meta,
      trace_id: traceId
    });

    emitUiText(
      plan.meta?.chat_id || null,
      `❌ Plan falló por timeout en el paso ${plan.current_step_index + 1}/${plan.steps.length}: ${step.action}`,
      traceId,
      meta
    );

    runningPlans.delete(plan.task_id);
  }, STEP_TIMEOUT_MS);
}

function clearStepTimeout(plan) {
  if (plan?.step_timeout) {
    clearTimeout(plan.step_timeout);
    plan.step_timeout = null;
  }
}

function commandFromStep(step, plan) {
  const meta = buildStepMeta(plan, step);

  if (step.action === "monitor_resources") {
    return {
      port: "command.out",
      payload: {
        command_id: `runner_${plan.task_id}_${step.step_id}`,
        text: "estado sistema",
        source: meta.source,
        chat_id: meta.chat_id,
        meta,
        trace_id: plan.trace_id
      }
    };
  }

  if (step.action === "search_file") {
    const filename = step.params?.filename || "";
    return {
      port: "command.out",
      payload: {
        command_id: `runner_${plan.task_id}_${step.step_id}`,
        text: `Buscar archivo ${filename}`,
        source: meta.source,
        chat_id: meta.chat_id,
        meta,
        trace_id: plan.trace_id
      }
    };
  }

  if (step.action === "open_application") {
    const name = step.params?.name || "";
    const resolvedApp = step.params?.resolved_app || null;

    return {
      port: "command.out",
      payload: {
        command_id: `runner_${plan.task_id}_${step.step_id}`,
        text: `abrir ${resolvedApp?.label || name}`,
        source: meta.source,
        chat_id: meta.chat_id,
        meta: {
          ...meta,
          target_application: resolvedApp?.label || name,
          resolved_application: resolvedApp
        },
        trace_id: plan.trace_id
      }
    };
  }

  if (step.action === "terminal.write_command") {
    const command = step.params?.command || "";
    const activeApp = plan.meta?.active_app || null;
    const resolvedApplication = plan.meta?.resolved_application || null;

    const windowId =
      step.params?.window_id ||
      activeApp?.window_id ||
      resolvedApplication?.window_id ||
      null;

    return {
      port: "command.out",
      payload: {
        command_id: `runner_${plan.task_id}_${step.step_id}`,
        text: `ejecutar en terminal: ${command}`,
        source: meta.source,
        chat_id: meta.chat_id,
        meta: {
          ...meta,
          locked: true,
          resolved_by: "runner.resolved_action",
          resolved_action: {
            action: "terminal.write_command",
            params: {
              command,
              window_id: windowId
            }
          },
          resolved_application: {
            id: "terminal",
            label: "Terminal",
            command: "gnome-terminal",
            source: "/usr/share/applications/org.gnome.Terminal.desktop",
            window_id: windowId
          }
        },
        trace_id: plan.trace_id
      }
    };
  }

  if (step.action === "open_url") {
    const rawUrl = step.params?.url || "";
    return {
      port: "command.out",
      payload: {
        command_id: `runner_${plan.task_id}_${step.step_id}`,
        text: `abrir web ${ensureUrl(rawUrl)}`,
        source: meta.source,
        chat_id: meta.chat_id,
        meta,
        trace_id: plan.trace_id
      }
    };
  }

  if (step.action === "memory_query") {
    return {
      port: "memory.query.out",
      payload: {
        text: step.params?.text || "",
        meta,
        trace_id: plan.trace_id
      }
    };
  }

  return null;
}

function emitUiText(chatId, text, traceId = null, meta = {}) {
  if (!chatId) return;

  emit("ui.response.out", {
    chat_id: chatId,
    mode: "send",
    text,
    inline_keyboard: [],
    trace_id: traceId || generateTraceId(),
    meta: {
      ...meta,
      chat_id: chatId,
      module: MODULE_ID,
      timestamp: safeIsoNow()
    }
  });
}

function executeCurrentStep(plan) {
  const step = plan.steps[plan.current_step_index];
  const traceId = plan.trace_id || generateTraceId();
  const meta = buildPlanMeta(plan);

  if (!step) {
    clearStepTimeout(plan);

    emit("event.out", {
      level: "info",
      type: "plan_runner_completed",
      task_id: plan.task_id,
      step_count: plan.steps.length,
      kind: plan.kind,
      meta,
      trace_id: traceId
    });

    emitUiText(
      plan.meta?.chat_id || null,
      `✅ Plan completado: ${plan.original_command}`,
      traceId,
      meta
    );

    runningPlans.delete(plan.task_id);
    return;
  }

  const mapped = commandFromStep(step, plan);

  if (!mapped) {
    clearStepTimeout(plan);

    emit("event.out", {
      level: "error",
      type: "plan_runner_unknown_step",
      task_id: plan.task_id,
      step_id: step.step_id,
      action: step.action,
      kind: plan.kind,
      meta,
      trace_id: traceId
    });

    emitUiText(
      plan.meta?.chat_id || null,
      `❌ Step no soportado todavía: ${step.action}`,
      traceId,
      meta
    );

    runningPlans.delete(plan.task_id);
    return;
  }

  emit("event.out", {
    level: "info",
    type: "plan_runner_step_started",
    task_id: plan.task_id,
    step_id: step.step_id,
    action: step.action,
    index: plan.current_step_index,
    kind: plan.kind,
    meta,
    trace_id: traceId
  });

  emitUiText(
    plan.meta?.chat_id || null,
    `▶️ Paso ${plan.current_step_index + 1}/${plan.steps.length}: ${step.action}`,
    traceId,
    meta
  );

  armStepTimeout(plan);
  emit(mapped.port, mapped.payload);
}

function handlePlan(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const taskId = payload?.task_id || payload?.plan_id;
  const steps = Array.isArray(payload?.steps) ? payload.steps : [];
  const kind =
    payload?.kind ||
    (steps.length > 1 ? "multi_step" : "single_step_plan");

  if (!taskId || !steps.length) {
    emit("event.out", {
      level: "error",
      type: "plan_runner_invalid_plan",
      payload,
      trace_id: incomingTraceId || generateTraceId(),
      meta: {
        ...mergeMeta(envelopeMeta, payload?.meta || {}),
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
    return;
  }

  const existing = runningPlans.get(taskId);
  if (existing) {
    clearStepTimeout(existing);
    runningPlans.delete(taskId);
  }

  const mergedMeta = mergeMeta(envelopeMeta, payload?.meta || {});
  const traceId = incomingTraceId || generateTraceId();

  const plan = {
    task_id: taskId,
    kind,
    original_command: payload.original_command || "",
    note: payload.note || null,
    steps,
    current_step_index: 0,
    meta: mergedMeta,
    results: [],
    step_timeout: null,
    trace_id: traceId
  };

  runningPlans.set(taskId, plan);

  emit("event.out", {
    level: "info",
    type: "plan_runner_started",
    task_id: taskId,
    step_count: steps.length,
    kind: plan.kind,
    original_command: plan.original_command,
    note: plan.note || null,
    meta: buildPlanMeta(plan),
    trace_id: traceId
  });

  if (plan.note) {
    emitUiText(
      plan.meta?.chat_id || null,
      `🧠 Plan detectado: ${steps.length} paso(s)\n${plan.original_command}\nℹ️ ${plan.note}`,
      traceId,
      buildPlanMeta(plan)
    );
  } else {
    emitUiText(
      plan.meta?.chat_id || null,
      `🧠 Plan detectado: ${steps.length} paso(s)\n${plan.original_command}`,
      traceId,
      buildPlanMeta(plan)
    );
  }

  executeCurrentStep(plan);
}

function findPlanFromPayload(payload = {}, envelopeMeta = {}) {
  const mergedMeta = mergeMeta(envelopeMeta, payload?.meta || {});
  const runnerTaskId =
    mergedMeta?.runner_task_id ||
    mergedMeta?.task_id ||
    payload?.task_id ||
    payload?.plan_id ||
    null;

  if (runnerTaskId && runningPlans.has(runnerTaskId)) {
    return runningPlans.get(runnerTaskId);
  }

  return null;
}

function finalizeStep(plan, payload = {}, incomingTraceId = null) {
  const step = plan.steps[plan.current_step_index];
  if (!step) return;

  clearStepTimeout(plan);

  plan.results.push({
    step_id: step.step_id,
    action: step.action,
    result: payload
  });

  const status = payload?.status || "success";
  const isError = status === "error";
  const traceId = incomingTraceId || plan.trace_id || generateTraceId();
  const meta = buildPlanMeta(plan);

  if (isError) {
    emit("event.out", {
      level: "error",
      type: "plan_runner_step_failed",
      task_id: plan.task_id,
      step_id: step.step_id,
      action: step.action,
      index: plan.current_step_index,
      kind: plan.kind,
      meta,
      trace_id: traceId
    });

    emit("event.out", {
      level: "error",
      type: "plan_runner_failed",
      task_id: plan.task_id,
      step_count: plan.steps.length,
      failed_step_id: step.step_id,
      failed_action: step.action,
      kind: plan.kind,
      meta,
      trace_id: traceId
    });

    emitUiText(
      plan.meta?.chat_id || null,
      `❌ Plan falló en el paso ${plan.current_step_index + 1}/${plan.steps.length}: ${step.action}`,
      traceId,
      meta
    );

    runningPlans.delete(plan.task_id);
    return;
  }

  emit("event.out", {
    level: "info",
    type: "plan_runner_step_finished",
    task_id: plan.task_id,
    step_id: step.step_id,
    action: step.action,
    index: plan.current_step_index,
    kind: plan.kind,
    meta,
    trace_id: traceId
  });

  plan.current_step_index += 1;
  runningPlans.set(plan.task_id, plan);

  executeCurrentStep(plan);
}

function handleResult(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const plan = findPlanFromPayload(payload, envelopeMeta);
  if (!plan) return;
  finalizeStep(plan, payload, incomingTraceId);
}

function handleMemoryResult(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const plan = findPlanFromPayload(payload, envelopeMeta);
  if (!plan) return;
  finalizeStep(plan, payload, incomingTraceId);
}

function handleEvent(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const plan = findPlanFromPayload(payload, envelopeMeta);
  if (!plan) return;

  const traceId = incomingTraceId || plan.trace_id || generateTraceId();
  const meta = buildPlanMeta(plan);

  if (payload?.level === "error") {
    clearStepTimeout(plan);

    const step = plan.steps[plan.current_step_index];

    emit("event.out", {
      level: "error",
      type: "plan_runner_failed_by_event",
      task_id: plan.task_id,
      failed_step_id: step?.step_id || null,
      failed_action: step?.action || null,
      observed_type: payload?.type || null,
      kind: plan.kind,
      meta,
      trace_id: traceId
    });

    emitUiText(
      plan.meta?.chat_id || null,
      `❌ Plan interrumpido por evento de error en ${step?.action || "paso actual"}`,
      traceId,
      meta
    );

    runningPlans.delete(plan.task_id);
    return;
  }

  emit("event.out", {
    level: "debug",
    type: "plan_runner_event_observed",
    task_id: plan.task_id,
    observed_type: payload?.type || null,
    trace_id: traceId,
    meta
  });
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (err) {
    emit("event.out", {
      level: "error",
      type: "plan_runner_parse_error",
      error: String(err),
      trace_id: generateTraceId(),
      meta: {
        source: "internal",
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
    return;
  }

  const payload = msg?.payload || {};
  const envelopeMeta = msg?.meta || {};
  const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();

  if (msg.port === "plan.in") {
    handlePlan(payload, envelopeMeta, traceId);
    return;
  }

  if (msg.port === "result.in") {
    handleResult(payload, envelopeMeta, traceId);
    return;
  }

  if (msg.port === "memory.in") {
    handleMemoryResult(payload, envelopeMeta, traceId);
    return;
  }

  if (msg.port === "event.in") {
    handleEvent(payload, envelopeMeta, traceId);
  }
});