import readline from "readline";

const MODULE_ID = "ai.intent.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

function generateTraceId() {
  return `aii_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

function normalizeText(text) {
  return (text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function isMemoryQuery(text) {
  return (
    text.includes("ultimo comando") ||
    text.includes("ultima app") ||
    text.includes("ultimo archivo") ||
    text.includes("ultimo arcivo") ||
    text.includes("ultimo estado")
  );
}

function analyzeCommand(cmd = {}, envelopeMeta = {}) {
  const raw = cmd?.text || "";
  const text = normalizeText(raw);

  const mergedMeta = {
    source: cmd?.source || envelopeMeta?.source || "cli",
    chat_id: cmd?.chat_id || envelopeMeta?.chat_id || null,
    ...(envelopeMeta || {}),
    ...(cmd?.meta || {})
  };

  const base = {
    observer_only: true,
    raw_text: raw,
    normalized_text: text,
    meta: mergedMeta,
    ts: Date.now(),
    intent: "unknown",
    confidence: 0.35,
    entities: {},
    suggested_action: null
  };

  if (cmd?.meta?.target_application) {
    return {
      ...base,
      intent: "open_application",
      confidence: 0.99,
      entities: {
        application: cmd.meta.target_application
      },
      suggested_action: "open_application",
      locked: true
    };
  }

  if (!text) {
    return {
      ...base,
      intent: "empty_command",
      confidence: 0.99,
      suggested_action: "ignore"
    };
  }

  if (/^(hola|buenas|buen dia|buenas tardes|buenas noches|hello|hi)$/i.test(text)) {
    return {
      ...base,
      intent: "greeting",
      confidence: 0.98,
      suggested_action: "echo_text"
    };
  }

  if (isMemoryQuery(text)) {
    let target = "unknown";

    if (text.includes("ultimo comando")) target = "last_command";
    else if (text.includes("ultima app")) target = "last_app_opened";
    else if (text.includes("ultimo archivo") || text.includes("ultimo arcivo")) target = "last_file_search";
    else if (text.includes("ultimo estado")) target = "last_system_state";

    return {
      ...base,
      intent: "memory_query",
      confidence: 0.99,
      entities: { target },
      suggested_action: "memory.query"
    };
  }

  const mFile = text.match(/^(buscar archivo|busca archivo|search file)\s+(.+)$/i);
  if (mFile) {
    return {
      ...base,
      intent: "search_file",
      confidence: 0.98,
      entities: {
        filename: mFile[2].trim(),
        base_path: "."
      },
      suggested_action: "search_file"
    };
  }

  if (/^(recurso|recursos|estado sistema|estado del sistema|monitor resources)$/i.test(text)) {
    return {
      ...base,
      intent: "monitor_resources",
      confidence: 0.98,
      entities: {},
      suggested_action: "monitor_resources"
    };
  }

  const mGoogle = text.match(/^(buscar en google|googlear|google)\s+(.+)$/i);
  if (mGoogle) {
    return {
      ...base,
      intent: "search_google",
      confidence: 0.97,
      entities: {
        query: mGoogle[2].trim()
      },
      suggested_action: "search_google"
    };
  }

  const mUrl = text.match(/^(abrir web|abrir pagina|abrir pagina web|open url|ir a)\s+(.+)$/i);
  if (mUrl) {
    const rawUrl = mUrl[2].trim();
    const url = /^https?:\/\//i.test(rawUrl) ? rawUrl : `https://${rawUrl}`;

    return {
      ...base,
      intent: "open_url",
      confidence: 0.97,
      entities: { url },
      suggested_action: "open_url"
    };
  }

  const mClick = text.match(/^click web\s+(.+?)\s+\|\s+(.+)$/i);
  if (mClick) {
    const rawUrl = mClick[1].trim();
    const url = /^https?:\/\//i.test(rawUrl) ? rawUrl : `https://${rawUrl}`;

    return {
      ...base,
      intent: "click_web",
      confidence: 0.96,
      entities: {
        url,
        selector: mClick[2].trim()
      },
      suggested_action: "click_web"
    };
  }

  const mForm = text.match(/^form web\s+(.+?)\s+\|\s+(.+?)(?:\s+\|\s+(.+))?$/i);
  if (mForm) {
    const rawUrl = mForm[1].trim();
    const url = /^https?:\/\//i.test(rawUrl) ? rawUrl : `https://${rawUrl}`;

    const fieldsRaw = mForm[2]
      .split(";")
      .map((x) => x.trim())
      .filter(Boolean);

    const fields = [];
    for (const item of fieldsRaw) {
      const idx = item.indexOf("=");
      if (idx === -1) continue;

      fields.push({
        selector: item.slice(0, idx).trim(),
        value: item.slice(idx + 1).trim()
      });
    }

    return {
      ...base,
      intent: "fill_form",
      confidence: 0.96,
      entities: {
        url,
        fields,
        submit_selector: mForm[3] ? mForm[3].trim() : null
      },
      suggested_action: "fill_form"
    };
  }

  if (text.includes("youtube")) {
    return {
      ...base,
      intent: "open_url",
      confidence: 0.86,
      entities: { url: "https://www.youtube.com" },
      suggested_action: "open_url"
    };
  }

  if (text.includes("github")) {
    return {
      ...base,
      intent: "open_url",
      confidence: 0.86,
      entities: { url: "https://github.com" },
      suggested_action: "open_url"
    };
  }

  if (text.includes("google")) {
    return {
      ...base,
      intent: "open_url",
      confidence: 0.82,
      entities: { url: "https://www.google.com" },
      suggested_action: "open_url"
    };
  }

  if (/^(abri|abrir|abre|open)\b/.test(text)) {
    let application = null;

    if (text.includes("chrome")) application = "Google Chrome";
    else if (text.includes("firefox")) application = "Firefox";
    else if (
      text.includes("vscode") ||
      text.includes("vs code") ||
      text.includes("visual studio code") ||
      /\bcode\b/.test(text)
    ) {
      application = "VS Code";
    } else {
      application = text
        .replace(/^(abri|abrir|abre|open)\s+/, "")
        .replace(/^(aplicacion|app)\s+/, "")
        .trim();
    }

    return {
      ...base,
      intent: "open_application",
      confidence: application ? 0.95 : 0.60,
      entities: { application },
      suggested_action: "open_application"
    };
  }

  return {
    ...base,
    intent: "fallback_echo",
    confidence: 0.55,
    entities: { text: raw },
    suggested_action: "echo_text"
  };
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (err) {
    emit("event.out", {
      level: "error",
      type: "ai_intent_invalid_json",
      text: "ai.intent.main recibió una línea JSON inválida",
      error: String(err?.message || err),
      raw_line: String(line).slice(0, 500),
      trace_id: generateTraceId(),
      meta: {
        source: "internal",
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
    return;
  }

  if (msg.port !== "command.in") return;

  const traceId = msg?.trace_id || msg?.payload?.trace_id || generateTraceId();
  const envelopeMeta = msg?.meta || {};
  const analysis = analyzeCommand(msg.payload || {}, envelopeMeta);

  emit("analysis.out", {
    ...analysis,
    trace_id: traceId,
    meta: {
      ...(analysis.meta || {}),
      module: MODULE_ID,
      timestamp: safeIsoNow()
    }
  });

  emit("event.out", {
    level: "info",
    type: "ai_intent_analysis",
    text: `IA observadora detectó ${analysis.intent}`,
    analysis,
    trace_id: traceId,
    meta: {
      ...(analysis.meta || {}),
      module: MODULE_ID,
      timestamp: safeIsoNow()
    }
  });
});