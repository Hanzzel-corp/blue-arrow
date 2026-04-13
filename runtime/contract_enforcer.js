/**
 * Contract Enforcer - Validación progresiva de contratos (3 fases).
 *
 * Fase A: Warning solamente (compatibilidad)
 * Fase B: Warning + métricas por módulo (transparencia)
 * Fase C: Rechazo estricto para core (gobernanza)
 *
 * Lee configuración de config/contract_phase.json
 */

import { readFileSync } from "fs";
import { getLogger } from "./logger.js";

const logger = getLogger("runtime.contract");

// Módulos core (Fase C aplica rechazo estricto)
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

const VALID_SOURCES = new Set(["cli", "telegram", "internal", "system"]);

export class ContractEnforcer {
  constructor() {
    this.phase = this._loadPhase();
    this.metrics = new Map(); // module -> metrics
    this.rejectedCount = 0;

    logger.info(`ContractEnforcer inicializado - Fase ${this.phase}`);
  }

  _loadPhase() {
    try {
      const configPath = new URL("../config/contract_phase.json", import.meta.url);
      const config = JSON.parse(readFileSync(configPath, "utf8"));
      const phase = String(config?.phase || "").toUpperCase();

      if (["A", "B", "C"].includes(phase)) {
        return phase;
      }
    } catch (err) {
      logger.debug("No se pudo cargar config/contract_phase.json, usando Fase A");
    }

    return "A";
  }

  /**
   * Valida un mensaje contra el contrato.
   *
   * @param {object} msg - Mensaje a validar
   * @param {string} moduleId - ID del módulo que envía
   * @returns {object} { isValid, enriched, violations, rejected? }
   */
  validate(msg, moduleId) {
    const violations = this._checkContract(msg, moduleId);
    const isCore = CORE_MODULES.has(moduleId);

    // Actualizar métricas (Fase B y C)
    if (this.phase === "B" || this.phase === "C") {
      this._updateMetrics(moduleId, violations, isCore);
    }

    // Fase C: rechazo estricto para core
    if (this.phase === "C" && isCore) {
      const criticalViolations = violations.filter((v) => v.severity === "critical");
      if (criticalViolations.length > 0) {
        this.rejectedCount++;

        logger.error(`[Fase C] Mensaje rechazado de ${moduleId}`, {
          violations: criticalViolations.map((v) => v.message),
          trace_id: msg?.trace_id || null
        });

        return {
          isValid: false,
          enriched: null,
          violations,
          rejected: true
        };
      }
    }

    // Enriquecer mensaje
    const enriched = this._enrichMessage(msg, moduleId);

    // Log de warnings (Fase A y B)
    if (violations.length > 0 && this.phase !== "C") {
      for (const v of violations) {
        if (v.severity === "critical" || v.severity === "high") {
          logger.warn(`[Contrato] ${moduleId}: ${v.message}`, {
            field: v.field,
            trace_id: enriched.trace_id
          });
        }
      }
    }

    return {
      isValid: true,
      enriched,
      violations
    };
  }

  _checkContract(msg, moduleId) {
    const violations = [];

    if (!msg || typeof msg !== "object") {
      violations.push({
        field: "message",
        severity: "critical",
        message: "mensaje inválido: debe ser un objeto"
      });
      return violations;
    }

    // module obligatorio
    if (!msg.module) {
      violations.push({
        field: "module",
        severity: "high",
        message: "module es obligatorio"
      });
    } else if (typeof msg.module !== "string") {
      violations.push({
        field: "module",
        severity: "medium",
        message: `module debe ser string, es ${typeof msg.module}`
      });
    }

    // port obligatorio
    if (!msg.port) {
      violations.push({
        field: "port",
        severity: "high",
        message: "port es obligatorio"
      });
    } else if (typeof msg.port !== "string") {
      violations.push({
        field: "port",
        severity: "medium",
        message: `port debe ser string, es ${typeof msg.port}`
      });
    }

    // payload obligatorio
    if (msg.payload === undefined) {
      violations.push({
        field: "payload",
        severity: "high",
        message: "payload es obligatorio"
      });
    }

    // trace_id obligatorio (top-level)
    if (!msg.trace_id) {
      violations.push({
        field: "trace_id",
        severity: "critical",
        message: "trace_id es obligatorio para trazabilidad"
      });
    } else if (typeof msg.trace_id !== "string") {
      violations.push({
        field: "trace_id",
        severity: "high",
        message: `trace_id debe ser string, es ${typeof msg.trace_id}`
      });
    }

    // meta obligatorio
    if (!msg.meta || typeof msg.meta !== "object" || Array.isArray(msg.meta)) {
      violations.push({
        field: "meta",
        severity: "critical",
        message: "meta es obligatorio para contexto"
      });
    } else {
      // meta.source obligatorio
      if (!msg.meta.source) {
        violations.push({
          field: "meta.source",
          severity: "high",
          message: "meta.source es obligatorio"
        });
      } else if (!VALID_SOURCES.has(msg.meta.source)) {
        violations.push({
          field: "meta.source",
          severity: "medium",
          message: `meta.source='${msg.meta.source}' no es válido (debe ser: ${Array.from(VALID_SOURCES).join("|")})`
        });
      }

      // meta.timestamp recomendable / autoenriquecible
      if (msg.meta.timestamp && typeof msg.meta.timestamp !== "string") {
        violations.push({
          field: "meta.timestamp",
          severity: "low",
          message: `meta.timestamp debería ser string ISO, es ${typeof msg.meta.timestamp}`
        });
      }
    }

    return violations;
  }

  _enrichMessage(msg, moduleId) {
    const enriched = {
      ...(msg || {})
    };

    // Auto-generar trace_id si falta
    if (!enriched.trace_id) {
      enriched.trace_id = `${moduleId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }

    // Crear meta mínima si falta
    if (!enriched.meta || typeof enriched.meta !== "object" || Array.isArray(enriched.meta)) {
      enriched.meta = {};
    }

    // Asegurar source
    if (!enriched.meta.source) {
      enriched.meta.source = "internal";
    }

    // Asegurar timestamp
    if (!enriched.meta.timestamp) {
      enriched.meta.timestamp = new Date().toISOString();
    }

    return enriched;
  }

  _updateMetrics(moduleId, violations, isCore) {
    if (!this.metrics.has(moduleId)) {
      this.metrics.set(moduleId, {
        module: moduleId,
        tier: isCore ? "core" : "satellite",
        total: 0,
        violations: 0,
        missingTraceId: 0,
        missingMeta: 0,
        invalidSource: 0,
        lastViolation: null
      });
    }

    const m = this.metrics.get(moduleId);
    m.total++;

    if (violations.length > 0) {
      m.violations += violations.length;
      m.lastViolation = Date.now();

      for (const v of violations) {
        if (v.field === "trace_id") m.missingTraceId++;
        if (v.field === "meta") m.missingMeta++;
        if (v.field === "meta.source") m.invalidSource++;
      }
    }
  }

  /**
   * Obtiene reporte de métricas (para Fase B y C)
   */
  getMetricsReport() {
    if (this.metrics.size === 0) {
      return {
        status: "no_data",
        phase: this.phase
      };
    }

    const modules = Array.from(this.metrics.values());
    const core = modules.filter((m) => m.tier === "core");
    const satellite = modules.filter((m) => m.tier === "satellite");

    const calcCompliance = (list) => {
      if (list.length === 0) return 0;
      const total = list.reduce((sum, m) => sum + m.total, 0);
      const violations = list.reduce((sum, m) => sum + m.violations, 0);
      return total > 0 ? Math.round(((total - violations) / total) * 100) : 100;
    };

    return {
      status: "ok",
      phase: this.phase,
      timestamp: new Date().toISOString(),
      summary: {
        modulesMonitored: modules.length,
        coreModules: core.length,
        satelliteModules: satellite.length,
        totalMessages: modules.reduce((sum, m) => sum + m.total, 0),
        totalViolations: modules.reduce((sum, m) => sum + m.violations, 0),
        rejectedMessages: this.rejectedCount
      },
      compliance: {
        core: calcCompliance(core),
        satellite: calcCompliance(satellite)
      },
      modulesWithViolations: modules
        .filter((m) => m.violations > 0)
        .map((m) => ({
          module: m.module,
          tier: m.tier,
          total: m.total,
          violations: m.violations,
          missingTraceId: m.missingTraceId,
          missingMeta: m.missingMeta,
          invalidSource: m.invalidSource,
          lastViolation: m.lastViolation
        }))
        .sort((a, b) => b.violations - a.violations)
    };
  }

  /**
   * Loguea reporte de métricas
   */
  logMetrics() {
    if (this.phase === "A") return;

    const report = this.getMetricsReport();
    if (report.status === "no_data") return;

    logger.info(`[Contrato] Métricas - Fase ${this.phase}`, {
      compliance: report.compliance,
      violations: report.summary.totalViolations,
      rejected: report.summary.rejectedMessages
    });

    const problematic = report.modulesWithViolations?.slice(0, 3) || [];
    for (const m of problematic) {
      logger.warn(`[Contrato] ${m.module} (${m.tier}): ${m.violations} violaciones en ${m.total} mensajes`, {
        missingTraceId: m.missingTraceId,
        missingMeta: m.missingMeta,
        invalidSource: m.invalidSource
      });
    }
  }
}

// Singleton
let instance = null;

export function getContractEnforcer() {
  if (!instance) {
    instance = new ContractEnforcer();
  }
  return instance;
}

export function resetContractEnforcer() {
  instance = null;
}
