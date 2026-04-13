import readline from "readline";

const MODULE_ID = "memory.menu.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

function generateTraceId() {
  return `memm_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

function buildTelegramMeta(payload = {}, extra = {}) {
  return {
    source: "telegram",
    chat_id: payload?.chat_id || null,
    module: MODULE_ID,
    timestamp: safeIsoNow(),
    ...extra
  };
}

function btn(text, callbackData) {
  return { text, callback_data: callbackData };
}

function isMemoryCallback(data) {
  return data === "menu:memory" || data.startsWith("memory:");
}

function uiPayload(payload, text, inline_keyboard, traceId = null) {
  return {
    chat_id: payload?.chat_id || null,
    message_id: payload?.message_id || null,
    mode: payload?.message_id ? "edit" : "send",
    text,
    inline_keyboard,
    trace_id: traceId || generateTraceId(),
    meta: buildTelegramMeta(payload)
  };
}

function memoryQueryPayload(payload, text, traceId = null) {
  return {
    text,
    source: "telegram",
    chat_id: payload?.chat_id || null,
    trace_id: traceId || generateTraceId(),
    meta: buildTelegramMeta(payload, {
      ui_origin: "memory_menu",
      callback_data: payload?.data || null
    })
  };
}

function renderMemoryMenu(payload, traceId = null) {
  emit(
    "ui.response.out",
    uiPayload(
      payload,
      "Memoria",
      [
        [btn("Último comando", "memory:last_command")],
        [btn("Última app", "memory:last_app")],
        [btn("Último web", "memory:last_web")],
        [btn("Contexto activo", "memory:active_context")],
        [btn("Último archivo", "memory:last_file")],
        [btn("Último estado", "memory:last_state")],
        [btn("Volver", "menu:main")]
      ],
      traceId
    )
  );
}

function handleCallback(payload, traceId = null) {
  const data = payload?.data || "";
  if (!isMemoryCallback(data)) return;

  const finalTraceId = traceId || generateTraceId();

  if (data === "menu:memory") {
    renderMemoryMenu(payload, finalTraceId);
    return;
  }

  if (data === "memory:last_command") {
    emit("memory.query.out", memoryQueryPayload(payload, "ultimo comando", finalTraceId));
    return;
  }

  if (data === "memory:last_app") {
    emit("memory.query.out", memoryQueryPayload(payload, "ultima app", finalTraceId));
    return;
  }

  if (data === "memory:last_web") {
    emit("memory.query.out", memoryQueryPayload(payload, "ultimo web", finalTraceId));
    return;
  }

  if (data === "memory:active_context") {
    emit("memory.query.out", memoryQueryPayload(payload, "contexto activo", finalTraceId));
    return;
  }

  if (data === "memory:last_file") {
    emit("memory.query.out", memoryQueryPayload(payload, "ultimo archivo", finalTraceId));
    return;
  }

  if (data === "memory:last_state") {
    emit("memory.query.out", memoryQueryPayload(payload, "ultimo estado", finalTraceId));
    return;
  }

  emit(
    "ui.response.out",
    uiPayload(
      payload,
      "Opción de memoria no reconocida.",
      [
        [btn("Memoria", "menu:memory")],
        [btn("Menú", "menu:main")]
      ],
      finalTraceId
    )
  );
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }

  if (msg.port !== "callback.in") return;

  const payload = msg?.payload || {};
  const topMeta = msg?.meta || {};
  const payloadMeta =
    typeof payload?.meta === "object" && payload?.meta !== null ? payload.meta : {};
  const mergedMeta = mergeMeta(topMeta, payloadMeta);

  handleCallback(
    {
      ...payload,
      meta: mergedMeta
    },
    msg?.trace_id || payload?.trace_id || generateTraceId()
  );
});