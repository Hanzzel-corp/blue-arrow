import readline from "readline";

const MODULE_ID = "office.writer.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const sessions = new Map();

function now() {
  return new Date().toISOString();
}

function generateTraceId(prefix = "office_writer") {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function emit(port, payload = {}, envelopeMeta = {}) {
  const traceId = payload?.trace_id || envelopeMeta?.trace_id || generateTraceId();
  const meta = {
    source: payload?.meta?.source || envelopeMeta?.source || "internal",
    chat_id: payload?.meta?.chat_id ?? envelopeMeta?.chat_id ?? payload?.chat_id ?? null,
    user_id: payload?.meta?.user_id ?? envelopeMeta?.user_id ?? null,
    module: MODULE_ID,
    timestamp: now(),
    task_id: payload?.meta?.task_id || envelopeMeta?.task_id || payload?.task_id || null,
    plan_id: payload?.meta?.plan_id || envelopeMeta?.plan_id || payload?.plan_id || null
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
    .trim();
}

function getChatId(payload = {}, meta = {}) {
  return payload?.chat_id ?? payload?.meta?.chat_id ?? meta?.chat_id ?? "local";
}

function getTaskId(payload = {}, meta = {}) {
  return payload?.task_id || meta?.task_id || payload?.command_id || `office_${Date.now()}`;
}

function getSession(chatId) {
  if (!sessions.has(chatId)) {
    sessions.set(chatId, {
      chat_id: chatId,
      root_task_id: null,
      last_writer_window_id: null,
      pending_ai_task_id: null,
      pending_open_task_id: null,
      pending_write_task_id: null,
      pending_mode: null,
      draft_text: null,
      last_trace_id: null,
      waiting_open: false,
      waiting_ai: false,
      waiting_write: false
    });
  }
  return sessions.get(chatId);
}

function resetFlow(session) {
  session.root_task_id = null;
  session.pending_ai_task_id = null;
  session.pending_open_task_id = null;
  session.pending_write_task_id = null;
  session.pending_mode = null;
  session.draft_text = null;
  session.waiting_open = false;
  session.waiting_ai = false;
  session.waiting_write = false;
}

function parseWriterIntent(text) {
  const raw = normalize(text);

  if (
    raw.includes("writer") ||
    raw.includes("office") ||
    raw.includes("libreoffice") ||
    raw.includes("documento")
  ) {
    if (raw.includes("mejor") || raw.includes("mejora") || raw.includes("reescrib")) {
      return "office.writer.generate";
    }
    if (raw.includes("redact") || raw.includes("carta") || raw.includes("nota") || raw.includes("escrib")) {
      return "office.writer.generate";
    }
    return "office.writer.open";
  }

  return null;
}

function extractPrompt(text) {
  const raw = text || "";
  return raw
    .replace(/^(abr[ií]r?|abre|abrir)\s+(office|writer|libreoffice)\s*/i, "")
    .replace(/^(escrib[ií]|escribe|redact[aá])\s*/i, "")
    .trim();
}

function requestOpenWriter(payload, meta) {
  const chatId = getChatId(payload, meta);
  const session = getSession(chatId);
  const taskId = getTaskId(payload, meta);

  session.root_task_id = taskId;
  session.pending_open_task_id = `${taskId}__open`;
  session.waiting_open = true;

  emit("event.out", {
    level: "info",
    type: "office_writer_open_requested",
    chat_id: chatId,
    task_id: taskId,
    pending_open_task_id: session.pending_open_task_id
  }, meta);

  emit("desktop.action.out", {
    task_id: session.pending_open_task_id,
    action: "office.open_writer",
    params: {
      app: "writer",
      command: "libreoffice --writer"
    }
  }, meta);
}

function requestAiDraft(payload, meta, userPrompt) {
  const chatId = getChatId(payload, meta);
  const session = getSession(chatId);
  const aiTaskId = `${session.root_task_id || getTaskId(payload, meta)}__ai`;

  session.pending_ai_task_id = aiTaskId;
  session.waiting_ai = true;
  session.pending_mode = "generate_and_write";

  emit("event.out", {
    level: "info",
    type: "office_writer_ai_requested",
    chat_id: chatId,
    ai_task_id: aiTaskId
  }, meta);

  emit("ai.action.out", {
    task_id: aiTaskId,
    action: "ai.query",
    params: {
      prompt:
        `Redactá en español, claro y profesional. ` +
        `Devolvé solo el texto final para pegar en LibreOffice Writer. ` +
        `Pedido del usuario: ${userPrompt}`
    }
  }, meta);
}

function requestWriteText(payload, meta, textToWrite) {
  const chatId = getChatId(payload, meta);
  const session = getSession(chatId);

  session.pending_write_task_id = `${session.root_task_id || getTaskId(payload, meta)}__write`;
  session.waiting_write = true;

  emit("event.out", {
    level: "info",
    type: "office_writer_text_write_requested",
    chat_id: chatId,
    worker_task_id: session.pending_write_task_id,
    has_window_id: Boolean(session.last_writer_window_id || payload?.meta?.window_id || null),
    chars: (textToWrite || "").length
  }, meta);

  emit("desktop.action.out", {
    task_id: session.pending_write_task_id,
    action: "office.write_text",
    params: {
      text: textToWrite,
      window_id: session.last_writer_window_id || payload?.meta?.window_id || null,
      app: "writer"
    }
  }, meta);
}

function finishSuccess(session, meta, extra = {}) {
  emit("result.out", {
    task_id: session.root_task_id || `office_done_${Date.now()}`,
    status: "success",
    result: {
      handled: true,
      opened: true,
      wrote: true,
      window_id: session.last_writer_window_id || null,
      ...extra
    }
  }, meta);

  resetFlow(session);
}

function finishError(session, meta, error) {
  emit("result.out", {
    task_id: session.root_task_id || `office_error_${Date.now()}`,
    status: "error",
    result: {
      error
    }
  }, meta);

  resetFlow(session);
}

function handleCommand(payload, meta) {
  const text = payload?.text || "";
  const intent = parseWriterIntent(text);

  if (!intent) {
    emit("result.out", {
      task_id: getTaskId(payload, meta),
      status: "ignored",
      result: {
        handled: false,
        reason: "no_writer_intent"
      }
    }, meta);
    return;
  }

  const chatId = getChatId(payload, meta);
  const session = getSession(chatId);
  session.root_task_id = getTaskId(payload, meta);

  if (intent === "office.writer.open") {
    requestOpenWriter(payload, meta);
    return;
  }

  const prompt = extractPrompt(text);

  if (!prompt) {
    emit("ui.response.out", {
      task_id: getTaskId(payload, meta),
      status: "success",
      result: {
        response: "Decime qué querés redactar en Writer. Ejemplo: 'abrí writer y redactá una nota formal para un cliente'."
      }
    }, meta);
    return;
  }

  requestOpenWriter(payload, meta);
  requestAiDraft(payload, meta, prompt);
}

function handleDesktopResult(payload, meta) {
  const result = payload?.result || {};
  const chatId = getChatId(payload, meta);
  const session = getSession(chatId);
  const taskId = payload?.task_id || "";

  if (!session.root_task_id) {
    return;
  }

  if (result?.window_id) {
    session.last_writer_window_id = result.window_id;
  }

  emit("event.out", {
    level: "info",
    type: "office_writer_desktop_result",
    chat_id: chatId,
    status: payload?.status || "unknown",
    worker_task_id: taskId,
    expected_open_task_id: session.pending_open_task_id,
    expected_write_task_id: session.pending_write_task_id,
    window_id: result?.window_id || null
  }, meta);

  if (taskId === session.pending_open_task_id) {
    session.waiting_open = false;

    if (payload?.status === "error" || result?.success === false) {
      finishError(session, meta, result?.error || "writer_open_failed");
      return;
    }

    emit("event.out", {
      level: "info",
      type: "office_writer_open_confirmed",
      task_id: session.root_task_id,
      pending_ai: session.waiting_ai,
      pending_write: session.waiting_write,
      window_id: session.last_writer_window_id || null
    }, meta);

    if (!session.waiting_ai && !session.waiting_write) {
      emit("result.out", {
        task_id: session.root_task_id || `office_open_${Date.now()}`,
        status: "success",
        result: {
          handled: true,
          action: "office.open_writer",
          opened: true,
          window_id: session.last_writer_window_id || null
        }
      }, meta);
      resetFlow(session);
      return;
    }

    return;
  }

  if (taskId === session.pending_write_task_id) {
    session.waiting_write = false;

    if (payload?.status === "error" || result?.success === false) {
      finishError(session, meta, result?.error || "writer_write_failed");
      return;
    }

    emit("event.out", {
      level: "info",
      type: "office_writer_write_confirmed",
      task_id: session.root_task_id,
      window_id: session.last_writer_window_id || null
    }, meta);

    finishSuccess(session, meta, {
      action: "office.writer.generate",
      text_generated: Boolean(session.draft_text)
    });
  }
}

function handleAiResult(payload, meta) {
  const chatId = getChatId(payload, meta);
  const session = getSession(chatId);

  if (!session.root_task_id) {
    return;
  }

  emit("event.out", {
    level: "info",
    type: "office_writer_ai_result_received",
    task_id: payload?.task_id || null,
    expected_ai_task_id: session.pending_ai_task_id,
    status: payload?.status || "unknown"
  }, meta);

  if (!session.pending_ai_task_id || payload?.task_id !== session.pending_ai_task_id) {
    emit("event.out", {
      level: "warn",
      type: "office_writer_ai_result_ignored",
      task_id: payload?.task_id || null,
      expected_ai_task_id: session.pending_ai_task_id || null
    }, meta);
    return;
  }

  const text =
    payload?.result?.text ||
    payload?.result?.response ||
    payload?.result?.content ||
    payload?.result?.message ||
    "";

  session.waiting_ai = false;

  if (payload?.status === "error") {
    finishError(session, meta, payload?.result?.error || "ai_generation_failed");
    return;
  }

  if (!text) {
    finishError(session, meta, "ai_empty_response");
    return;
  }

  session.draft_text = text;
  session.pending_ai_task_id = null;

  emit("event.out", {
    level: "info",
    type: "office_writer_ai_text_ready",
    task_id: session.root_task_id,
    chars: text.length,
    has_window_id: Boolean(session.last_writer_window_id)
  }, meta);

  requestWriteText(
    {
      task_id: session.root_task_id,
      meta: { ...meta, chat_id: chatId }
    },
    meta,
    text
  );

  emit("ui.response.out", {
    task_id: `${session.root_task_id || "office"}__ai_notice`,
    status: "success",
    result: {
      response: "Ya generé el texto con IA y lo estoy mandando a Writer."
    }
  }, meta);
}

function handleAction(payload, meta) {
  const action = payload?.action;
  const params = payload?.params || {};
  const chatId = getChatId(payload, meta);
  const session = getSession(chatId);
  session.root_task_id = getTaskId(payload, meta);

  if (action === "office.open_writer") {
    requestOpenWriter(payload, meta);
    return;
  }

  if (action === "office.write_text") {
    requestWriteText(payload, meta, params.text || "");
    return;
  }

  if (action === "office.writer.generate") {
    requestOpenWriter(payload, meta);
    requestAiDraft(payload, meta, params.prompt || params.text || "");
  }
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (err) {
    emit("event.out", {
      level: "error",
      type: "office_writer_invalid_json",
      error: String(err)
    });
    return;
  }

  const port = msg?.port;
  const payload = msg?.payload || {};
  const meta = msg?.meta || {};
  const sourceModule = msg?.module || meta?.module || payload?.meta?.module || "";

  if (port === "command.in") {
    handleCommand(payload, meta);
    return;
  }

  if (port === "action.in") {
    handleAction(payload, meta);
    return;
  }

  if (port === "result.in") {
    emit("event.out", {
      level: "info",
      type: "office_writer_result_in_received",
      source_module: sourceModule,
      task_id: payload?.task_id || null,
      status: payload?.status || "unknown"
    }, meta);

    if (sourceModule === "worker.python.desktop") {
      handleDesktopResult(payload, meta);
      return;
    }

    if (sourceModule === "ai.assistant.main") {
      handleAiResult(payload, meta);
      return;
    }

    emit("event.out", {
      level: "warn",
      type: "office_writer_result_in_unknown_source",
      source_module: sourceModule || "unknown",
      task_id: payload?.task_id || null
    }, meta);
  }
});