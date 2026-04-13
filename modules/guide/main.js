import readline from "readline";

const MODULE_ID = "guide.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const state = new Map();

function generateTraceId() {
  return `guide_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

function now() {
  return new Date().toISOString();
}

function emit(port, payload = {}) {
  const traceId = payload?.trace_id || generateTraceId();
  const meta = payload?.meta || {
    source: "internal",
    timestamp: now(),
    chat_id: getChatIdStrict(payload),
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

function normalize(text) {
  return (text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function mergeMeta(topMeta = {}, payloadMeta = {}) {
  return {
    ...(topMeta || {}),
    ...(payloadMeta || {})
  };
}

function getChatIdStrict(payload = {}, meta = {}) {
  return payload?.chat_id ?? payload?.meta?.chat_id ?? meta?.chat_id ?? null;
}

function getChatIdForCommand(payload = {}, meta = {}) {
  return payload?.chat_id ?? payload?.meta?.chat_id ?? meta?.chat_id ?? "local";
}

function getMeta(payload = {}, envelopeMeta = {}) {
  return {
    source: payload?.source || payload?.meta?.source || envelopeMeta?.source || "unknown",
    chat_id: payload?.chat_id ?? payload?.meta?.chat_id ?? envelopeMeta?.chat_id ?? null,
    user_id: payload?.meta?.user_id || envelopeMeta?.user_id || null
  };
}

function getSession(chatId) {
  if (!state.has(chatId)) {
    state.set(chatId, {
      last_command: null,
      last_action: null,
      last_module: null,
      last_error: null,
      last_result: null,
      history: [],
      updated_at: now(),
      last_context_fingerprint: null,
      last_result_fingerprint: null,
      last_command_trace_id: null
    });
  }
  return state.get(chatId);
}

function pushHistory(session, item) {
  session.history.push({ ...item, at: now() });
  if (session.history.length > 15) {
    session.history = session.history.slice(-15);
  }
  session.updated_at = now();
}

function buildContextFingerprint(payload = {}, meta = {}) {
  return JSON.stringify({
    text: payload?.text || null,
    action: payload?.action || meta?.action || null,
    module: payload?.module || meta?.module || null,
    error: payload?.error || null,
    result_keys: payload?.result && typeof payload.result === "object"
      ? Object.keys(payload.result).sort()
      : null,
    source: meta?.source || payload?.source || null
  });
}

function buildResultFingerprint(payload = {}, meta = {}) {
  return JSON.stringify({
    status: payload?.status || null,
    action: payload?.action || meta?.action || null,
    module: meta?.module || payload?.module || null,
    error: payload?.error || payload?.result?.error || null,
    result_keys: payload?.result && typeof payload.result === "object"
      ? Object.keys(payload.result).sort()
      : null
  });
}

function updateFromContext(payload, meta = {}, traceId = null) {
  const chatId = getChatIdStrict(payload, meta);

  if (chatId == null) {
    return;
  }

  const session = getSession(chatId);
  const fingerprint = buildContextFingerprint(payload, meta);

  if (session.last_context_fingerprint === fingerprint) {
    return;
  }

  session.last_context_fingerprint = fingerprint;

  if (payload?.text) session.last_command = payload.text;
  if (payload?.action) session.last_action = payload.action;
  if (payload?.module || meta?.module) session.last_module = payload?.module || meta?.module;
  if (payload?.error) session.last_error = payload.error;
  if (payload?.result) session.last_result = payload.result;

  pushHistory(session, {
    type: "context",
    source: meta?.source || payload?.source || null
  });
}

function updateFromResult(payload, meta = {}, traceId = null) {
  const chatId = getChatIdStrict(payload, meta);

  if (chatId == null) {
    return;
  }

  const session = getSession(chatId);
  const fingerprint = buildResultFingerprint(payload, meta);

  if (session.last_result_fingerprint === fingerprint) {
    return;
  }

  session.last_result_fingerprint = fingerprint;

  if (payload?.status === "error") {
    session.last_error = payload?.result?.error || payload?.error || "unknown_error";
  } else {
    session.last_result = payload?.result || {};
  }

  if (payload?.action || meta?.action) {
    session.last_action = payload?.action || meta?.action;
  }

  if (meta?.module) {
    session.last_module = meta.module;
  }

  pushHistory(session, {
    type: "result",
    status: payload?.status,
    source: meta?.source || payload?.source || null
  });
}

function isGuideIntent(text) {
  return (
    text.includes("que hago") ||
    text.includes("qué hago") ||
    text.includes("seguimos") ||
    text.includes("como sigo") ||
    text.includes("cómo sigo") ||
    text.includes("que conviene") ||
    text.includes("qué conviene") ||
    text.includes("revisame") ||
    text.includes("revisa") ||
    text.includes("guiame") ||
    text.includes("guíame") ||
    text.includes("orientame") ||
    text.includes("oriéntame") ||
    text.includes("por donde sigo") ||
    text.includes("por dónde sigo")
  );
}

function isExecutable(text) {
  return (
    /^(abrir|abre|abri|open)\b/.test(text) ||
    /^(buscar|busca|search)\b/.test(text) ||
    /^(click|form)\b/.test(text)
  );
}

function shouldForcePassthrough(payload = {}) {
  return !!(
    payload?.meta?.locked ||
    payload?.meta?.target_application ||
    payload?.meta?.resolved_application ||
    payload?.meta?.ui_origin === "apps_menu" ||
    payload?.meta?.ui_origin === "telegram_menu" ||
    payload?.meta?.app_id ||
    payload?.meta?.app_command
  );
}

function inferContext(session) {
  const raw = [
    session.last_command,
    session.last_action,
    session.last_module,
    session.last_error
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (raw.includes("ollama") || raw.includes("llama") || raw.includes("ai")) {
    return "ia";
  }

  if (raw.includes("supervisor") || raw.includes("timeout")) {
    return "supervisor";
  }

  if (raw.includes("router") || raw.includes("blueprint")) {
    return "arquitectura";
  }

  if (raw.includes("telegram") || raw.includes("menu")) {
    return "ui";
  }

  return "general";
}

function buildResponse(text, session) {
  const ctx = inferContext(session);

  if (text.includes("en esto")) {
    return {
      response: `Si te referís a ${ctx}, yo avanzaría con el siguiente paso en ese hilo. ¿Querés que te sugiera el paso técnico o preferís definir primero la estrategia?`
    };
  }

  if (ctx === "ia") {
    return {
      response:
        "Por cómo viene el flujo, yo consolidaría la IA local antes de abrir otro frente. ¿Querés priorizar estabilidad o integración con otros módulos?"
    };
  }

  if (ctx === "supervisor") {
    return {
      response:
        "Estás en la parte de control y ciclos. Yo iría por robustez o limpieza del flujo. ¿Cuál te interesa más ahora?"
    };
  }

  if (ctx === "arquitectura") {
    return {
      response:
        "Parece que estás tocando arquitectura. Yo cerraría primero conexiones antes de sumar más módulos. ¿Querés ajustar wiring o avanzar con funcionalidad?"
    };
  }

  return {
    response:
      "Te acompaño. Antes de avanzar, definamos el siguiente paso: ¿querés destrabar algo, estabilizar algo o agregar algo nuevo?"
  };
}

function buildPassthroughPayload(payload, baseMeta, traceId) {
  return {
    ...payload,
    trace_id: traceId,
    meta: {
      ...(baseMeta || {}),
      ...(payload?.meta || {}),
      module: MODULE_ID,
      timestamp: now()
    }
  };
}

/*
  Guide consume contexto y resultados,
  pero NO re-emite event.out por cada update interno.
  Eso evita storms hacia memory/ui.
*/

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (err) {
    emit("event.out", {
      level: "error",
      type: "guide_invalid_json",
      error: String(err),
      trace_id: generateTraceId(),
      meta: {
        source: "internal",
        module: MODULE_ID,
        timestamp: now()
      }
    });
    return;
  }

  const { port, payload = {} } = msg;
  const topMeta = msg?.meta || {};
  const payloadMeta =
    typeof payload?.meta === "object" && payload?.meta !== null ? payload.meta : {};
  const mergedMeta = mergeMeta(topMeta, payloadMeta);
  const incomingTraceId = msg?.trace_id || payload?.trace_id || generateTraceId();

  if (port === "context.in") {
    updateFromContext(payload, mergedMeta, incomingTraceId);
    return;
  }

  if (port === "result.in") {
    updateFromResult(payload, mergedMeta, incomingTraceId);
    return;
  }

  if (port === "command.in") {
    const chatId = getChatIdForCommand(payload, mergedMeta);
    const meta = getMeta(payload, mergedMeta);
    const session = getSession(chatId);

    const text = payload?.text || "";
    const normalized = normalize(text);
    const traceId = incomingTraceId;

    if (session.last_command_trace_id === traceId) {
      return;
    }
    session.last_command_trace_id = traceId;

    session.last_command = text;
    pushHistory(session, { type: "command", text });

    emit("event.out", {
      level: "info",
      type: "guide_command_received",
      text,
      meta: {
        ...meta,
        module: MODULE_ID,
        timestamp: now()
      },
      trace_id: traceId
    });

    if (shouldForcePassthrough(payload)) {
      emit("command.out", buildPassthroughPayload(payload, meta, traceId));
      return;
    }

    if (isGuideIntent(normalized)) {
      const response = buildResponse(normalized, session);

      emit("event.out", {
        level: "info",
        type: "guide_intervention",
        mode: "adaptive",
        meta: {
          ...meta,
          module: MODULE_ID,
          timestamp: now()
        },
        trace_id: traceId
      });

      emit("response.out", {
        task_id: payload?.task_id || payload?.command_id || `guide_${Date.now()}`,
        status: "success",
        result: {
          guided: true,
          response: response.response
        },
        trace_id: traceId,
        meta: {
          ...meta,
          ...(payload?.meta || {}),
          module: MODULE_ID,
          timestamp: now()
        }
      });
      return;
    }

    if (isExecutable(normalized)) {
      emit("event.out", {
        level: "info",
        type: "guide_passthrough",
        text,
        meta: {
          ...meta,
          module: MODULE_ID,
          timestamp: now()
        },
        trace_id: traceId
      });

      emit("command.out", buildPassthroughPayload(payload, meta, traceId));
      return;
    }

    emit("event.out", {
      level: "info",
      type: "guide_default_passthrough",
      text,
      meta: {
        ...meta,
        module: MODULE_ID,
        timestamp: now()
      },
      trace_id: traceId
    });

    emit("command.out", buildPassthroughPayload(payload, meta, traceId));
  }
});