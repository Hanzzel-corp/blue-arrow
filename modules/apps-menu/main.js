import fs from "fs";
import path from "path";
import readline from "readline";
import { fileURLToPath } from "url";

const MODULE_ID = "apps.menu.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const APP_CACHE_PATH = path.resolve(__dirname, "../../logs/desktop-apps.json");
const MAX_APPS = 12;

function generateTraceId() {
  return `appsm_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

function btn(text, callbackData) {
  return { text, callback_data: callbackData };
}

function buildMeta(payload = {}) {
  return {
    source: "telegram",
    chat_id: payload?.chat_id || null,
    module: MODULE_ID,
    timestamp: safeIsoNow()
  };
}

function uiPayload(payload, text, inline_keyboard, traceId = null) {
  return {
    chat_id: payload?.chat_id || null,
    message_id: payload?.message_id || null,
    mode: payload?.message_id ? "edit" : "send",
    text,
    inline_keyboard,
    meta: buildMeta(payload),
    trace_id: traceId || generateTraceId()
  };
}

function commandPayload(payload, app, traceId = null) {
  return {
    command_id: `appm_${Date.now()}`,
    text: `abri ${app.label}`,
    source: "telegram",
    chat_id: payload?.chat_id || null,
    meta: {
      source: "telegram",
      chat_id: payload?.chat_id || null,
      ui_origin: "apps_menu",
      callback_data: payload?.data || null,
      app_id: app.id,
      app_command: app.command,
      target_application: app.label,
      target_application_label: app.label,
      resolved_application: {
        id: app.id,
        label: app.label,
        command: app.command,
        source: app.source || null
      }
    },
    trace_id: traceId || generateTraceId()
  };
}

function officeWriterCommandPayload(payload, traceId = null) {
  const nowIso = safeIsoNow();

  return {
    command_id: `appm_${Date.now()}`,
    text: "abrí writer y ayudame a redactar",
    source: "telegram",
    chat_id: payload?.chat_id || null,
    meta: {
      source: "telegram",
      chat_id: payload?.chat_id || null,
      ui_origin: "apps_menu",
      callback_data: payload?.data || null,
      app_id: "office_writer",
      app_command: "office.writer.generate",
      module: MODULE_ID,
      timestamp: nowIso
    },
    trace_id: traceId || generateTraceId()
  };
}

function officeWriterUiResult(payload, traceId = null) {
  const nowIso = safeIsoNow();

  return {
    task_id: `office_writer_ui_${Date.now()}`,
    status: "success",
    result: {
      response: "Writer IA listo. Ahora mandame el texto o pedido de redacción por mensaje."
    },
    meta: {
      source: "telegram",
      chat_id: payload?.chat_id || null,
      module: MODULE_ID,
      timestamp: nowIso
    },
    trace_id: traceId || generateTraceId()
  };
}

function loadAppsCache(traceId = null) {
  try {
    if (!fs.existsSync(APP_CACHE_PATH)) return [];

    const raw = fs.readFileSync(APP_CACHE_PATH, "utf8");
    const data = JSON.parse(raw);

    if (!Array.isArray(data)) return [];

    return data
      .filter((item) => item && item.id && item.label && item.command)
      .sort((a, b) => a.label.localeCompare(b.label))
      .slice(0, MAX_APPS);
  } catch (err) {
    emit("event.out", {
      level: "error",
      type: "apps_menu_cache_read_error",
      text: "Error leyendo cache de apps",
      error: String(err),
      cache_path: APP_CACHE_PATH,
      trace_id: traceId || generateTraceId(),
      meta: {
        source: "internal",
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
    return [];
  }
}

function buildAppsKeyboard(apps) {
  const rows = [];

  for (let i = 0; i < apps.length; i += 2) {
    const row = [btn(apps[i].label, `app:open:${apps[i].id}`)];

    if (apps[i + 1]) {
      row.push(btn(apps[i + 1].label, `app:open:${apps[i + 1].id}`));
    }

    rows.push(row);
  }

  rows.push([btn("📝 Writer IA", "app:office_writer")]);
  rows.push([btn("Volver", "menu:main")]);
  return rows;
}

function renderAppsMenu(payload, traceId = null) {
  const finalTraceId = traceId || generateTraceId();
  const apps = loadAppsCache(finalTraceId);

  if (!apps.length) {
    emit(
      "ui.response.out",
      uiPayload(
        payload,
        "No hay apps detectadas todavía en logs/desktop-apps.json",
        [
          [btn("📝 Writer IA", "app:office_writer")],
          [btn("Volver", "menu:main")]
        ],
        finalTraceId
      )
    );
    return;
  }

  emit(
    "ui.response.out",
    uiPayload(
      payload,
      "Apps detectadas",
      buildAppsKeyboard(apps),
      finalTraceId
    )
  );
}

function handleAppOpen(payload, appId, traceId = null) {
  const finalTraceId = traceId || generateTraceId();
  const apps = loadAppsCache(finalTraceId);
  const app = apps.find((item) => item.id === appId);

  if (!app) {
    emit(
      "ui.response.out",
      uiPayload(
        payload,
        "No encontré esa app en el cache actual.",
        [
          [btn("Apps", "menu:apps")],
          [btn("Menú", "menu:main")]
        ],
        finalTraceId
      )
    );
    return;
  }

  emit("command.out", commandPayload(payload, app, finalTraceId));
}

function handleOfficeWriter(payload, traceId = null) {
  const finalTraceId = traceId || generateTraceId();

  emit("command.out", officeWriterCommandPayload(payload, finalTraceId));

  emit("ui.response.out", officeWriterUiResult(payload, finalTraceId));
}

function handleCallback(payload, traceId = null) {
  const data = payload?.data || "";
  const finalTraceId = traceId || generateTraceId();

  if (data === "menu:apps") {
    renderAppsMenu(payload, finalTraceId);
    return;
  }

  if (data === "app:office_writer") {
    handleOfficeWriter(payload, finalTraceId);
    return;
  }

  if (data.startsWith("app:open:")) {
    const appId = data.slice("app:open:".length);
    handleAppOpen(payload, appId, finalTraceId);
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
      type: "apps_menu_invalid_json",
      text: "apps.menu.main recibió una línea JSON inválida",
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

  if (msg.port !== "callback.in") return;

  const traceId = msg?.trace_id || msg?.payload?.trace_id || generateTraceId();
  handleCallback(msg.payload || {}, traceId);
});