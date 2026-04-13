/**
 * Tier Manager - Gestión de módulos core vs satellite
 * 
 * Responsabilidades:
 * - Separar módulos por tier (core vs satellite)
 * - Orden de arranque (core primero)
 * - Health checks diferenciados
 * - Degradación graceful
 */

import { getLogger } from "./logger.js";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const logger = getLogger("runtime.tier");

// Cargar configuración de perfiles
let PROFILES_CONFIG = null;
try {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);
  const profilesPath = join(__dirname, "..", "config", "profiles.json");
  const profilesData = JSON.parse(readFileSync(profilesPath, "utf8"));
  PROFILES_CONFIG = profilesData.profiles;
} catch (err) {
  logger.warn("No se pudo cargar config/profiles.json, usando defaults", { error: err.message });
}

// Módulos core hardcodeados (fallback si no está en manifest)
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

export class TierManager {
  constructor(registry, blueprint) {
    this.registry = registry;
    this.blueprint = blueprint;
    this.coreModules = new Map();
    this.satelliteModules = new Map();
    this.criticalState = false;
    
    this._classifyModules();
  }

  _classifyModules() {
    // Clasifica módulos en core vs satellite según manifest o fallback
    for (const moduleId of this.blueprint.modules) {
      const mod = this.registry.get(moduleId);
      if (!mod) continue;

      // Usar tier del manifest o determinar por fallback
      const tier = mod.tier || (CORE_MODULES.has(moduleId) ? "core" : "satellite");
      
      if (tier === "core") {
        this.coreModules.set(moduleId, mod);
      } else {
        this.satelliteModules.set(moduleId, mod);
      }
    }

    logger.info("Módulos clasificados por tier", {
      core: this.coreModules.size,
      satellite: this.satelliteModules.size,
      coreList: Array.from(this.coreModules.keys())
    });
  }

  /**
   * Obtiene orden de arranque: core primero (por prioridad), luego satellites
   */
  getStartupOrder() {
    // Core ordenados por prioridad (critical > high > medium > low)
    const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
    
    const sortedCore = Array.from(this.coreModules.values()).sort((a, b) => {
      const prioA = priorityOrder[a.priority] ?? 999;
      const prioB = priorityOrder[b.priority] ?? 999;
      return prioA - prioB;
    });

    const sortedSatellite = Array.from(this.satelliteModules.values()).sort((a, b) => {
      const prioA = priorityOrder[a.priority] ?? 999;
      const prioB = priorityOrder[b.priority] ?? 999;
      return prioA - prioB;
    });

    return {
      core: sortedCore.map(m => m.id),
      satellite: sortedSatellite.map(m => m.id),
      all: [...sortedCore.map(m => m.id), ...sortedSatellite.map(m => m.id)]
    };
  }

  /**
   * Determina si un módulo es core
   */
  isCore(moduleId) {
    return this.coreModules.has(moduleId);
  }

  /**
   * Determina si un módulo es satellite
   */
  isSatellite(moduleId) {
    return this.satelliteModules.has(moduleId);
  }

  /**
   * Obtiene política de restart para un módulo
   */
  getRestartPolicy(moduleId) {
    const mod = this.registry.get(moduleId);
    if (!mod) return "lazy";
    
    return mod.restartPolicy || (this.isCore(moduleId) ? "immediate" : "lazy");
  }

  /**
   * Obtiene delay de restart según tier
   */
  getRestartDelay(moduleId) {
    const policy = this.getRestartPolicy(moduleId);
    
    switch (policy) {
      case "immediate":
        return 1000; // 1 segundo para core
      case "lazy":
        return 10000; // 10 segundos para satellite
      case "on_demand":
        return -1; // No auto-restart
      default:
        return this.isCore(moduleId) ? 5000 : 30000;
    }
  }

  /**
   * Maneja caída de módulo y determina impacto
   */
  handleModuleExit(moduleId, exitCode) {
    const isCore = this.isCore(moduleId);
    
    if (isCore) {
      this.criticalState = true;
      logger.error(`Módulo CORE caído: ${moduleId}`, {
        exitCode,
        criticalState: true,
        impact: "Sistema degradado críticamente"
      });
      
      return {
        tier: "core",
        critical: true,
        autoRestart: true,
        restartDelay: this.getRestartDelay(moduleId),
        impact: "critical"
      };
    } else {
      logger.warn(`Módulo SATELLITE caído: ${moduleId}`, {
        exitCode,
        criticalState: false,
        impact: "Feature no disponible"
      });
      
      return {
        tier: "satellite",
        critical: false,
        autoRestart: this.getRestartPolicy(moduleId) !== "on_demand",
        restartDelay: this.getRestartDelay(moduleId),
        impact: "degraded"
      };
    }
  }

  /**
   * Health check: estado del sistema
   */
  getSystemHealth(runningModules) {
    const runningCore = Array.from(this.coreModules.keys()).filter(id => 
      runningModules.has(id)
    );
    const failedCore = Array.from(this.coreModules.keys()).filter(id => 
      !runningModules.has(id)
    );
    
    const runningSatellite = Array.from(this.satelliteModules.keys()).filter(id => 
      runningModules.has(id)
    );
    const failedSatellite = Array.from(this.satelliteModules.keys()).filter(id => 
      !runningModules.has(id)
    );

    const healthy = failedCore.length === 0;
    const degraded = failedCore.length === 0 && failedSatellite.length > 0;
    const critical = failedCore.length > 0;

    return {
      status: critical ? "critical" : (degraded ? "degraded" : "healthy"),
      healthy,
      degraded,
      critical,
      core: {
        total: this.coreModules.size,
        running: runningCore.length,
        failed: failedCore.length,
        list: failedCore
      },
      satellite: {
        total: this.satelliteModules.size,
        running: runningSatellite.length,
        failed: failedSatellite.length
      }
    };
  }

  /**
   * Verifica si el sistema puede operar (al menos core críticos funcionando)
   */
  canOperate(runningModules) {
    // Core mínimos para operar
    const criticalCore = ["router.main", "agent.main", "supervisor.main"];
    return criticalCore.every(id => runningModules.has(id));
  }

  /**
   * Obtiene mensaje de estado para UI
   */
  getStatusMessage(runningModules) {
    const health = this.getSystemHealth(runningModules);
    
    if (health.critical) {
      const failedList = health.core.list.slice(0, 3).join(", ");
      return `🔴 CRÍTICO: ${failedList} no responde(n)`;
    } else if (health.degraded) {
      return `🟡 DEGRADADO: ${health.satellite.failed} satellites offline`;
    } else {
      return `🟢 OK: ${health.core.running} core, ${health.satellite.running} satellites`;
    }
  }
}

// Perfiles de bootstrap - cargados desde config/profiles.json
export function getBootstrapProfile(profileName, blueprint) {
  // Usar configuración de profiles.json si está disponible
  const config = PROFILES_CONFIG?.[profileName];
  
  if (config?.modules) {
    logger.info(`Perfil ${profileName} cargado desde profiles.json`, {
      moduleCount: config.modules.length,
      description: config.description
    });
    return config.modules;
  }
  
  // Fallback a lógica anterior
  if (profileName === "standard") {
    return blueprint.modules.filter(id => {
      const isAISatellite = id.startsWith("ai.") && id !== "ai.intent.main";
      const isGamification = id === "gamification.main";
      return !isAISatellite && !isGamification;
    });
  }
  
  if (profileName === "minimal") {
    return blueprint.modules.filter(id => {
      const tier = PROFILES_CONFIG?.minimal?.excluded_categories || [];
      const isSatellite = tier.includes("satellite");
      const isAI = id.startsWith("ai.");
      const isGamification = id === "gamification.main";
      const isTelegram = id.includes("telegram");
      const isMenu = id.includes("menu");
      return !isSatellite && !isAI && !isGamification && !isTelegram && !isMenu;
    });
  }
  
  return blueprint.modules;
}

export function getProfileInfo(profileName) {
  const config = PROFILES_CONFIG?.[profileName];
  if (!config) return null;
  
  return {
    name: config.name,
    description: config.description,
    useCases: config.use_cases,
    moduleCount: config.modules?.length || "all",
    resourceLimits: config.resource_limits,
    healthCheck: config.health_check
  };
}

export function listProfiles() {
  if (!PROFILES_CONFIG) return [];
  
  return Object.entries(PROFILES_CONFIG).map(([name, config]) => ({
    name,
    description: config.description,
    useCases: config.use_cases,
    moduleCount: config.modules?.length || "dynamic"
  }));
}
