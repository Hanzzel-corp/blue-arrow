import readline from "readline";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const MODULE_ID = "planner.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const APP_CACHE_PATH = path.resolve(__dirname, "../../logs/desktop-apps.json");

function generateTraceId() {
  return `planner_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenize(value) {
  return normalizeText(value)
    .split(" ")
    .map((x) => x.trim())
    .filter(Boolean);
}

function makeTaskId() {
  return `plan_${Date.now()}`;
}

function makeCommandId() {
  return `planner_${Date.now()}`;
}

function mergeMeta(topMeta = {}, payloadMeta = {}) {
  return {
    ...(topMeta || {}),
    ...(payloadMeta || {})
  };
}

function buildMeta(payload = {}, envelopeMeta = {}) {
  const merged = mergeMeta(envelopeMeta, payload?.meta || {});
  const activeApp = merged?.active_app || null;
  const resolvedApplication =
    merged?.resolved_application ||
    (activeApp
      ? {
          id: activeApp.id || null,
          label: activeApp.label || null,
          command: activeApp.command || null,
          source: activeApp.source || null,
          window_id: activeApp.window_id || null
        }
      : null);

  return {
    ...merged,
    source: payload?.source || merged?.source || "unknown",
    chat_id: payload?.chat_id || merged?.chat_id || null,
    active_app: activeApp || null,
    resolved_application: resolvedApplication,
    window_id:
      merged?.window_id ||
      activeApp?.window_id ||
      resolvedApplication?.window_id ||
      null,
    module: MODULE_ID,
    timestamp: safeIsoNow()
  };
}

function loadAppsCache(traceId = null, meta = null) {
  try {
    if (!fs.existsSync(APP_CACHE_PATH)) return [];
    const raw = fs.readFileSync(APP_CACHE_PATH, "utf8");
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed.filter(
      (item) => item && item.id && item.label && item.command
    );
  } catch (err) {
    emit("event.out", {
      level: "error",
      type: "planner_apps_cache_error",
      error: String(err),
      trace_id: traceId || generateTraceId(),
      meta: meta || {
        source: "internal",
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
    return [];
  }
}

function cleanAppRequest(normalized) {
  return normalized
    .replace(
      /^(abrir aplicacion|abrir app|abrir programa|abrir programa app|abrir|abri|abre|open)\s+/,
      ""
    )
    .replace(/^(la|el|app|aplicacion|programa)\s+/, "")
    .trim();
}

function aliasVariants(text) {
  const variants = new Set([text]);

  if (text.includes("calculadora")) {
    variants.add("calculator");
    variants.add("gnome calculator");
  }

  if (text.includes("terminal")) {
    variants.add("terminal");
    variants.add("gnome terminal");
    variants.add("gnome-terminal");
  }

  if (text.includes("consola")) {
    variants.add("terminal");
    variants.add("gnome terminal");
    variants.add("gnome-terminal");
    variants.add("console");
  }

  if (text.includes("reloj") || text.includes("relojes")) {
    variants.add("clocks");
    variants.add("gnome clocks");
  }

  if (text.includes("discos") || text.includes("disco")) {
    variants.add("disks");
    variants.add("gnome disks");
  }

  if (text.includes("archivos")) {
    variants.add("files");
    variants.add("nautilus");
  }

  if (text.includes("configuracion")) {
    variants.add("settings");
    variants.add("gnome control center");
  }

  if (text.includes("monitor del sistema")) {
    variants.add("system monitor");
    variants.add("gnome system monitor");
  }

  if (text.includes("editor de texto")) {
    variants.add("text editor");
    variants.add("gnome text editor");
  }

  if (
    text.includes("vscode") ||
    text.includes("vs code") ||
    text.includes("visual studio code")
  ) {
    variants.add("vs code");
    variants.add("vscode");
    variants.add("code");
  }

  if (
    text.includes("writer") ||
    text.includes("libreoffice writer") ||
    text.includes("office writer")
  ) {
    variants.add("writer");
    variants.add("libreoffice writer");
    variants.add("libreoffice");
  }

  return Array.from(variants);
}

function scoreAppCandidate(app, requestText) {
  const request = normalizeText(requestText);
  const requestTokens = tokenize(request);
  const variants = aliasVariants(request);

  const label = normalizeText(app.label || "");
  const command = normalizeText(app.command || "");
  const id = normalizeText(app.id || "");
  const generic = normalizeText(app.generic_name || "");
  const keywords = Array.isArray(app.keywords)
    ? app.keywords.map((x) => normalizeText(x)).filter(Boolean)
    : [];

  let score = 0;

  for (const v of variants) {
    if (!v) continue;

    if (label === v) score += 100;
    if (id === v) score += 95;
    if (command === v) score += 90;
    if (generic === v) score += 70;

    if (label.includes(v)) score += 50;
    if (id.includes(v)) score += 45;
    if (command.includes(v)) score += 40;
    if (generic.includes(v)) score += 30;

    for (const kw of keywords) {
      if (kw === v) score += 35;
      else if (kw.includes(v) || v.includes(kw)) score += 15;
    }
  }

  for (const token of requestTokens) {
    if (!token) continue;

    if (label.includes(token)) score += 10;
    if (id.includes(token)) score += 8;
    if (command.includes(token)) score += 6;
    if (generic.includes(token)) score += 5;

    for (const kw of keywords) {
      if (kw.includes(token)) score += 4;
    }
  }

  return score;
}

function resolveAppFromCatalog(rawText, traceId = null, meta = null) {
  const normalized = normalizeText(rawText);

  if (
    !/^(abrir aplicacion|abrir app|abrir programa|abrir|abri|abre|open)\b/.test(
      normalized
    )
  ) {
    return null;
  }

  const request = cleanAppRequest(normalized);
  if (!request) return null;

  const apps = loadAppsCache(traceId, meta);
  if (!apps.length) return null;

  const scored = apps
    .map((app) => ({
      app,
      score: scoreAppCandidate(app, request)
    }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score);

  if (!scored.length) return null;

  const best = scored[0];
  const second = scored[1] || null;

  if (best.score < 40) return null;
  if (second && best.score - second.score < 10 && best.score < 80) return null;

  return best.app;
}

function detectOfficePlan(rawText) {
  const normalized = normalizeText(rawText);

  const mentionsOffice =
    normalized.includes("writer") ||
    normalized.includes("libreoffice") ||
    normalized.includes("office") ||
    normalized.includes("documento");

  if (!mentionsOffice) {
    return null;
  }

  const wantsWriting =
    normalized.includes("redact") ||
    normalized.includes("escrib") ||
    normalized.includes("nota") ||
    normalized.includes("carta") ||
    normalized.includes("mejor") ||
    normalized.includes("texto") ||
    normalized.includes("contenido");

  if (wantsWriting) {
    return {
      kind: "single_step_plan",
      steps: [
        {
          step_id: "step_1",
          action: "office.writer.generate",
          params: {
            prompt: rawText,
            text: rawText
          }
        }
      ]
    };
  }

  return {
    kind: "single_step_plan",
    steps: [
      {
        step_id: "step_1",
        action: "office.open_writer",
        params: {}
      }
    ]
  };
}

function detectTerminalOpenPlan(normalized) {
  const isTerminalIntent =
    normalized === "terminal" ||
    normalized === "consola" ||
    /^(abrir|abri|abre|open)\s+(la\s+)?terminal\b/.test(normalized) ||
    /^(abrir|abri|abre|open)\s+(la\s+)?consola\b/.test(normalized);

  if (!isTerminalIntent) {
    return null;
  }

  return {
    kind: "single_step_plan",
    steps: [
      {
        step_id: "step_1",
        action: "open_application",
        params: {
          name: "terminal",
          resolved_app: {
            id: "terminal",
            label: "Terminal",
            command: "gnome-terminal",
            source: "intent_alias"
          }
        }
      }
    ],
    resolved_app: {
      id: "terminal",
      label: "Terminal",
      command: "gnome-terminal",
      source: "intent_alias"
    }
  };
}

function detectSystemMemoryPlan(normalized) {
  const asksSystemState =
    normalized.includes("estado del sistema") ||
    normalized.includes("estado sistema") ||
    normalized.includes("recurso") ||
    normalized.includes("recursos");

  const asksLastCommand =
    normalized.includes("ultimo comando") ||
    normalized.includes("último comando");

  const asksLastApp =
    normalized.includes("ultima app") ||
    normalized.includes("última app");

  const asksLastState =
    normalized.includes("ultimo estado") ||
    normalized.includes("último estado");

  if (asksSystemState && asksLastCommand) {
    return {
      kind: "multi_step",
      steps: [
        {
          step_id: "step_1",
          action: "monitor_resources",
          params: {}
        },
        {
          step_id: "step_2",
          action: "memory_query",
          params: { text: "ultimo comando" }
        }
      ]
    };
  }

  if (asksSystemState && asksLastApp) {
    return {
      kind: "multi_step",
      steps: [
        {
          step_id: "step_1",
          action: "monitor_resources",
          params: {}
        },
        {
          step_id: "step_2",
          action: "memory_query",
          params: { text: "ultima app" }
        }
      ]
    };
  }

  if (asksLastCommand && asksLastState) {
    return {
      kind: "multi_step",
      steps: [
        {
          step_id: "step_1",
          action: "memory_query",
          params: { text: "ultimo comando" }
        },
        {
          step_id: "step_2",
          action: "memory_query",
          params: { text: "ultimo estado" }
        }
      ]
    };
  }

  return null;
}

function ensureUrl(raw) {
  const trimmed = String(raw || "").trim();
  if (!trimmed) return trimmed;
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

function detectWebPlan(normalized) {
  const webSearchMatch = normalized.match(/abrir web (.+?) y buscar (.+)/);
  if (webSearchMatch) {
    return {
      kind: "single_step_plan",
      steps: [
        {
          step_id: "step_1",
          action: "open_url",
          params: {
            url: ensureUrl(webSearchMatch[1].trim())
          }
        }
      ],
      note: "search_web_text todavía no está soportado por el runner"
    };
  }

  const openWebMatch = normalized.match(/abrir web (.+)/);
  if (openWebMatch) {
    return {
      kind: "single_step_plan",
      steps: [
        {
          step_id: "step_1",
          action: "open_url",
          params: {
            url: ensureUrl(openWebMatch[1].trim())
          }
        }
      ]
    };
  }

  return null;
}

function detectFilePlan(normalized) {
  const searchOpenMatch = normalized.match(
    /buscar archivo (.+?) y abrir (el primero|primero)/
  );

  if (searchOpenMatch) {
    return {
      kind: "single_step_plan",
      steps: [
        {
          step_id: "step_1",
          action: "search_file",
          params: {
            filename: searchOpenMatch[1].trim()
          }
        }
      ],
      note: "open_first_search_result todavía no está soportado por el runner"
    };
  }

  const searchFileMatch = normalized.match(/buscar archivo (.+)/);
  if (searchFileMatch) {
    return {
      kind: "single_step_plan",
      steps: [
        {
          step_id: "step_1",
          action: "search_file",
          params: {
            filename: searchFileMatch[1].trim()
          }
        }
      ]
    };
  }

  return null;
}

function detectTerminalCommandPlan(normalized) {
  const prefixes = [
    { prefix: "ejecutar en terminal:", execute: true },
    { prefix: "ejecutar en terminal", execute: true },
    { prefix: "run in terminal:", execute: true },
    { prefix: "run in terminal", execute: true },
    { prefix: "terminal:", execute: true },
    { prefix: "escribir en terminal:", execute: false },
    { prefix: "escribir en terminal", execute: false },
    { prefix: "type in terminal:", execute: false },
    { prefix: "type in terminal", execute: false }
  ];

  for (const item of prefixes) {
    if (!normalized.startsWith(item.prefix)) continue;

    const command = normalized.slice(item.prefix.length).trim();
    if (!command) return null;

    return {
      kind: "single_step_plan",
      steps: [
        {
          step_id: "step_1",
          action: "terminal.write_command",
          params: {
            command,
            execute: item.execute
          }
        }
      ]
    };
  }

  return null;
}

function detectAppPlan(rawText, traceId = null, meta = null) {
  const normalized = normalizeText(rawText);

  if (
    !/^(abrir aplicacion|abrir app|abrir programa|abrir|abri|abre|open)\b/.test(
      normalized
    )
  ) {
    return null;
  }

  const request = cleanAppRequest(normalized);
  if (!request) return null;

  const resolvedApp = resolveAppFromCatalog(normalized, traceId, meta);
  if (!resolvedApp) return null;

  return {
    kind: "single_step_plan",
    steps: [
      {
        step_id: "step_1",
        action: "open_application",
        params: {
          name: resolvedApp.command || resolvedApp.label,
          resolved_app: {
            id: resolvedApp.id || null,
            label: resolvedApp.label || null,
            command: resolvedApp.command || null,
            source: resolvedApp.source || null
          }
        }
      }
    ],
    resolved_app: {
      id: resolvedApp.id || null,
      label: resolvedApp.label || null,
      command: resolvedApp.command || null,
      source: resolvedApp.source || null
    }
  };
}

function detectPlan(text, traceId = null, meta = null) {
  const normalized = normalizeText(text);

  return (
    detectOfficePlan(text) ||
    detectTerminalCommandPlan(normalized) ||
    detectTerminalOpenPlan(normalized) ||
    detectSystemMemoryPlan(normalized) ||
    detectWebPlan(normalized) ||
    detectFilePlan(normalized) ||
    detectAppPlan(normalized, traceId, meta) ||
    null
  );
}

function emitPassthroughCommand(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const text = payload?.text || "";
  const meta = buildMeta(payload, envelopeMeta);
  const traceId = incomingTraceId || generateTraceId();

  emit("command.out", {
    command_id: payload?.command_id || makeCommandId(),
    text,
    source: payload?.source || meta?.source || "unknown",
    chat_id: payload?.chat_id || meta?.chat_id || null,
    meta: {
      ...meta,
      planner: {
        planned: false,
        mode: "passthrough"
      }
    },
    trace_id: traceId
  });

  emit("event.out", {
    level: "info",
    type: "planner_passthrough",
    text,
    meta,
    trace_id: traceId
  });
}

function emitPlan(payload = {}, envelopeMeta = {}, detectedPlan, incomingTraceId = null) {
  const text = payload?.text || "";
  const meta = buildMeta(payload, envelopeMeta);
  const kind =
    detectedPlan.kind ||
    (detectedPlan.steps.length > 1 ? "multi_step" : "single_step_plan");

  const traceId = incomingTraceId || generateTraceId();
  const taskId = payload?.task_id || payload?.plan_id || makeTaskId();

  emit("plan.out", {
    task_id: taskId,
    plan_id: taskId,
    kind,
    original_command: text,
    steps: detectedPlan.steps,
    note: detectedPlan.note || null,
    resolved_app: detectedPlan.resolved_app || null,
    meta: {
      ...meta,
      planner: {
        planned: true,
        mode: kind
      }
    },
    trace_id: traceId
  });

  emit("event.out", {
    level: "info",
    type:
      kind === "multi_step"
        ? "planner_multi_step_detected"
        : "planner_single_step_plan_detected",
    text,
    step_count: detectedPlan.steps.length,
    note: detectedPlan.note || null,
    resolved_app: detectedPlan.resolved_app || null,
    meta,
    trace_id: traceId
  });

  emit("signal.out", {
    type: "plan_ready",
    payload: {
      task_id: taskId,
      plan_id: taskId,
      step_count: detectedPlan.steps.length
    },
    meta,
    trace_id: traceId
  });
}

function handleCommand(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const text = payload?.text || "";
  const detectedPlan = detectPlan(text, incomingTraceId, envelopeMeta);

  if (!detectedPlan) {
    emitPassthroughCommand(payload, envelopeMeta, incomingTraceId);
    return;
  }

  emitPlan(payload, envelopeMeta, detectedPlan, incomingTraceId);
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (err) {
    emit("event.out", {
      level: "error",
      type: "planner_parse_error",
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

  if (msg.port === "command.in") {
    const payload = msg?.payload || {};
    const envelopeMeta = msg?.meta || {};
    const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();
    handleCommand(payload, envelopeMeta, traceId);
  }
});