import fs from "fs";
import path from "path";
import readline from "readline";
import { fileURLToPath } from "url";

const MODULE_ID = "apps.session.main";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const STORE_PATH = path.resolve(__dirname, "../../logs/apps-session.json");

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

function generateTraceId() {
  return `apps_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

function loadStore() {
  try {
    if (!fs.existsSync(STORE_PATH)) return new Map();
    const raw = fs.readFileSync(STORE_PATH, "utf8");
    if (!raw.trim()) return new Map();
    const parsed = JSON.parse(raw);
    return new Map(Object.entries(parsed));
  } catch (error) {
    process.stderr.write(`[${MODULE_ID}] loadStore error: ${String(error)}\n`);
    return new Map();
  }
}

const sessionByChat = loadStore();

function saveStore(traceId = null, meta = null) {
  try {
    const out = Object.fromEntries(sessionByChat);
    fs.mkdirSync(path.dirname(STORE_PATH), { recursive: true });
    fs.writeFileSync(STORE_PATH, JSON.stringify(out, null, 2), "utf8");
  } catch (error) {
    emit("event.out", {
      level: "error",
      type: "app_session_store_error",
      error: String(error),
      trace_id: traceId || generateTraceId(),
      meta: meta || {
        source: "internal",
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
  }
}

function nowIso() {
  return safeIsoNow();
}

function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim();
}

function slugify(value) {
  const text = normalizeText(value)
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return text || "app";
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function mergeMeta(topMeta = {}, payloadMeta = {}) {
  return {
    ...(topMeta || {}),
    ...(payloadMeta || {})
  };
}

function getChatId(payload = {}, meta = {}) {
  return (
    payload?.chat_id ??
    payload?.meta?.chat_id ??
    meta?.chat_id ??
    payload?.report?.meta?.chat_id ??
    payload?.result?.meta?.chat_id ??
    null
  );
}

function includesAny(text, fragments) {
  return fragments.some((fragment) => text.includes(fragment));
}

function detectFamily({ label, command, url }) {
  if (url) return "browser";

  const haystack = normalizeText(`${label || ""} ${command || ""}`);

  if (
    includesAny(haystack, [
      "calculator",
      "gnome-calculator",
      "kcalc",
      "qalculate",
      "calc"
    ])
  ) {
    return "calculator";
  }

  if (
    includesAny(haystack, [
      "nautilus",
      "files",
      "file manager",
      "explorer",
      "dolphin",
      "thunar",
      "caja",
      "nemo",
      "folder"
    ])
  ) {
    return "files";
  }

  if (
    includesAny(haystack, [
      "firefox",
      "chrome",
      "chromium",
      "brave",
      "opera",
      "edge",
      "browser",
      "youtube",
      "github"
    ])
  ) {
    return "browser";
  }

  return "generic";
}

function detectPlatformFamily({ url, opened }) {
  if (url) return "browser";
  if (opened) return "desktop";
  return "unknown";
}

function capabilitiesForFamily(family) {
  if (family === "calculator") {
    return [
      "input_expression",
      "read_result",
      "clear",
      "copy_result",
      "close_app"
    ];
  }

  if (family === "files") {
    return [
      "open_folder",
      "search_file",
      "recent_files",
      "close_app"
    ];
  }

  if (family === "browser") {
    return [
      "open_url",
      "search_web",
      "click",
      "fill_form",
      "close_app"
    ];
  }

  return ["close_app"];
}

function buildResolvedApplication(app = {}) {
  return {
    id: app?.id || null,
    label: app?.label || null,
    command: app?.command || null,
    source: app?.source || null,
    window_id: app?.window_id || null
  };
}

function enrichCommandWithUiContext(payload, state) {
  const activeApp = state?.active_app || state?.app || null;

  return {
    ...payload,
    meta: {
      ...(payload?.meta || {}),
      active_app: activeApp,
      resolved_application: activeApp
        ? {
            id: activeApp.id || null,
            label: activeApp.label || null,
            command: activeApp.command || null,
            source: activeApp.source || null,
            window_id: activeApp.window_id || null
          }
        : (payload?.meta?.resolved_application || null),
      window_id: payload?.meta?.window_id || activeApp?.window_id || null
    }
  };
}

function buildContextFromResult(payload, meta = {}) {
  if (payload?.status !== "success") return null;

  const result = payload?.result || {};
  const opened = result?.opened === true;
  const url = firstString(result?.url);
  const title = firstString(result?.title);

  const label = firstString(
    result?.resolved_name,
    result?.application,
    result?.label,
    title,
    url ? "Browser" : null
  );

  const command = firstString(
    result?.command,
    result?.application,
    url ? "browser" : null
  );

  const source = firstString(
    result?.source,
    payload?.meta?.source,
    meta?.source,
    url ? "browser" : "desktop"
  );

  const family = detectFamily({ label, command, url });
  const platformFamily = detectPlatformFamily({ url, opened });

  const looksLikeDesktopOpen =
    opened &&
    !url &&
    (result?.application || result?.resolved_name || result?.command);

  const looksLikeBrowserOpen =
    (opened && !!url) ||
    (opened && family === "browser") ||
    (!!url && !!title);

  if (!looksLikeDesktopOpen && !looksLikeBrowserOpen) {
    return null;
  }

  const appId =
    family === "calculator"
      ? "calculator"
      : family === "files"
        ? "files"
        : family === "browser"
          ? "browser"
          : slugify(label || command || "app");

  const capabilities = capabilitiesForFamily(family);

  const app = {
    id: appId,
    label: label || "App",
    command,
    source,
    family,
    window_id: result?.window_id || result?.windowId || null
  };

  return {
    chat_id: getChatId(payload, meta),
    task_id: payload?.task_id || meta?.task_id || null,
    family,
    platform_family: platformFamily,
    app,
    active_app: app,
    resolved_application: buildResolvedApplication(app),
    capabilities,
    web: looksLikeBrowserOpen
      ? {
          url: url || null,
          title: title || null
        }
      : null
  };
}

function getSession(chatId) {
  return sessionByChat.get(String(chatId)) || null;
}

function emitMemorySync(session, traceId = null) {
  const basePayload = {
    chat_id: session.chat_id,
    task_id: session.task_id || null,
    family: session.family,
    platform_family: session.platform_family || null,
    app: session.app,
    resolved_application:
      session.resolved_application || buildResolvedApplication(session.app),
    capabilities: session.capabilities,
    web: session.web || null,
    updated_at: session.updated_at,
    source: MODULE_ID,
    trace_id: traceId || generateTraceId()
  };

  emit("memory.sync.out", enrichCommandWithUiContext(basePayload, session));
}

function writeSession(context, traceId = null) {
  const chatId = context?.chat_id;
  if (chatId == null) return;

  const key = String(chatId);
  const previous = getSession(chatId);
  const existingApp = previous?.app || null;
  const existingResolvedApplication =
    previous?.resolved_application || buildResolvedApplication(existingApp || {});
  const app = context?.app || {};
  const capabilities = Array.isArray(context?.capabilities)
    ? context.capabilities
    : ["close_app"];

  const nextApp = {
    id: app?.id || existingApp?.id || null,
    label: app?.label || existingApp?.label || null,
    command: app?.command || existingApp?.command || null,
    source: app?.source || existingApp?.source || null,
    family: app?.family || context?.family || existingApp?.family || "generic",
    window_id: app?.window_id || existingApp?.window_id || null
  };

  const nextResolvedApplication = {
    id: nextApp.id || existingResolvedApplication?.id || null,
    label: nextApp.label || existingResolvedApplication?.label || null,
    command: nextApp.command || existingResolvedApplication?.command || null,
    source: nextApp.source || existingResolvedApplication?.source || null,
    window_id: nextApp.window_id || existingResolvedApplication?.window_id || null
  };

  const next = {
    chat_id: chatId,
    active: true,
    updated_at: nowIso(),
    task_id: context?.task_id || null,
    family: context?.family || "generic",
    platform_family: context?.platform_family || "unknown",
    app: nextApp,
    active_app: nextApp,
    resolved_application: nextResolvedApplication,
    capabilities,
    web: context?.web || null,
    previous_app_id: previous?.app?.id || null
  };

  sessionByChat.set(key, next);
  saveStore(traceId, {
    source: MODULE_ID,
    chat_id: chatId,
    module: MODULE_ID,
    timestamp: safeIsoNow()
  });

  const appContextPayload = {
    chat_id: chatId,
    session: next,
    family: next.family,
    platform_family: next.platform_family,
    app: {
      ...next.app,
      capabilities: next.capabilities
    },
    resolved_application: next.resolved_application,
    capabilities: next.capabilities,
    web: next.web,
    source: MODULE_ID,
    trace_id: traceId || generateTraceId()
  };

  emit("app.context.out", enrichCommandWithUiContext(appContextPayload, next));
  emitMemorySync(next, traceId);

  emit("event.out", {
    level: "info",
    type: "app_session_updated",
    chat_id: chatId,
    family: next?.family || null,
    session: next || null,
    trace_id: traceId || generateTraceId(),
    app_id: next.app.id,
    platform_family: next.platform_family,
    capabilities: next.capabilities,
    meta: {
      source: next.app.source,
      task_id: next.task_id,
      window_id: next.app.window_id || null,
      active_app: next.app,
      resolved_application: next.resolved_application,
      module: MODULE_ID,
      timestamp: safeIsoNow()
    }
  });
}

function emitCurrentSession(chatId, traceId = null) {
  const session = getSession(chatId);

  if (!session) {
    emit("event.out", {
      level: "info",
      type: "app_session_missing",
      chat_id: chatId,
      trace_id: traceId || generateTraceId(),
      meta: {
        source: MODULE_ID,
        chat_id: chatId,
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
    return;
  }

  const currentSessionPayload = {
    chat_id: chatId,
    session,
    family: session.family,
    platform_family: session.platform_family || null,
    app: {
      ...session.app,
      capabilities: session.capabilities
    },
    resolved_application:
      session.resolved_application || buildResolvedApplication(session.app),
    capabilities: session.capabilities,
    web: session.web || null,
    source: MODULE_ID,
    trace_id: traceId || generateTraceId()
  };

  emit(
    "app.context.out",
    enrichCommandWithUiContext(currentSessionPayload, session)
  );

  emitMemorySync(session, traceId);
}

function clearSession(chatId, traceId = null) {
  if (chatId == null) return;
  const key = String(chatId);
  const existed = sessionByChat.get(key);
  sessionByChat.delete(key);
  saveStore(traceId, {
    source: MODULE_ID,
    chat_id: chatId,
    module: MODULE_ID,
    timestamp: safeIsoNow()
  });

  emit("app.context.out", {
    chat_id: chatId,
    session: null,
    family: null,
    resolved_application: null,
    window_id: null,
    source: MODULE_ID,
    trace_id: traceId || generateTraceId(),
    meta: {
      source: MODULE_ID,
      chat_id: chatId,
      reason: "session_cleared",
      module: MODULE_ID,
      timestamp: safeIsoNow()
    }
  });

  emit("memory.sync.out", {
    chat_id: chatId,
    task_id: null,
    family: null,
    platform_family: null,
    app: null,
    resolved_application: null,
    capabilities: [],
    web: null,
    updated_at: nowIso(),
    source: MODULE_ID,
    trace_id: traceId || generateTraceId(),
    meta: {
      active_app: null,
      resolved_application: null,
      window_id: null,
      module: MODULE_ID,
      timestamp: safeIsoNow()
    }
  });

  emit("event.out", {
    level: "info",
    type: "app_session_cleared",
    chat_id: chatId,
    meta: {
      source: MODULE_ID,
      module: MODULE_ID,
      timestamp: safeIsoNow()
    },
    trace_id: traceId || generateTraceId(),
    app_id: existed?.app?.id || null
  });
}

function handleResult(payload, meta = {}, traceId = null) {
  const context = buildContextFromResult(payload, meta);
  if (!context || context.chat_id == null) return;
  writeSession(context, traceId);
}

function handleQuery(payload, meta = {}, traceId = null) {
  const action = payload?.action || "get_active_app";
  const chatId = getChatId(payload, meta);

  if (chatId == null) return;

  if (action === "clear_active_app") {
    clearSession(chatId, traceId);
    return;
  }

  emitCurrentSession(chatId, traceId);
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (error) {
    emit("event.out", {
      level: "error",
      type: "app_session_parse_error",
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

  const payload = msg?.payload || {};
  const topMeta = msg?.meta || {};
  const payloadMeta = typeof payload?.meta === "object" && payload?.meta !== null ? payload.meta : {};
  const meta = mergeMeta(topMeta, payloadMeta);
  const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();

  if (msg.port === "result.in") {
    handleResult(payload, meta, traceId);
    return;
  }

  if (msg.port === "query.in") {
    handleQuery(payload, meta, traceId);
  }
});