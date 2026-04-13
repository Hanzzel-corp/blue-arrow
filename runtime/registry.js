import fs from "fs";
import path from "path";

// Core modules para fallback de tier
const CORE_MODULES = new Set([
  "supervisor.main",
  "router.main",
  "agent.main",
  "planner.main",
  "safety.guard.main",
  "approval.main",
  "worker.python.desktop",
  "worker.python.terminal",
  "worker.python.system",
  "worker.python.browser",
  "memory.log.main",
  "ui.state.main",
  "interface.main",
  "interface.telegram"
]);

const VALID_LANGUAGES = new Set(["node", "python"]);
const VALID_TIERS = new Set(["core", "satellite"]);
const VALID_PRIORITIES = new Set(["critical", "high", "medium", "low"]);
const VALID_RESTART_POLICIES = new Set(["immediate", "lazy", "on_demand"]);

export function loadManifest(moduleDir) {
  const manifestPath = path.join(moduleDir, "manifest.json");

  if (!fs.existsSync(manifestPath)) {
    throw new Error(`Manifest no encontrado: ${manifestPath}`);
  }

  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (error) {
    throw new Error(`Manifest JSON inválido: ${error.message}`);
  }

  return manifest;
}

function normalizeTier(manifest) {
  const rawTier = manifest?.tier;
  if (VALID_TIERS.has(rawTier)) {
    return rawTier;
  }

  return CORE_MODULES.has(manifest.id) ? "core" : "satellite";
}

function normalizePriority(manifest, tier) {
  const rawPriority = manifest?.priority;
  if (VALID_PRIORITIES.has(rawPriority)) {
    return rawPriority;
  }

  return tier === "core" ? "high" : "low";
}

function normalizeRestartPolicy(manifest, tier) {
  const rawPolicy = manifest?.restart_policy || manifest?.restartPolicy;
  if (VALID_RESTART_POLICIES.has(rawPolicy)) {
    return rawPolicy;
  }

  return tier === "core" ? "immediate" : "lazy";
}

function validateManifest(manifest, moduleDir) {
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
    throw new Error("Manifest inválido: debe ser un objeto");
  }

  if (!manifest.id || typeof manifest.id !== "string") {
    throw new Error("Manifest incompleto: falta 'id'");
  }

  if (!manifest.entry || typeof manifest.entry !== "string") {
    throw new Error("Manifest incompleto: falta 'entry'");
  }

  if (!manifest.language || typeof manifest.language !== "string") {
    throw new Error("Manifest incompleto: falta 'language'");
  }

  if (!VALID_LANGUAGES.has(manifest.language)) {
    throw new Error(
      `Lenguaje no soportado '${manifest.language}' en ${manifest.id}`
    );
  }

  const entryPath = path.join(moduleDir, manifest.entry);
  if (!fs.existsSync(entryPath)) {
    throw new Error(`Entry no encontrado: ${manifest.entry}`);
  }
}

export function discoverModules(baseDir) {
  const modulesDir = path.join(baseDir, "modules");

  if (!fs.existsSync(modulesDir)) {
    throw new Error(`Directorio modules no encontrado: ${modulesDir}`);
  }

  const entries = fs.readdirSync(modulesDir, { withFileTypes: true });
  const registry = new Map();

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;

    const moduleDir = path.join(modulesDir, entry.name);

    try {
      const manifest = loadManifest(moduleDir);
      validateManifest(manifest, moduleDir);

      const tier = normalizeTier(manifest);
      const priority = normalizePriority(manifest, tier);
      const restartPolicy = normalizeRestartPolicy(manifest, tier);

      registry.set(manifest.id, {
        ...manifest,
        dir: moduleDir,
        tier,
        priority,
        restartPolicy
      });
    } catch (error) {
      throw new Error(
        `No se pudo cargar el módulo '${entry.name}': ${error.message}`
      );
    }
  }

  return registry;
}