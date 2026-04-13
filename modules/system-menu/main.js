import readline from "readline";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const MODULE_ID = "system.menu.main";

function generateTraceId() {
  return `sysm_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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
    chat_id: payload?.chat_id ?? null,
    module: MODULE_ID,
    timestamp: safeIsoNow(),
    ...extra
  };
}

function btn(text, callbackData) {
  return { text, callback_data: callbackData };
}

function isSystemCallback(data) {
  return typeof data === "string" &&
    (data === "menu:system" || data.startsWith("system:"));
}

function uiPayload(payload, text, inlineKeyboard, traceId = null) {
  return {
    chat_id: payload?.chat_id ?? null,
    message_id: payload?.message_id || null,
    mode: payload?.message_id ? "edit" : "send",
    text,
    inline_keyboard: inlineKeyboard,
    meta: buildTelegramMeta(payload),
    trace_id: traceId || generateTraceId()
  };
}

function buildCommandId() {
  return `sysm_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function commandPayload(payload, text, traceId = null) {
  return {
    command_id: buildCommandId(),
    text,
    source: "telegram",
    chat_id: payload?.chat_id ?? null,
    meta: buildTelegramMeta(payload, {
      ui_origin: "system_menu",
      callback_data: payload?.data || null
    }),
    trace_id: traceId || generateTraceId()
  };
}

function hasValidChatId(payload) {
  return payload?.chat_id !== null && payload?.chat_id !== undefined;
}

function renderSystemMenu(payload, traceId = null) {
  emit(
    "ui.response.out",
    uiPayload(
      payload,
      "Sistema\n\nElegí una acción:",
      [
        [btn("Estado sistema", "system:state")],
        [btn("Buscar archivo", "system:search_file_help")],
        [btn("Volver", "menu:main")]
      ],
      traceId
    )
  );
}

function renderSearchHelp(payload, traceId = null) {
  emit(
    "ui.response.out",
    uiPayload(
      payload,
      "Escribí:\nbuscar archivo <nombre>\n\nEjemplo:\nbuscar archivo main.py",
      [
        [btn("Volver", "menu:system")],
        [btn("Menú", "menu:main")]
      ],
      traceId
    )
  );
}

function handleCallback(payload = {}, traceId = null) {
  const data = payload?.data;
  const finalTraceId = traceId || generateTraceId();

  if (!isSystemCallback(data)) {
    return;
  }

  if (!hasValidChatId(payload)) {
    return;
  }

  if (data === "menu:system") {
    renderSystemMenu(payload, finalTraceId);
    return;
  }

  if (data === "system:state") {
    emit("command.out", commandPayload(payload, "estado sistema", finalTraceId));
    return;
  }

  if (data === "system:search_file_help") {
    renderSearchHelp(payload, finalTraceId);
  }
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

  try {
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
  } catch {
    // Menú defensivo: no tiramos abajo el módulo por un callback roto.
  }
});