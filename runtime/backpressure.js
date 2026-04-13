/**
 * Back-Pressure System - Control de flujo para evitar saturación
 *
 * Estrategias:
 * 1. Rate limiting: límites de mensajes por segundo
 * 2. Queue limiting: tamaño máximo de colas
 * 3. Load shedding: descarte controlado en sobrecarga
 * 4. Flow control: pausa/reanudación de emisores
 */

import { getLogger } from "./logger.js";

const logger = getLogger("runtime.backpressure");

// Configuración por defecto
const DEFAULT_CONFIG = {
  // Límites por módulo
  maxQueueSize: 2000,
  maxRatePerSecond: 500,

  // Ventanas de tiempo
  rateWindowMs: 1000,

  // Acciones ante sobrecarga
  sheddableTypes: ["event.out", "query.in"],
  criticalTypes: ["action.in", "plan.in"],

  // Alertas
  warningThreshold: 0.8,
  criticalThreshold: 0.95
};

export class BackPressureManager {
  constructor(config = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };

    // Estado por módulo
    this.moduleStats = new Map();   // moduleId -> stats
    this.queues = new Map();        // moduleId -> Array<{message,timestamp,retryCount,id}>
    this.pausedModules = new Set(); // módulos pausados

    // Métricas globales
    this.totalDropped = 0;
    this.totalDelayed = 0;

    // Cleanup periódico
    this.cleanupInterval = setInterval(() => this._cleanup(), 5000);
  }

  /**
   * Registra un mensaje entrante y aplica backpressure si es necesario
   *
   * @param {string} moduleId - Módulo destino
   * @param {object} message - Mensaje a entregar
   * @returns {{ action: 'accept'|'drop'|'delay', reason?: string, delayMs?: number }}
   */
  registerIncoming(moduleId, message) {
    const now = Date.now();
    const stats = this._getStats(moduleId);

    // 1. Rate limiting
    const rateStatus = this._checkRateLimit(moduleId, now);
    if (rateStatus.exceeded) {
      const isCritical = this._isCriticalMessage(message);

      if (isCritical) {
        this.totalDelayed++;
        logger.warn(`Rate limit exceeded for ${moduleId}, delaying critical message`, {
          currentRate: rateStatus.currentRate,
          maxRate: this.config.maxRatePerSecond,
          port: message?.port
        });

        return {
          action: "delay",
          reason: "rate_limit",
          delayMs: Math.min(
            1000,
            Math.max(50, Math.round((rateStatus.currentRate / this.config.maxRatePerSecond) * 100))
          )
        };
      }

      this.totalDropped++;
      logger.debug(`Rate limit shedding for ${moduleId}`, {
        port: message?.port,
        type: "load_shedding"
      });

      return {
        action: "drop",
        reason: "rate_limit_shedding"
      };
    }

    // 2. Queue limiting
    const queueStatus = this._checkQueueSize(moduleId);
    if (queueStatus.full) {
      const isSheddable = this._isSheddableMessage(message);

      if (isSheddable) {
        this.totalDropped++;
        logger.warn(`Queue full for ${moduleId}, shedding message`, {
          queueSize: queueStatus.currentSize,
          maxSize: this.config.maxQueueSize,
          port: message?.port
        });

        return {
          action: "drop",
          reason: "queue_full_shedding"
        };
      }

      this._applyBackPressure(moduleId);

      logger.error(`Queue full for ${moduleId}, applying backpressure`, {
        queueSize: queueStatus.currentSize,
        module: moduleId,
        port: message?.port
      });

      return {
        action: "delay",
        reason: "queue_full_backpressure",
        delayMs: 500
      };
    }

    // 3. Aceptar mensaje
    stats.messageCount++;
    stats.lastMessageTime = now;
    stats.recentTimestamps.push(now);

    if (!this.queues.has(moduleId)) {
      this.queues.set(moduleId, []);
    }

    const queue = this.queues.get(moduleId);
    queue.push({
      id: this._getMessageId(message),
      message,
      timestamp: now,
      retryCount: 0
    });

    return { action: "accept" };
  }

  /**
   * Notifica que un mensaje fue procesado (libera espacio en cola)
   */
  notifyProcessed(moduleId, messageId) {
    const queue = this.queues.get(moduleId);
    if (!queue || !queue.length) return;

    const normalizedId = String(messageId ?? "");
    const index = queue.findIndex(
      (item) =>
        item.id === normalizedId ||
        String(item.message?.message_id ?? "") === normalizedId ||
        String(item.message?.trace_id ?? "") === normalizedId
    );

    if (index >= 0) {
      queue.splice(index, 1);
    } else if (queue.length > 0) {
      // fallback conservador: si no encontramos el id, quitar el más viejo
      queue.shift();
    }

    const utilization = queue.length / this.config.maxQueueSize;
    if (utilization < 0.5 && this.pausedModules.has(moduleId)) {
      this._releaseBackPressure(moduleId);
    }
  }

  /**
   * Obtiene estadísticas de backpressure
   */
  getStats() {
    const moduleStats = {};

    for (const [moduleId, stats] of this.moduleStats.entries()) {
      const queue = this.queues.get(moduleId) || [];
      const rate = this._calculateCurrentRate(moduleId);

      moduleStats[moduleId] = {
        queueSize: queue.length,
        queueUtilization: this.config.maxQueueSize > 0 ? queue.length / this.config.maxQueueSize : 0,
        currentRate: rate,
        rateUtilization: this.config.maxRatePerSecond > 0 ? rate / this.config.maxRatePerSecond : 0,
        isPaused: this.pausedModules.has(moduleId),
        messageCount: stats.messageCount
      };
    }

    return {
      global: {
        totalDropped: this.totalDropped,
        totalDelayed: this.totalDelayed,
        pausedModules: Array.from(this.pausedModules)
      },
      modules: moduleStats
    };
  }

  /**
   * Verifica si un módulo está bajo backpressure
   */
  isUnderPressure(moduleId) {
    const queue = this.queues.get(moduleId) || [];
    const utilization = this.config.maxQueueSize > 0 ? queue.length / this.config.maxQueueSize : 0;
    const rate = this._calculateCurrentRate(moduleId);
    const rateUtilization =
      this.config.maxRatePerSecond > 0 ? rate / this.config.maxRatePerSecond : 0;

    return (
      this.pausedModules.has(moduleId) ||
      utilization >= this.config.warningThreshold ||
      rateUtilization >= this.config.warningThreshold
    );
  }

  /**
   * Limpia recursos del manager
   */
  stop() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
      this.cleanupInterval = null;
    }
  }

  // =========================
  // Internals
  // =========================

  _getStats(moduleId) {
    if (!this.moduleStats.has(moduleId)) {
      this.moduleStats.set(moduleId, {
        moduleId,
        messageCount: 0,
        lastMessageTime: 0,
        recentTimestamps: [],
        pausedAt: null,
        lastPressureAt: null
      });
    }
    return this.moduleStats.get(moduleId);
  }

  _checkRateLimit(moduleId, now) {
    const stats = this._getStats(moduleId);
    const windowStart = now - this.config.rateWindowMs;

    stats.recentTimestamps = stats.recentTimestamps.filter((ts) => ts >= windowStart);

    const currentRate = stats.recentTimestamps.length;
    const exceeded = currentRate >= this.config.maxRatePerSecond;

    if (exceeded) {
      stats.lastPressureAt = now;
    }

    return {
      exceeded,
      currentRate
    };
  }

  _checkQueueSize(moduleId) {
    const queue = this.queues.get(moduleId) || [];
    const currentSize = queue.length;

    return {
      full: currentSize >= this.config.maxQueueSize,
      currentSize
    };
  }

  _calculateCurrentRate(moduleId) {
    const stats = this._getStats(moduleId);
    const now = Date.now();
    const windowStart = now - this.config.rateWindowMs;

    stats.recentTimestamps = stats.recentTimestamps.filter((ts) => ts >= windowStart);
    return stats.recentTimestamps.length;
  }

  _isCriticalMessage(message) {
    const port = message?.port || "";
    return this.config.criticalTypes.includes(port);
  }

  _isSheddableMessage(message) {
    const port = message?.port || "";
    return this.config.sheddableTypes.includes(port);
  }

  _applyBackPressure(moduleId) {
    if (!this.pausedModules.has(moduleId)) {
      this.pausedModules.add(moduleId);
      const stats = this._getStats(moduleId);
      stats.pausedAt = Date.now();

      logger.warn(`Backpressure applied to ${moduleId}`, {
        module: moduleId
      });
    }
  }

  _releaseBackPressure(moduleId) {
    if (this.pausedModules.has(moduleId)) {
      this.pausedModules.delete(moduleId);
      const stats = this._getStats(moduleId);
      stats.pausedAt = null;

      logger.info(`Backpressure released for ${moduleId}`, {
        module: moduleId
      });
    }
  }

  _cleanup() {
    const now = Date.now();
    const maxAgeMs = Math.max(this.config.rateWindowMs * 5, 30000);

    // limpiar timestamps viejos
    for (const stats of this.moduleStats.values()) {
      stats.recentTimestamps = stats.recentTimestamps.filter(
        (ts) => ts >= now - this.config.rateWindowMs
      );
    }

    // limpiar mensajes muy viejos en colas para evitar leaks
    for (const [moduleId, queue] of this.queues.entries()) {
      const filtered = queue.filter((item) => item.timestamp >= now - maxAgeMs);

      if (filtered.length !== queue.length) {
        this.queues.set(moduleId, filtered);
      }

      // liberar presión si la cola ya bajó
      const utilization =
        this.config.maxQueueSize > 0 ? filtered.length / this.config.maxQueueSize : 0;

      if (utilization < 0.5 && this.pausedModules.has(moduleId)) {
        this._releaseBackPressure(moduleId);
      }
    }
  }

  _getMessageId(message) {
    return String(
      message?.message_id ??
      message?.trace_id ??
      `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
    );
  }
}

// Singleton
let instance = null;

export function getBackPressureManager(config = {}) {
  if (!instance) {
    instance = new BackPressureManager(config);
  }
  return instance;
}

export function resetBackPressureManager() {
  if (instance) {
    instance.stop();
  }
  instance = null;
}
