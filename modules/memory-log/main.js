import readline from "readline";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const MODULE_ID = "memory.log.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const logsDir = path.resolve(__dirname, "../../logs");
const logFile = path.join(logsDir, "events.log");
const sessionFile = path.join(logsDir, "session-memory.json");

fs.mkdirSync(logsDir, { recursive: true });

const defaultSession = {
  last_command: null,
  last_app_opened: null,
  last_app_opened_label: null,
  last_web_opened: null,
  last_web_opened_label: null,
  last_active_family: null,
  last_file_search: null,
  last_system_state: null,
  last_response: null,
  last_error: null,
  last_task_id: null
};

function generateTraceId() {
  return `mem_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

function append(entry) {
  try {
    fs.appendFileSync(logFile, JSON.stringify(entry) + "\n");
  } catch (err) {
    process.stderr.write(`[memory] append error: ${err.message}\n`);
  }
}

function persistSession() {
  try {
    fs.writeFileSync(sessionFile, JSON.stringify(session, null, 2), "utf8");
  } catch (err) {
    process.stderr.write(`[memory] persist error: ${err.message}\n`);
  }
}

function loadSession() {
  try {
    if (fs.existsSync(sessionFile)) {
      const raw = fs.readFileSync(sessionFile, "utf8");
      const parsed = JSON.parse(raw);
      return { ...defaultSession, ...parsed };
    }
  } catch (err) {
    process.stderr.write(
      `[memory] No se pudo cargar session-memory.json: ${err.message}\n`
    );
  }
  return { ...defaultSession };
}

const session = loadSession();
const recentAnswers = new Map();

function mergeMeta(topMeta = {}, payloadMeta = {}) {
  return {
    ...(topMeta || {}),
    ...(payloadMeta || {})
  };
}

function normalizeQuery(text) {
  return (text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function dedupeKey(text, meta = {}) {
  const chatId = meta?.chat_id || "global";
  return `${chatId}::${normalizeQuery(text)}`;
}

function cleanupRecentAnswers(windowMs = 2500) {
  const now = Date.now();
  for (const [key, ts] of recentAnswers.entries()) {
    if (now - ts > windowMs * 4) {
      recentAnswers.delete(key);
    }
  }
}

function shouldSkipDuplicateAnswer(text, meta = {}, windowMs = 2500) {
  cleanupRecentAnswers(windowMs);

  const key = dedupeKey(text, meta);
  const now = Date.now();
  const prev = recentAnswers.get(key) || 0;

  if (now - prev < windowMs) {
    return true;
  }

  recentAnswers.set(key, now);
  return false;
}

function isMemoryQuery(text) {
  const q = normalizeQuery(text);
  return (
    q.includes("ultimo comando") ||
    q.includes("ultima app") ||
    q.includes("ultima app activa") ||
    q.includes("ultima app desktop") ||
    q.includes("ultima app abierta") ||
    q.includes("ultimo desktop") ||
    q.includes("ultimo web") ||
    q.includes("ultima web") ||
    q.includes("ultimo contexto web") ||
    q.includes("ultimo archivo") ||
    q.includes("ultimo arcivo") ||
    q.includes("ultimo estado") ||
    q.includes("contexto activo")
  );
}

const SATELLITE_SOURCES = new Set([
  "ai.learning.engine.main",
  "gamification.main",
  "ai.self.audit.main"
]);

function isSatelliteResult(payload, meta = {}) {
  const source = payload?.meta?.source || meta?.source || payload?.source || null;
  const moduleId = payload?.module || meta?.module || null;
  return SATELLITE_SOURCES.has(source) || SATELLITE_SOURCES.has(moduleId);
}

function updateFromResult(payload, meta = {}) {
  if (!isSatelliteResult(payload, meta)) {
    session.last_response = payload || null;
    session.last_task_id =
      payload?.task_id || payload?.plan_id || meta?.task_id || meta?.plan_id || null;
  }

  if (payload?.status === "error") {
    session.last_error =
      payload?.result?.error || payload?.error || "unknown_error";
  }

  if (payload?.result?.filename && Array.isArray(payload?.result?.matches)) {
    session.last_file_search = {
      filename: payload.result.filename,
      matches: payload.result.matches
    };
  }

  if (
    payload?.result?.cpu_percent !== undefined &&
    payload?.result?.memory_percent !== undefined &&
    payload?.result?.disk_percent !== undefined
  ) {
    session.last_system_state = {
      cpu_percent: payload.result.cpu_percent,
      memory_percent: payload.result.memory_percent,
      disk_percent: payload.result.disk_percent
    };
  }

  if (payload?.result?.opened && payload?.result?.application && !payload?.result?.url) {
    session.last_app_opened =
      payload.result.command || payload.result.application || null;
    session.last_app_opened_label =
      payload.result.resolved_name || payload.result.application || null;
    session.last_active_family = "desktop";
  }

  if (payload?.result?.opened && payload?.result?.url) {
    session.last_web_opened = payload.result.url || null;
    session.last_web_opened_label =
      payload.result.title || payload.result.url || null;
    session.last_active_family = "browser";
  }

  persistSession();
}

function updateFromAppSession(payload, meta = {}) {
  const family = payload?.family || payload?.app?.family || null;
  const platformFamily =
    payload?.platform_family ||
    (payload?.web ? "browser" : payload?.app ? "desktop" : null);

  const app = payload?.app || {};
  const web = payload?.web || null;

  if (platformFamily) {
    session.last_active_family = platformFamily;
  }

  if (platformFamily === "browser") {
    session.last_web_opened = web?.url || null;
    session.last_web_opened_label =
      web?.title || app?.label || web?.url || null;
  } else if (platformFamily === "desktop") {
    session.last_app_opened = app?.command || app?.id || null;
    session.last_app_opened_label = app?.label || null;
  } else if (family === "browser") {
    session.last_active_family = "browser";
    session.last_web_opened = web?.url || null;
    session.last_web_opened_label =
      web?.title || app?.label || web?.url || null;
  }

  if (meta?.task_id || meta?.plan_id) {
    session.last_task_id = meta?.task_id || meta?.plan_id || null;
  }

  persistSession();
}

function answerMemoryQuery(text, meta = {}) {
  const q = normalizeQuery(text);
  let answer = "No tengo ese dato todavía.";

  if (q.includes("ultimo comando")) {
    answer = session.last_command
      ? `Último comando: ${session.last_command}`
      : "No tengo último comando todavía.";
  } else if (
    q.includes("ultima app activa") ||
    q.includes("contexto activo") ||
    q.includes("ultima app")
  ) {
    if (session.last_active_family === "browser") {
      answer = session.last_web_opened_label
        ? `Contexto activo actual: ${session.last_web_opened_label}`
        : "No tengo contexto activo actual todavía.";
    } else if (session.last_active_family === "desktop") {
      answer = session.last_app_opened_label
        ? `App activa actual: ${session.last_app_opened_label}`
        : "No tengo app activa actual todavía.";
    } else {
      answer = session.last_app_opened_label
        ? `Última app desktop abierta: ${session.last_app_opened_label}`
        : session.last_web_opened_label
          ? `Último contexto web activo: ${session.last_web_opened_label}`
          : "No tengo contexto activo todavía.";
    }
  } else if (
    q.includes("ultima app desktop") ||
    q.includes("ultimo desktop") ||
    q.includes("ultima app abierta")
  ) {
    answer = session.last_app_opened_label
      ? `Última app desktop abierta: ${session.last_app_opened_label}`
      : "No tengo última app desktop abierta todavía.";
  } else if (
    q.includes("ultimo web") ||
    q.includes("ultima web") ||
    q.includes("ultimo contexto web")
  ) {
    answer = session.last_web_opened_label
      ? `Último contexto web: ${session.last_web_opened_label}`
      : "No tengo último contexto web todavía.";
  } else if (q.includes("ultimo archivo") || q.includes("ultimo arcivo")) {
    answer = session.last_file_search?.filename
      ? `Último archivo buscado: ${session.last_file_search.filename}`
      : "No tengo último archivo buscado todavía.";
  } else if (q.includes("ultimo estado")) {
    if (session.last_system_state) {
      answer =
        `Último estado: CPU ${session.last_system_state.cpu_percent}% | ` +
        `RAM ${session.last_system_state.memory_percent}% | ` +
        `Disco ${session.last_system_state.disk_percent}%`;
    } else {
      answer = "No tengo último estado del sistema todavía.";
    }
  }

  emit("memory.out", {
    task_id: `memory_${Date.now()}`,
    status: "success",
    result: {
      memory_answer: answer
    },
    meta: {
      ...meta,
      module: MODULE_ID,
      timestamp: safeIsoNow()
    }
  });
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (err) {
    process.stderr.write(`[memory] parse error: ${err.message}\n`);
    return;
  }

  const { port, payload = {} } = msg;
  const topMeta = msg?.meta || {};
  const payloadMeta =
    typeof payload?.meta === "object" && payload?.meta !== null ? payload.meta : {};
  const meta = mergeMeta(topMeta, payloadMeta);

  if (port === "command.in") {
    const incomingText = payload?.text || null;
    if (!isMemoryQuery(incomingText)) {
      session.last_command = incomingText;
      persistSession();
    }
    append({ ts: Date.now(), port, payload, meta });
    return;
  }

  if (port === "result.in") {
    updateFromResult(payload, meta);
    append({ ts: Date.now(), port, payload, meta });
    return;
  }

  if (port === "app.session.in") {
    updateFromAppSession(payload, meta);
    append({ ts: Date.now(), port, payload, meta });
    return;
  }

  if (port === "query.in") {
    append({ ts: Date.now(), port, payload, meta });

    const text = payload?.text || "";

    if (isMemoryQuery(text) && !shouldSkipDuplicateAnswer(text, meta)) {
      answerMemoryQuery(text, meta);
    }

    return;
  }

  if (port === "event.in") {
    append({ ts: Date.now(), port, payload, meta });
  }
});