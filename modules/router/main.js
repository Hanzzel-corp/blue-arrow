import readline from "readline";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const MODULE_ID = "router.main";
const DEDUPE_WINDOW_MS = 1000;
const DEDUPE_MAX_KEYS = 1000;
const recentTasks = new Map();

function generateTraceId() {
  return `router_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

function stableStringify(value) {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }

  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }

  const keys = Object.keys(value).sort();
  return `{${keys
    .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
    .join(",")}}`;
}

function mergeMeta(topMeta = {}, payloadMeta = {}) {
  return {
    ...(topMeta || {}),
    ...(payloadMeta || {})
  };
}

function cleanupRecentTasks(now = Date.now(), windowMs = DEDUPE_WINDOW_MS) {
  for (const [key, ts] of recentTasks.entries()) {
    if (now - ts >= windowMs) {
      recentTasks.delete(key);
    }
  }

  if (recentTasks.size <= DEDUPE_MAX_KEYS) {
    return;
  }

  const overflow = recentTasks.size - DEDUPE_MAX_KEYS;
  const keys = recentTasks.keys();
  for (let i = 0; i < overflow; i += 1) {
    const next = keys.next();
    if (next.done) break;
    recentTasks.delete(next.value);
  }
}

function shouldSkipTask(action, meta = {}, params = {}, windowMs = DEDUPE_WINDOW_MS) {
  const key = [
    action || "unknown_action",
    meta?.chat_id || "global",
    stableStringify(params || {})
  ].join("::");

  const now = Date.now();
  cleanupRecentTasks(now, windowMs);

  const prev = recentTasks.get(key) || 0;
  if (now - prev < windowMs) {
    return true;
  }

  recentTasks.set(key, now);
  return false;
}

function resolveTaskId(payload = {}, meta = {}) {
  return (
    payload?.task_id ||
    payload?.plan_id ||
    payload?.command_id ||
    payload?.meta?.runner_task_id ||
    payload?.meta?.task_id ||
    meta?.runner_task_id ||
    meta?.task_id ||
    meta?.plan_id ||
    null
  );
}

function buildRouteMeta(payload = {}, envelopeMeta = {}, step = {}, worker = null) {
  const merged = mergeMeta(envelopeMeta, payload?.meta || {});
  const now = safeIsoNow();

  return {
    ...merged,
    action: step?.action || null,
    worker,
    routed_at: now,
    module: MODULE_ID,
    timestamp: now
  };
}

function emitRoute(port, payload, envelopeMeta, step, worker, label, incomingTraceId = null) {
  const meta = buildRouteMeta(payload, envelopeMeta, step, worker);
  const taskId = resolveTaskId(payload, meta);
  const traceId = incomingTraceId || generateTraceId();
  const rawText =
    payload?.text ||
    payload?.params?.text ||
    step?.params?.text ||
    step?.params?.prompt ||
    "";

  emit(port, {
    task_id: taskId,
    plan_id: taskId,
    action: step.action,
    params: step.params || {},
    text: rawText,
    meta,
    trace_id: traceId
  });

  emit("event.out", {
    level: "info",
    type: "router_action_routed",
    text: `Router envió ${step.action} por ${port}`,
    task_id: taskId,
    plan_id: taskId,
    action: step.action,
    route: label,
    worker,
    meta,
    trace_id: traceId
  });
}

function routeToDesktop(payload, envelopeMeta, step, traceId) {
  emitRoute(
    "desktop.action.out",
    payload,
    envelopeMeta,
    step,
    "worker.python.desktop",
    "desktop",
    traceId
  );
}

function routeToTerminal(payload, envelopeMeta, step, traceId) {
  emitRoute(
    "terminal.action.out",
    payload,
    envelopeMeta,
    step,
    "worker.python.terminal",
    "terminal",
    traceId
  );
}

function routeToSystem(payload, envelopeMeta, step, traceId) {
  emitRoute(
    "system.action.out",
    payload,
    envelopeMeta,
    step,
    "worker.python.system",
    "system",
    traceId
  );
}

function routeToBrowser(payload, envelopeMeta, step, traceId) {
  emitRoute(
    "browser.action.out",
    payload,
    envelopeMeta,
    step,
    "worker.python.browser",
    "browser",
    traceId
  );
}

function routeToNative(payload, envelopeMeta, step, traceId) {
  emitRoute(
    "native.action.out",
    payload,
    envelopeMeta,
    step,
    "native",
    "native",
    traceId
  );
}

function routeToAI(payload, envelopeMeta, step, traceId) {
  emitRoute(
    "ai.action.out",
    payload,
    envelopeMeta,
    step,
    "ai.assistant.main",
    "ai",
    traceId
  );
}

function routeToOffice(payload, envelopeMeta, step, traceId) {
  emitRoute(
    "office.action.out",
    payload,
    envelopeMeta,
    step,
    "office.writer.main",
    "office_writer",
    traceId
  );
}

function isTerminalAction(action) {
  return [
    "terminal.write_command",
    "terminal.ensure"
  ].includes(action);
}

function isDesktopAction(action) {
  return [
    "open_application",
    "click",
    "type_text",
    "screenshot",
    "focus_window",
    "echo_text"
  ].includes(action);
}

function isSystemAction(action) {
  return [
    "search_file",
    "move_file",
    "copy_file",
    "read_processes",
    "monitor_resources"
  ].includes(action);
}

function isBrowserAction(action) {
  return [
    "open_url",
    "search_google",
    "fill_form",
    "click_web"
  ].includes(action);
}

function isNativeAction(action) {
  return [
    "fast_capture",
    "low_level_input",
    "process_hook"
  ].includes(action);
}

function isOfficeAction(action) {
  return [
    "office.open_writer",
    "office.write_text",
    "office.writer.generate"
  ].includes(action);
}

function resolveOfficeActionFromText(text = "") {
  const raw = String(text || "").toLowerCase().trim();
  if (!raw) return null;

  const mentionsOffice =
    raw.includes("writer") ||
    raw.includes("libreoffice") ||
    raw.includes("office") ||
    raw.includes("documento");

  if (!mentionsOffice) {
    return null;
  }

  const wantsWriting =
    raw.includes("redact") ||
    raw.includes("escrib") ||
    raw.includes("nota") ||
    raw.includes("carta") ||
    raw.includes("mejor") ||
    raw.includes("texto") ||
    raw.includes("contenido");

  if (wantsWriting) {
    return {
      action: "office.writer.generate",
      params: {
        prompt: text,
        text
      }
    };
  }

  return {
    action: "office.open_writer",
    params: {}
  };
}

function resolveStepFromPayload(payload = {}) {
  const directStep = payload?.steps?.[0] || payload?.step || null;
  if (directStep && typeof directStep === "object") {
    return {
      action: directStep.action,
      params: directStep.params || {}
    };
  }

  if (typeof payload?.action === "string" && payload.action.trim()) {
    return {
      action: payload.action.trim(),
      params: payload?.params || {}
    };
  }

  if (typeof payload?.text === "string" && payload.text.trim()) {
    const officeStep = resolveOfficeActionFromText(payload.text);
    if (officeStep) {
      return officeStep;
    }
  }

  return null;
}

function routePlan(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const step = resolveStepFromPayload(payload);
  const mergedMeta = mergeMeta(envelopeMeta, payload?.meta || {});
  const taskId = resolveTaskId(payload, mergedMeta);
  const traceId = incomingTraceId || generateTraceId();

  if (!step || typeof step !== "object") {
    emit("event.out", {
      level: "error",
      type: "router_invalid_step",
      text: "Router recibió plan sin step válido",
      task_id: taskId,
      plan_id: taskId,
      meta: {
        ...mergedMeta,
        module: MODULE_ID,
        timestamp: safeIsoNow()
      },
      trace_id: traceId
    });
    return;
  }

  if (typeof step.action !== "string" || !step.action.trim()) {
    emit("event.out", {
      level: "error",
      type: "router_invalid_action",
      text: "Router recibió step sin action válida",
      task_id: taskId,
      plan_id: taskId,
      step,
      meta: {
        ...mergedMeta,
        module: MODULE_ID,
        timestamp: safeIsoNow()
      },
      trace_id: traceId
    });
    return;
  }

  if (shouldSkipTask(step.action, mergedMeta, step.params || {})) {
    emit("event.out", {
      level: "info",
      type: "router_duplicate_skipped",
      text: `Router omitió acción duplicada: ${step.action}`,
      task_id: taskId,
      plan_id: taskId,
      action: step.action,
      chat_id: mergedMeta?.chat_id || null,
      meta: {
        ...mergedMeta,
        module: MODULE_ID,
        timestamp: safeIsoNow()
      },
      trace_id: traceId
    });
    return;
  }

  if (isOfficeAction(step.action)) {
    routeToOffice(payload, mergedMeta, step, traceId);
    return;
  }

  if (isTerminalAction(step.action)) {
    routeToTerminal(payload, mergedMeta, step, traceId);
    return;
  }

  if (isDesktopAction(step.action)) {
    routeToDesktop(payload, mergedMeta, step, traceId);
    return;
  }

  if (isSystemAction(step.action)) {
    routeToSystem(payload, mergedMeta, step, traceId);
    return;
  }

  if (isBrowserAction(step.action)) {
    routeToBrowser(payload, mergedMeta, step, traceId);
    return;
  }

  if (isNativeAction(step.action)) {
    routeToNative(payload, mergedMeta, step, traceId);
    return;
  }

  if (step.action.startsWith("ai.")) {
    routeToAI(payload, mergedMeta, step, traceId);
    return;
  }

  emit("event.out", {
    level: "error",
    type: "router_route_not_found",
    text: `No hay capability route para acción: ${step.action}`,
    task_id: taskId,
    plan_id: taskId,
    action: step.action,
    meta: {
      ...mergedMeta,
      module: MODULE_ID,
      timestamp: safeIsoNow()
    },
    trace_id: traceId
  });
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (error) {
    emit("event.out", {
      level: "error",
      type: "router_parse_error",
      text: "Router recibió una línea JSON inválida",
      error: String(error),
      trace_id: generateTraceId(),
      meta: {
        source: "internal",
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
    return;
  }

  if (msg.port !== "plan.in") {
    return;
  }

  try {
    const payload = msg?.payload || {};
    const envelopeMeta = msg?.meta || {};
    const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();
    routePlan(payload, envelopeMeta, traceId);
  } catch (error) {
    const payload = msg?.payload || {};
    const envelopeMeta = msg?.meta || {};
    const mergedMeta = mergeMeta(envelopeMeta, payload?.meta || {});

    emit("event.out", {
      level: "error",
      type: "router_runtime_error",
      text: "Router falló procesando plan.in",
      error: String(error),
      task_id: resolveTaskId(payload, mergedMeta),
      plan_id: resolveTaskId(payload, mergedMeta),
      meta: {
        ...mergedMeta,
        module: MODULE_ID,
        timestamp: safeIsoNow()
      },
      trace_id: msg?.trace_id || payload?.trace_id || generateTraceId()
    });
  }
});