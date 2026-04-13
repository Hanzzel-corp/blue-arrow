/**
 * Contract Versioning - Versionado fuerte de contratos de mensajes
 *
 * Features:
 * - Schema versioning semántico (major.minor.patch)
 * - Validación estricta de compatibilidad
 * - Migración automática entre versiones
 * - Registro de versiones por puerto
 */

import { getLogger } from "./logger.js";

const logger = getLogger("runtime.contract_version");

// Esquemas de contrato versionados
const CONTRACT_REGISTRY = {
  // Mensaje base
  "message": {
    "1.0.0": {
      required: ["module", "port", "payload"],
      optional: ["timestamp", "message_id"]
    },
    "2.0.0": {
      required: ["module", "port", "payload", "trace_id", "meta"],
      optional: ["timestamp"],
      deprecated: ["message_id"]
    }
  },

  // action.in
  "action.in": {
    "1.0.0": {
      required: ["task_id", "action", "params"],
      optional: ["timeout_ms"]
    },
    "2.0.0": {
      required: ["task_id", "action", "params", "trace_id", "meta"],
      fields: {
        "meta": { required: ["source"] }
      }
    }
  },

  // result.out
  "result.out": {
    "1.0.0": {
      required: ["task_id", "status"],
      optional: ["result", "error"]
    },
    "2.0.0": {
      required: ["task_id", "status", "trace_id", "meta"],
      fields: {
        "meta": { required: ["source"] }
      }
    }
  },

  // event.out
  "event.out": {
    "1.0.0": {
      required: ["event_type"],
      optional: ["data", "timestamp"]
    },
    "2.0.0": {
      required: ["event_type", "timestamp", "trace_id", "meta"],
      fields: {
        "meta": { required: ["source"] }
      }
    }
  }
};

// Versiones soportadas por cada módulo (manifest-based)
const MODULE_VERSIONS = new Map();

export class ContractVersionManager {
  constructor() {
    this.supportedVersions = new Map(); // module:port -> Set<versions>
    this.activeVersions = new Map(); // port -> current version
    this.migrations = new Map(); // port:from->to -> migrator function
  }

  /**
   * Registra versión soportada por un módulo
   */
  registerModuleVersion(moduleId, port, version, isProducer = false) {
    const key = `${moduleId}:${port}`;

    if (!this.supportedVersions.has(key)) {
      this.supportedVersions.set(key, new Set());
    }

    this.supportedVersions.get(key).add(version);

    // Si es productor, establecer como versión activa
    if (isProducer && !this.activeVersions.has(port)) {
      this.activeVersions.set(port, version);
    }

    MODULE_VERSIONS.set(key, version);

    logger.debug(`Module ${moduleId} supports ${port}@${version}`, {
      isProducer,
      module: moduleId,
      port,
      version
    });
  }

  /**
   * Negocia versión entre productor y consumidor
   */
  negotiateVersion(port, producerModule, consumerModule) {
    const producerKey = `${producerModule}:${port}`;
    const consumerKey = `${consumerModule}:${port}`;

    const producerVersions = this.supportedVersions.get(producerKey) || new Set();
    const consumerVersions = this.supportedVersions.get(consumerKey) || new Set();

    // Encontrar versión común más alta
    const commonVersions = [...producerVersions]
      .filter((v) => consumerVersions.has(v))
      .sort((a, b) => this._compareVersions(a, b));

    if (commonVersions.length === 0) {
      logger.error(`No common version for ${port} between ${producerModule} and ${consumerModule}`, {
        producerVersions: [...producerVersions],
        consumerVersions: [...consumerVersions]
      });
      return null;
    }

    const negotiated = commonVersions[commonVersions.length - 1];

    logger.info(`Negotiated ${port}@${negotiated} for ${producerModule} -> ${consumerModule}`);

    return negotiated;
  }

  /**
   * Valida mensaje contra contrato versionado
   */
  validateMessage(message, port, version) {
    const schema = this._getSchema(port, version);
    if (!schema) {
      return { valid: false, error: `Unknown schema ${port}@${version}` };
    }

    const errors = [];

    // Verificar campos requeridos
    for (const field of schema.required || []) {
      if (message[field] === undefined || message[field] === null) {
        errors.push(`Missing required field: ${field}`);
      }
    }

    // Verificar campos deprecados
    for (const field of schema.deprecated || []) {
      if (message[field] !== undefined) {
        logger.warn(`Deprecated field used: ${field} in ${port}@${version}`);
      }
    }

    // Verificar sub-campos (nested validation)
    if (schema.fields) {
      for (const [field, fieldSchema] of Object.entries(schema.fields)) {
        if (message[field] && typeof message[field] === "object") {
          for (const subField of fieldSchema.required || []) {
            if (message[field][subField] === undefined) {
              errors.push(`Missing required sub-field: ${field}.${subField}`);
            }
          }
        }
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      version
    };
  }

  /**
   * Migra mensaje de una versión a otra
   */
  migrateMessage(message, port, fromVersion, toVersion) {
    if (fromVersion === toVersion) {
      return { success: true, message };
    }

    const migrationKey = `${port}:${fromVersion}->${toVersion}`;
    const migrator = this.migrations.get(migrationKey);

    if (!migrator) {
      logger.warn(`No migrator for ${migrationKey}, attempting direct validation`);

      const validation = this.validateMessage(message, port, toVersion);
      if (validation.valid) {
        return { success: true, message };
      }

      return {
        success: false,
        error: `No migration path from ${fromVersion} to ${toVersion} for ${port}`,
        validationErrors: validation.errors
      };
    }

    try {
      const migrated = migrator(message);

      logger.debug(`Migrated ${port} ${fromVersion} -> ${toVersion}`);

      return { success: true, message: migrated };
    } catch (error) {
      logger.error(`Migration failed for ${migrationKey}`, { error: error.message });

      return {
        success: false,
        error: `Migration failed: ${error.message}`
      };
    }
  }

  /**
   * Registra función de migración
   */
  registerMigration(port, fromVersion, toVersion, migratorFn) {
    const key = `${port}:${fromVersion}->${toVersion}`;
    this.migrations.set(key, migratorFn);
  }

  /**
   * Verifica compatibilidad entre versiones
   */
  checkCompatibility(port, version1, version2) {
    const [major1] = version1.split(".").map(Number);
    const [major2] = version2.split(".").map(Number);

    // Major version debe coincidir para compatibilidad
    if (major1 !== major2) {
      return {
        compatible: false,
        reason: `Major version mismatch: ${version1} vs ${version2}`
      };
    }

    return { compatible: true };
  }

  /**
   * Obtiene versión actual de un puerto
   */
  getActiveVersion(port) {
    return this.activeVersions.get(port);
  }

  /**
   * Fija versión activa de un puerto
   */
  setActiveVersion(port, version) {
    this.activeVersions.set(port, version);
  }

  /**
   * Lista versiones soportadas por un puerto
   */
  listSupportedVersions(port) {
    const versions = new Set();

    for (const [key, portVersions] of this.supportedVersions.entries()) {
      if (key.endsWith(`:${port}`)) {
        portVersions.forEach((v) => versions.add(v));
      }
    }

    return [...versions].sort((a, b) => this._compareVersions(a, b));
  }

  /**
   * Devuelve stats simples para debug
   */
  getStats() {
    return {
      supportedKeys: this.supportedVersions.size,
      activePorts: this.activeVersions.size,
      migrations: this.migrations.size
    };
  }

  // Métodos privados

  _getSchema(port, version) {
    const portSchemas = CONTRACT_REGISTRY[port];
    if (!portSchemas) return null;

    return portSchemas[version] || null;
  }

  _compareVersions(v1, v2) {
    const parts1 = String(v1).split(".").map(Number);
    const parts2 = String(v2).split(".").map(Number);

    for (let i = 0; i < 3; i += 1) {
      const a = parts1[i] || 0;
      const b = parts2[i] || 0;
      if (a < b) return -1;
      if (a > b) return 1;
    }

    return 0;
  }
}

// Migraciones predefinidas
export function registerDefaultMigrations(manager) {
  // 1.0.0 -> 2.0.0: Agregar trace_id y meta
  manager.registerMigration("message", "1.0.0", "2.0.0", (msg) => {
    return {
      ...msg,
      trace_id: msg.trace_id || msg.message_id || `gen-${Date.now()}`,
      meta: {
        ...(msg.meta || {}),
        source: msg?.meta?.source || "unknown",
        timestamp: msg?.meta?.timestamp || msg.timestamp || new Date().toISOString()
      }
    };
  });

  manager.registerMigration("action.in", "1.0.0", "2.0.0", (msg) => {
    return {
      ...msg,
      trace_id: msg.trace_id || msg.task_id || `gen-${Date.now()}`,
      meta: {
        ...(msg.meta || {}),
        source: msg?.meta?.source || "unknown",
        timestamp: msg?.meta?.timestamp || new Date().toISOString()
      }
    };
  });

  manager.registerMigration("result.out", "1.0.0", "2.0.0", (msg) => {
    return {
      ...msg,
      trace_id: msg.trace_id || msg.task_id || `gen-${Date.now()}`,
      meta: {
        ...(msg.meta || {}),
        source: msg?.meta?.source || "unknown",
        timestamp: msg?.meta?.timestamp || new Date().toISOString()
      }
    };
  });

  manager.registerMigration("event.out", "1.0.0", "2.0.0", (msg) => {
    return {
      ...msg,
      event_type: msg.event_type || msg.type || "unknown_event",
      timestamp: msg.timestamp || new Date().toISOString(),
      trace_id: msg.trace_id || `gen-${Date.now()}`,
      meta: {
        ...(msg.meta || {}),
        source: msg?.meta?.source || "unknown",
        timestamp: msg?.meta?.timestamp || new Date().toISOString()
      }
    };
  });
}

// Singleton
let instance = null;

export function getContractVersionManager() {
  if (!instance) {
    instance = new ContractVersionManager();
    registerDefaultMigrations(instance);
  }
  return instance;
}

export function resetContractVersionManager() {
  instance = null;
}