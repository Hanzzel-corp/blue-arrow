import fs from "fs/promises";
import path from "path";
import readline from "readline";
import { fileURLToPath } from "url";

const MODULE_ID = "project.audit.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, "../../");

function generateTraceId() {
  return `audit_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

function emit(port, payload) {
  // Asegurar trace_id y meta en el nivel superior para cumplir contrato
  const traceId = payload?.trace_id || generateTraceId();
  const meta = payload?.meta || {
    source: "internal",
    timestamp: new Date().toISOString(),
    module: "project.audit.main"
  };
  // Eliminar trace_id y meta del payload si existen para evitar duplicados
  const { trace_id: _, meta: __, ...cleanPayload } = payload || {};
  process.stdout.write(
    JSON.stringify({
      module: "project.audit.main",
      port,
      trace_id: traceId,
      meta,
      payload: cleanPayload
    }) + "\n"
  );
}

function now() {
  return Date.now();
}

function normalizeText(text) {
  return (text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function parseAuditCommand(text) {
  const normalized = normalizeText(text);

  if (normalized === "auditar proyecto") {
    return { mode: "project", moduleId: null };
  }

  const m = normalized.match(/^auditar modulo\s+(.+)$/i);
  if (m) {
    return { mode: "module", moduleId: m[1].trim() };
  }

  return null;
}

async function walk(dir) {
  const out = [];
  let entries = [];

  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }

  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...(await walk(full)));
    } else {
      out.push(full);
    }
  }

  return out;
}

async function findManifestFiles(modulesRoot) {
  const files = await walk(modulesRoot);
  return files.filter((f) => path.basename(f) === "manifest.json");
}

async function loadJson(filePath) {
  const raw = await fs.readFile(filePath, "utf8");
  return JSON.parse(raw);
}

function splitEndpoint(endpoint) {
  const [moduleId, port] = String(endpoint || "").split(":");
  return {
    moduleId: moduleId || null,
    port: port || null
  };
}

function rel(root, target) {
  return path.relative(root, target).replace(/\\/g, "/");
}

function pushIssue(list, type, message, extra = {}) {
  list.push({
    type,
    message,
    ...extra
  });
}

const AUDIT_RULES = {
  ignore_input_without_source: new Set([
    "interface.main:command.in"
  ]),
  ignore_output_without_target: new Set([
    "router.main:native.action.out",
    "ai.intent.main:analysis.out",
    "approval.main:approval.request.out"
  ]),
  ignore_code_uses_undeclared_output: new Set([
    "interface.telegram:event.out"
  ])
};

function shouldIgnore(ruleSet, key) {
  return ruleSet.has(key);
}

function collectMatches(regex, text) {
  const values = [];
  for (const match of text.matchAll(regex)) {
    values.push(match[1]);
  }
  return [...new Set(values)];
}

function hasConnection(connections, from, to) {
  return connections.some((c) => c.from === from && c.to === to);
}

function incomingFrom(connections, to) {
  return connections
    .filter((c) => c.to === to)
    .map((c) => c.from);
}

async function loadModuleRegistry(projectRoot) {
  const modulesRoot = path.join(projectRoot, "modules");
  const manifestFiles = await findManifestFiles(modulesRoot);

  const registry = new Map();

  for (const manifestPath of manifestFiles) {
    try {
      const manifest = await loadJson(manifestPath);
      const folder = path.dirname(manifestPath);

      if (!manifest?.id) continue;

      registry.set(manifest.id, {
        id: manifest.id,
        folder,
        manifestPath,
        manifest,
        entryPath: manifest.entry ? path.join(folder, manifest.entry) : null
      });
    } catch {
      // se reporta indirectamente por ausencia o manifest inválido
    }
  }

  return { registry, modulesRoot };
}

function isRelatedToModule(item, focusModuleId) {
  if (!focusModuleId || !item) return true;

  const directModule = item.module === focusModuleId;
  const fromMatch = item.from?.startsWith(`${focusModuleId}:`);
  const toMatch = item.to?.startsWith(`${focusModuleId}:`);
  const pathMatch = item.path?.includes(focusModuleId);

  return Boolean(directModule || fromMatch || toMatch || pathMatch);
}

async function auditProject(projectRoot, focusModuleId = null) {
  const blueprintPath = path.join(projectRoot, "blueprints", "system.v0.json");
  const results = {
    ok: true,
    summary: {
      modules_declared: 0,
      modules_found: 0,
      errors: 0,
      warnings: 0,
      infos: 0
    },
    errors: [],
    warnings: [],
    info: []
  };

  let blueprint;
  try {
    blueprint = await loadJson(blueprintPath);
  } catch (err) {
    pushIssue(results.errors, "missing_blueprint", `No pude leer ${rel(projectRoot, blueprintPath)}`, {
      path: rel(projectRoot, blueprintPath),
      error: String(err)
    });
    results.ok = false;
    results.summary.errors = results.errors.length;
    return results;
  }

  const declaredModules = Array.isArray(blueprint?.modules) ? blueprint.modules : [];
  const connections = Array.isArray(blueprint?.connections) ? blueprint.connections : [];

  const { registry } = await loadModuleRegistry(projectRoot);

  results.summary.modules_declared = declaredModules.length;
  results.summary.modules_found = registry.size;

  for (const moduleId of declaredModules) {
    if (!registry.has(moduleId)) {
      pushIssue(results.errors, "missing_module_folder", `El módulo declarado ${moduleId} no tiene manifest encontrado en modules/`, {
        module: moduleId
      });
    }
  }

  for (const [moduleId, mod] of registry.entries()) {
    if (!declaredModules.includes(moduleId)) {
      pushIssue(results.warnings, "orphan_module_folder", `La carpeta ${rel(projectRoot, mod.folder)} existe pero ${moduleId} no está declarado en el blueprint`, {
        module: moduleId,
        path: rel(projectRoot, mod.folder)
      });
    }
  }

  for (const moduleId of declaredModules) {
    const mod = registry.get(moduleId);
    if (!mod) continue;

    const manifest = mod.manifest || {};

    if (manifest.id !== moduleId) {
      pushIssue(results.errors, "manifest_id_mismatch", `El manifest de ${moduleId} no coincide con el id esperado`, {
        module: moduleId,
        path: rel(projectRoot, mod.manifestPath)
      });
    }

    if (!manifest.entry) {
      pushIssue(results.errors, "missing_entry_field", `El módulo ${moduleId} no declara entry en manifest.json`, {
        module: moduleId,
        path: rel(projectRoot, mod.manifestPath)
      });
    }

    if (mod.entryPath) {
      try {
        await fs.access(mod.entryPath);
      } catch {
        pushIssue(results.errors, "missing_entry_file", `Falta el entry ${rel(projectRoot, mod.entryPath)} para ${moduleId}`, {
          module: moduleId,
          path: rel(projectRoot, mod.entryPath)
        });
      }
    }
  }

  const connectionSeen = new Set();
  const incomingByPort = new Map();
  const outgoingByPort = new Map();

  for (const conn of connections) {
    const from = splitEndpoint(conn.from);
    const to = splitEndpoint(conn.to);

    const key = `${conn.from} -> ${conn.to}`;
    if (connectionSeen.has(key)) {
      pushIssue(results.warnings, "duplicate_connection", `Conexión duplicada ${key}`, {
        from: conn.from,
        to: conn.to
      });
    }
    connectionSeen.add(key);

    if (!registry.has(from.moduleId)) {
      pushIssue(results.errors, "connection_from_missing_module", `La conexión sale de un módulo inexistente: ${conn.from}`, {
        from: conn.from
      });
    }

    if (!registry.has(to.moduleId)) {
      pushIssue(results.errors, "connection_to_missing_module", `La conexión entra a un módulo inexistente: ${conn.to}`, {
        to: conn.to
      });
    }

    if (registry.has(from.moduleId)) {
      const manifest = registry.get(from.moduleId).manifest;
      const outputs = Array.isArray(manifest.outputs) ? manifest.outputs : [];
      if (!outputs.includes(from.port)) {
        pushIssue(results.errors, "undeclared_output_port", `El puerto ${from.port} no está declarado en outputs de ${from.moduleId}`, {
          module: from.moduleId,
          port: from.port
        });
      }
    }

    if (registry.has(to.moduleId)) {
      const manifest = registry.get(to.moduleId).manifest;
      const inputs = Array.isArray(manifest.inputs) ? manifest.inputs : [];
      if (!inputs.includes(to.port)) {
        pushIssue(results.errors, "undeclared_input_port", `El puerto ${to.port} no está declarado en inputs de ${to.moduleId}`, {
          module: to.moduleId,
          port: to.port
        });
      }
    }

    const incomingKey = `${to.moduleId}:${to.port}`;
    const outgoingKey = `${from.moduleId}:${from.port}`;

    if (!incomingByPort.has(incomingKey)) incomingByPort.set(incomingKey, []);
    incomingByPort.get(incomingKey).push(conn.from);

    if (!outgoingByPort.has(outgoingKey)) outgoingByPort.set(outgoingKey, []);
    outgoingByPort.get(outgoingKey).push(conn.to);
  }

  for (const moduleId of declaredModules) {
    const mod = registry.get(moduleId);
    if (!mod) continue;

    const inputs = Array.isArray(mod.manifest.inputs) ? mod.manifest.inputs : [];
    const outputs = Array.isArray(mod.manifest.outputs) ? mod.manifest.outputs : [];

    for (const input of inputs) {
      const key = `${moduleId}:${input}`;
      if (!incomingByPort.has(key) && !shouldIgnore(AUDIT_RULES.ignore_input_without_source, key)) {
        pushIssue(results.warnings, "input_without_source", `El input ${key} no recibe ninguna conexión`, {
          module: moduleId,
          port: input
        });
      }
    }

    for (const output of outputs) {
      const key = `${moduleId}:${output}`;
      if (!outgoingByPort.has(key) && !shouldIgnore(AUDIT_RULES.ignore_output_without_target, key)) {
        pushIssue(results.warnings, "output_without_target", `El output ${key} no tiene destino`, {
          module: moduleId,
          port: output
        });
      }
    }
  }

  {
    const routerPlanIn = "router.main:plan.in";
    const allowedRouterPlanSources = new Set([
      "safety.guard.main:approved.plan.out",
      "approval.main:approved.plan.out"
    ]);

    const routerPlanIncoming = incomingFrom(connections, routerPlanIn);

    if (routerPlanIncoming.length === 0) {
      pushIssue(
        results.errors,
        "router_plan_in_without_source",
        "router.main:plan.in no recibe ninguna conexión válida",
        { port: routerPlanIn }
      );
    }

    for (const from of routerPlanIncoming) {
      if (!allowedRouterPlanSources.has(from)) {
        pushIssue(
          results.errors,
          "router_plan_in_invalid_source",
          `router.main:plan.in debe recibir solo desde safety.guard.main:approved.plan.out o approval.main:approved.plan.out, pero recibe desde ${from}`,
          { port: routerPlanIn, from }
        );
      }
    }

    if (
      !hasConnection(
        connections,
        "safety.guard.main:approved.plan.out",
        "router.main:plan.in"
      )
    ) {
      pushIssue(
        results.errors,
        "missing_safety_to_router",
        "Falta la conexión safety.guard.main:approved.plan.out -> router.main:plan.in",
        {
          from: "safety.guard.main:approved.plan.out",
          to: "router.main:plan.in"
        }
      );
    }

    if (
      !hasConnection(
        connections,
        "safety.guard.main:blocked.plan.out",
        "approval.main:blocked.plan.in"
      )
    ) {
      pushIssue(
        results.errors,
        "missing_safety_to_approval",
        "Falta la conexión safety.guard.main:blocked.plan.out -> approval.main:blocked.plan.in",
        {
          from: "safety.guard.main:blocked.plan.out",
          to: "approval.main:blocked.plan.in"
        }
      );
    }

    if (
      !hasConnection(
        connections,
        "approval.main:rejected.result.out",
        "supervisor.main:result.in"
      )
    ) {
      pushIssue(
        results.warnings,
        "missing_approval_rejected_to_supervisor",
        "approval.main:rejected.result.out no está conectado a supervisor.main:result.in",
        {
          from: "approval.main:rejected.result.out",
          to: "supervisor.main:result.in"
        }
      );
    }
  }

  for (const moduleId of declaredModules) {
    const mod = registry.get(moduleId);
    if (!mod?.entryPath) continue;

    let source = "";
    try {
      source = await fs.readFile(mod.entryPath, "utf8");
    } catch {
      continue;
    }

    const moduleEmitMatches = [
      ...collectMatches(/module:\s*"([^"]+)"/g, source),
      ...collectMatches(/module:\s*'([^']+)'/g, source)
    ];

    for (const emittedName of moduleEmitMatches) {
      if (emittedName !== moduleId) {
        pushIssue(
          results.warnings,
          "emitted_module_name_mismatch",
          `El código de ${moduleId} emite module "${emittedName}" y no coincide con su id`,
          {
            module: moduleId,
            path: rel(projectRoot, mod.entryPath)
          }
        );
      }
    }

    const emittedPorts = collectMatches(/emit\(\s*["'`]([^"'`]+)["'`]/g, source);
    const declaredOutputs = Array.isArray(mod.manifest.outputs) ? mod.manifest.outputs : [];
    for (const port of emittedPorts) {
      const key = `${moduleId}:${port}`;
      if (!declaredOutputs.includes(port) && !shouldIgnore(AUDIT_RULES.ignore_code_uses_undeclared_output, key)) {
        pushIssue(
          results.warnings,
          "code_uses_undeclared_output",
          `El módulo ${moduleId} emite ${port} pero no está en manifest.outputs`,
          {
            module: moduleId,
            port
          }
        );
      }
    }

    const inputChecks = [
      ...collectMatches(/msg\.port\s*===\s*["'`]([^"'`]+)["'`]/g, source),
      ...collectMatches(/\bport\s*===\s*["'`]([^"'`]+)["'`]/g, source)
    ];
    const declaredInputs = Array.isArray(mod.manifest.inputs) ? mod.manifest.inputs : [];
    for (const port of [...new Set(inputChecks)]) {
      if (!declaredInputs.includes(port)) {
        pushIssue(
          results.warnings,
          "code_uses_undeclared_input",
          `El módulo ${moduleId} escucha ${port} pero no está en manifest.inputs`,
          {
            module: moduleId,
            port
          }
        );
      }
    }

    if (
      /\bconsole\.log\s*\(/.test(source) ||
      /\bconsole\.warn\s*\(/.test(source) ||
      /\bprint\s*\(/.test(source)
    ) {
      pushIssue(
        results.warnings,
        "stdout_contamination_risk",
        `El módulo ${moduleId} usa salida potencialmente contaminante para stdout`,
        {
          module: moduleId,
          path: rel(projectRoot, mod.entryPath)
        }
      );
    }
  }

  if (focusModuleId) {
    results.errors = results.errors.filter((item) => isRelatedToModule(item, focusModuleId));
    results.warnings = results.warnings.filter((item) => isRelatedToModule(item, focusModuleId));
    results.info = results.info.filter((item) => isRelatedToModule(item, focusModuleId));

    const mod = registry.get(focusModuleId);
    if (!mod) {
      pushIssue(results.errors, "module_not_found", `No encontré el módulo ${focusModuleId}`, {
        module: focusModuleId
      });
    } else {
      pushIssue(results.info, "module_found", `Módulo ${focusModuleId} encontrado en ${rel(projectRoot, mod.folder)}`, {
        module: focusModuleId,
        path: rel(projectRoot, mod.folder)
      });
    }
  }

  results.summary.errors = results.errors.length;
  results.summary.warnings = results.warnings.length;
  results.summary.infos = results.info.length;
  results.ok = results.errors.length === 0;

  return results;
}

function renderReport(report, mode, moduleId = null) {
  const title =
    mode === "module"
      ? `🔎 Auditoría del módulo ${moduleId}`
      : "🔎 Auditoría del proyecto";

  const lines = [
    title,
    `OK: ${report.ok ? "sí" : "no"}`,
    `Módulos declarados: ${report.summary.modules_declared}`,
    `Módulos encontrados: ${report.summary.modules_found}`,
    `Errores: ${report.summary.errors}`,
    `Warnings: ${report.summary.warnings}`,
    `Info: ${report.summary.infos}`
  ];

  if (report.errors.length) {
    lines.push("", "Errores:");
    for (const item of report.errors.slice(0, 8)) {
      lines.push(`- ${item.message}`);
    }
  }

  if (report.warnings.length) {
    lines.push("", "Warnings:");
    for (const item of report.warnings.slice(0, 8)) {
      lines.push(`- ${item.message}`);
    }
  }

  if (report.info.length) {
    lines.push("", "Info:");
    for (const item of report.info.slice(0, 8)) {
      lines.push(`- ${item.message}`);
    }
  }

  return lines.join("\n");
}

async function handleAudit(payload) {
  const rawText = payload?.text || "";
  const meta = {
    source: payload?.source || payload?.meta?.source || "cli",
    chat_id: payload?.chat_id || payload?.meta?.chat_id || null
  };

  const parsed = parseAuditCommand(rawText);
  if (!parsed) return;

  const report = await auditProject(PROJECT_ROOT, parsed.moduleId);
  const text = renderReport(report, parsed.mode, parsed.moduleId);
  const traceId = generateTraceId();

  emit("event.out", {
    level: report.ok ? "info" : "warn",
    type: "project_audit_completed",
    audit: {
      mode: parsed.mode,
      module_id: parsed.moduleId,
      ok: report.ok,
      summary: report.summary
    },
    trace_id: traceId
  });

  emit("event.out", {
    level: report.ok ? "info" : "warn",
    type: "project_audit_response_ready",
    text: "Project audit generó una respuesta para la interfaz",
    meta,
    trace_id: traceId
  });

  emit("response.out", {
    task_id: `audit_${now()}`,
    status: "success",
    result: {
      echo: text,
      audit_report: report
    },
    meta,
    trace_id: traceId
  });
}

rl.on("line", async (line) => {
  if (!line.trim()) return;

  try {
    const msg = JSON.parse(line);
    if (msg.port !== "audit.in") return;
    await handleAudit(msg.payload);
  } catch (err) {
    const errorTraceId = generateTraceId();
    emit("event.out", {
      level: "error",
      type: "project_audit_error",
      error: String(err),
      trace_id: errorTraceId
    });

    emit("response.out", {
      task_id: `audit_${now()}`,
      status: "error",
      error: `Falló la auditoría: ${String(err)}`,
      meta: {
        source: "cli",
        chat_id: null
      },
      trace_id: errorTraceId
    });
  }
});