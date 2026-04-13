import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { discoverModules } from "./registry.js";
import { RuntimeBus } from "./bus.js";
import { getLogger } from "./logger.js";
import { config, PROJECT_ROOT } from "./config.js";
import { TierManager, getBootstrapProfile } from "./tier_manager.js";

const logger = getLogger("runtime.main");

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const blueprintRelative =
  config.get("runtime.blueprint_file", "blueprints/system.v0.json");
const blueprintPath = path.resolve(PROJECT_ROOT, blueprintRelative);

let blueprint;
try {
  blueprint = JSON.parse(fs.readFileSync(blueprintPath, "utf8"));

  if (!Array.isArray(blueprint.modules) || !Array.isArray(blueprint.connections)) {
    throw new Error("Blueprint inválido: faltan modules o connections");
  }

  logger.info("Blueprint cargado", {
    modules_count: blueprint.modules.length,
    blueprint_path: blueprintPath
  });
} catch (error) {
  logger.error("Error cargando blueprint", { error: error.message });
  process.exit(1);
}

const registry = discoverModules(PROJECT_ROOT);
logger.info("Módulos descubiertos", { count: registry.size });

const missingModules = [];
for (const id of blueprint.modules) {
  if (!registry.has(id)) {
    missingModules.push(id);
  }
}

if (missingModules.length > 0) {
  logger.error("Módulos faltantes en el blueprint", { missing: missingModules });
  console.error("❌ Módulos faltantes:");
  missingModules.forEach((id) => console.error(`   - ${id}`));
  process.exit(1);
}

logger.info("Todos los módulos del blueprint están disponibles");

const bus = new RuntimeBus(registry, blueprint);
const tierManager = new TierManager(registry, blueprint);

// Obtener perfil de bootstrap (env var BOOTSTRAP_PROFILE)
const bootstrapProfile = process.env.BOOTSTRAP_PROFILE || "full";
const modulesToStart = getBootstrapProfile(bootstrapProfile, blueprint) || blueprint.modules;

// Filtrar solo módulos que existen
const availableModules = modulesToStart.filter(id => registry.has(id));
const missingInProfile = modulesToStart.filter(id => !registry.has(id));

if (missingInProfile.length > 0) {
  logger.warn("Módulos del perfil no disponibles", { missing: missingInProfile });
}

// Orden de arranque: core primero, luego satellites
const startupOrder = tierManager.getStartupOrder();
const filteredCore = startupOrder.core.filter(id => availableModules.includes(id));
const filteredSatellite = startupOrder.satellite.filter(id => availableModules.includes(id));

logger.info("Orden de arranque", {
  profile: bootstrapProfile,
  coreModules: filteredCore.length,
  satelliteModules: filteredSatellite.length
});

// 1. Arrancar core modules
let coreStarted = 0;
let coreFailed = [];

for (const id of filteredCore) {
  try {
    bus.startModule(registry.get(id));
    coreStarted += 1;
    logger.info(`Core iniciado: ${id}`);
  } catch (error) {
    coreFailed.push(id);
    logger.error(`Core FAILED: ${id}`, { error: error.message });
  }
}

// Verificar si podemos operar (core críticos)
const runningCore = new Set(filteredCore.filter(id => !coreFailed.includes(id)));
if (!tierManager.canOperate(runningCore)) {
  logger.error("Core críticos no disponibles, sistema no puede operar", {
    failed: coreFailed
  });
  console.error("❌ CRÍTICO: No se pueden iniciar módulos core esenciales");
  coreFailed.forEach(id => console.error(`   - ${id}`));
  process.exit(1);
}

// 2. Arrancar satellite modules (lazy, no bloquean)
let satelliteStarted = 0;
let satelliteFailed = [];

for (const id of filteredSatellite) {
  try {
    bus.startModule(registry.get(id));
    satelliteStarted += 1;
    logger.info(`Satellite iniciado: ${id}`);
  } catch (error) {
    satelliteFailed.push(id);
    logger.warn(`Satellite failed (no crítico): ${id}`, { error: error.message });
  }
}

const startedCount = coreStarted + satelliteStarted;

logger.info("Runtime iniciado", {
  profile: bootstrapProfile,
  core_started: coreStarted,
  core_failed: coreFailed.length,
  satellite_started: satelliteStarted,
  satellite_failed: satelliteFailed.length
});

console.log("✅ Runtime iniciado con éxito");
console.log(`📦 ${startedCount}/${availableModules.length} módulos activos (${bootstrapProfile})`);
console.log(`🔴 Core: ${coreStarted}/${filteredCore.length} | 🛰️  Satellite: ${satelliteStarted}/${filteredSatellite.length}`);

// Status message
const runningModules = new Set([
  ...filteredCore.filter(id => !coreFailed.includes(id)),
  ...filteredSatellite.filter(id => !satelliteFailed.includes(id))
]);
console.log(tierManager.getStatusMessage(runningModules));

// Health check periódico
setInterval(() => {
  const health = tierManager.getSystemHealth(runningModules);
  if (health.critical) {
    logger.error("Sistema en estado CRÍTICO", health);
  } else if (health.degraded) {
    logger.warn("Sistema degradado", health);
  }
}, 30000);
console.log("💡 Escribí un comando o usá Telegram para interactuar");
console.log("");

process.stdin.on("data", (chunk) => {
  const text = chunk.toString().trim();
  if (!text) return;

  logger.debug("Comando CLI recibido", { command: text });

  bus.send("interface.main", "command.in", {
    command_id: `cmd_${Date.now()}`,
    text,
    source: "cli"
  });
});

let shuttingDown = false;

async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;

  logger.info(`Recibida señal ${signal}, cerrando gracefully...`);

  try {
    await bus.shutdown();
  } catch (error) {
    logger.error("Error durante shutdown", { error: error.message });
  } finally {
    process.exit(0);
  }
}

process.on("SIGINT", () => {
  shutdown("SIGINT");
});

process.on("SIGTERM", () => {
  shutdown("SIGTERM");
});