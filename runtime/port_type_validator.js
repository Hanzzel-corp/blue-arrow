/**
 * Port Type Validator (JS) - Validación de tipos de puertos en runtime
 *
 * Tipos:
 * - execution: Flujo real de acciones
 * - observation: Monitoreo sin side-effects
 * - ui: Interfaces de usuario
 * - persistence: Almacenamiento
 * - control: Señales de control
 */

import { getLogger } from "./logger.js";

const logger = getLogger("runtime.port_type");

export const PortType = {
  EXECUTION: "execution",
  OBSERVATION: "observation",
  UI: "ui",
  PERSISTENCE: "persistence",
  CONTROL: "control",
  UNKNOWN: "unknown"
};

// Patrones de puerto por tipo
const PORT_PATTERNS = {
  [PortType.EXECUTION]: [
    "action.in", "action.out",
    "plan.in", "plan.out",
    "command.in", "command.out",
    "result.in", "result.out",
    "approval.in", "approval.out",
    "approved.plan.out",
    "blocked.plan.out",
    "desktop.action.out",
    "browser.action.out",
    "system.action.out",
    "terminal.action.out"
  ],
  [PortType.OBSERVATION]: [
    "event.in", "event.out",
    "audit.in", "audit.out",
    "verification.out"
  ],
  [PortType.UI]: [
    "response.in", "response.out",
    "ui.response.in", "ui.response.out",
    "ui.state.in", "ui.state.out",
    "ui.render.request.in", "ui.render.request.out"
  ],
  [PortType.PERSISTENCE]: [
    "memory.in", "memory.out",
    "query.in", "query.out",
    "app.session.in", "app.session.out",
    "memory.sync.out"
  ],
  [PortType.CONTROL]: [
    "signal.in", "signal.out",
    "context.in", "context.out",
    "callback.in", "callback.out",
    "request.in", "request.out"
  ]
};

// Core modules para detectar satellites
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
  "interface.main",
  "interface.telegram",
  "ui.state.main"
]);

export class PortTypeValidator {
  constructor(blueprint) {
    this.blueprint = blueprint || { connections: [] };
    this.portTypes = new Map();
    this._classifyPorts();
  }

  _classifyPorts() {
    for (const conn of this.blueprint.connections || []) {
      const fromPort = this._extractPortName(conn?.from);
      const toPort = this._extractPortName(conn?.to);

      if (conn?.from && !this.portTypes.has(conn.from)) {
        this.portTypes.set(conn.from, this._getPortType(fromPort));
      }

      if (conn?.to && !this.portTypes.has(conn.to)) {
        this.portTypes.set(conn.to, this._getPortType(toPort));
      }
    }
  }

  _extractPortName(fullPort) {
    if (typeof fullPort !== "string") return "";
    const parts = fullPort.split(":");
    return parts.length > 1 ? parts[1] : fullPort;
  }

  _extractModuleId(fullPort) {
    if (typeof fullPort !== "string") return "";
    const parts = fullPort.split(":");
    return parts[0] || "";
  }

  _getPortType(portName) {
    if (!portName) return PortType.UNKNOWN;

    for (const [type, patterns] of Object.entries(PORT_PATTERNS)) {
      for (const pattern of patterns) {
        if (portName === pattern) {
          return type;
        }

        // Compatibilidad flexible con nombres cercanos
        const patternBase = pattern.replace(/\.in$|\.out$/, "");
        if (
          portName.startsWith(patternBase) ||
          portName.endsWith(pattern) ||
          portName.includes(patternBase)
        ) {
          return type;
        }
      }
    }

    return PortType.UNKNOWN;
  }

  getPortType(fullPort) {
    return this.portTypes.get(fullPort) || this._getPortType(this._extractPortName(fullPort));
  }

  _isSatelliteModule(moduleId) {
    return !CORE_MODULES.has(moduleId);
  }

  _isBroadcast(source, count) {
    return count > 3 && this.getPortType(source) !== PortType.UI;
  }

  validateConnection(conn) {
    if (!conn?.from || !conn?.to) {
      return {
        violation: "invalid_connection",
        severity: "medium",
        message: "Conexión inválida: falta from o to"
      };
    }

    const fromType = this.getPortType(conn.from);
    const toType = this.getPortType(conn.to);
    const fromModule = this._extractModuleId(conn.from);
    const toModule = this._extractModuleId(conn.to);
    const fromPortName = this._extractPortName(conn.from);
    const toPortName = this._extractPortName(conn.to);

    // observation -> execution (satellite = warning, core = critical)
    if (fromType === PortType.OBSERVATION && toType === PortType.EXECUTION) {
      if (this._isSatelliteModule(toModule)) {
        return {
          violation: "observation_to_satellite",
          severity: "low",
          message: `${conn.from} dispara acción en satélite ${conn.to}`
        };
      }

      return {
        violation: "observation_to_execution",
        severity: "critical",
        message: `CRÍTICO: ${conn.from} conecta a ejecución core ${conn.to}`
      };
    }

    // ui -> execution (solo command.in permitido directamente)
    if (fromType === PortType.UI && toType === PortType.EXECUTION) {
      if (toPortName !== "command.in") {
        return {
          violation: "ui_to_execution",
          severity: "medium",
          message: `${conn.from} (UI) no debería conectar a ${conn.to}; usar command.in`
        };
      }
    }

    // persistence -> execution (sospechoso)
    if (fromType === PortType.PERSISTENCE && toType === PortType.EXECUTION) {
      return {
        violation: "persistence_to_execution",
        severity: "medium",
        message: `${conn.from} (persistence) dispara ejecución en ${conn.to}`
      };
    }

    // unknown ports
    if (fromType === PortType.UNKNOWN || toType === PortType.UNKNOWN) {
      return {
        violation: "unknown_port_type",
        severity: "low",
        message: `Tipo de puerto desconocido en ${conn.from} -> ${conn.to}`
      };
    }

    // self-loop sospechoso
    if (fromModule && toModule && fromModule === toModule && fromPortName === toPortName) {
      return {
        violation: "self_loop_same_port",
        severity: "medium",
        message: `Loop exacto sospechoso en ${conn.from} -> ${conn.to}`
      };
    }

    return null;
  }

  validateAll() {
    const violations = [];
    const sourceTargets = new Map();

    for (const conn of this.blueprint.connections || []) {
      if (!sourceTargets.has(conn.from)) {
        sourceTargets.set(conn.from, []);
      }
      sourceTargets.get(conn.from).push(conn.to);

      const violation = this.validateConnection(conn);
      if (violation) {
        violations.push({
          ...violation,
          connection: conn
        });
      }
    }

    // Detectar broadcasts
    for (const [source, targets] of sourceTargets.entries()) {
      if (this._isBroadcast(source, targets.length)) {
        violations.push({
          violation: "broadcast_fanout",
          severity: "low",
          message: `${source} tiene fan-out alto (${targets.length} destinos)`,
          source,
          targets
        });
      }
    }

    const grouped = {
      critical: violations.filter((v) => v.severity === "critical"),
      medium: violations.filter((v) => v.severity === "medium"),
      low: violations.filter((v) => v.severity === "low")
    };

    return {
      valid: grouped.critical.length === 0,
      violations,
      summary: {
        total: violations.length,
        critical: grouped.critical.length,
        medium: grouped.medium.length,
        low: grouped.low.length
      },
      grouped
    };
  }

  logReport() {
    const report = this.validateAll();

    if (report.summary.total === 0) {
      logger.info("PortTypeValidator: sin violaciones");
      return report;
    }

    if (report.summary.critical > 0) {
      logger.error("PortTypeValidator: violaciones críticas detectadas", {
        summary: report.summary,
        critical: report.grouped.critical.map((v) => v.message)
      });
    } else {
      logger.warn("PortTypeValidator: violaciones detectadas", {
        summary: report.summary
      });
    }

    return report;
  }
}

let instance = null;

export function getPortTypeValidator(blueprint) {
  if (!instance) {
    instance = new PortTypeValidator(blueprint);
  }
  return instance;
}

export function resetPortTypeValidator() {
  instance = null;
}
