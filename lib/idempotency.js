/**
 * Idempotency Guard - Sistema de deduplicación para Node.js
 * 
 * Previene efectos duplicados en:
 * - Callbacks de Telegram
 * - Reenvío de comandos
 * - Acciones con efecto real
 * 
 * Fingerprint: hash(action + params + chat_id)
 * Ventana: 5 minutos default
 */

import crypto from "crypto";

// Configuración
const DEFAULT_WINDOW_MS = 5 * 60 * 1000; // 5 minutos
const CLEANUP_INTERVAL_MS = 60 * 1000;     // Limpiar cada minuto

class IdempotencyGuard {
  constructor(windowMs = DEFAULT_WINDOW_MS) {
    this.windowMs = windowMs;
    this.seen = new Map(); // fingerprint -> { timestamp, action, meta }
    this.stats = {
      total: 0,
      duplicates: 0,
      cleaned: 0
    };
    
    // Cleanup periódico
    this.cleanupInterval = setInterval(() => this._cleanup(), CLEANUP_INTERVAL_MS);
  }

  /**
   * Genera fingerprint único para una acción
   */
  _makeFingerprint(action, params, context = {}) {
    // Normalizar params (ordenar keys)
    const normalizedParams = JSON.stringify(params, Object.keys(params).sort());
    
    // Contexto: chat_id, user_id, etc.
    const contextStr = JSON.stringify({
      chat_id: context.chat_id,
      user_id: context.user_id,
      message_id: context.message_id
    });
    
    const data = `${action}:${normalizedParams}:${contextStr}`;
    return crypto.createHash("sha256").update(data).digest("hex").substring(0, 24);
  }

  /**
   * Verifica si una acción ya fue procesada (es duplicado)
   */
  isDuplicate(action, params, context = {}) {
    const fingerprint = this._makeFingerprint(action, params, context);
    const now = Date.now();
    
    this.stats.total++;
    
    if (this.seen.has(fingerprint)) {
      const entry = this.seen.get(fingerprint);
      const age = now - entry.timestamp;
      
      if (age < this.windowMs) {
        // Es duplicado
        this.stats.duplicates++;
        
        // Actualizar orden (LRU)
        this.seen.delete(fingerprint);
        this.seen.set(fingerprint, entry);
        
        return {
          isDuplicate: true,
          fingerprint,
          originalTimestamp: entry.timestamp,
          age: Math.round(age / 1000), // segundos
          action: entry.action
        };
      }
    }
    
    // No es duplicado - registrar
    this.seen.set(fingerprint, {
      timestamp: now,
      action,
      context,
      fingerprint
    });
    
    return {
      isDuplicate: false,
      fingerprint
    };
  }

  /**
   * Ejecuta función solo si no es duplicado
   */
  execute(action, params, context, fn) {
    const check = this.isDuplicate(action, params, context);
    
    if (check.isDuplicate) {
      console.error(`[IDEMPOTENCY] Acción duplicada rechazada: ${action}`, {
        fingerprint: check.fingerprint,
        age: check.age,
        original: new Date(check.originalTimestamp).toISOString()
      });
      
      return {
        executed: false,
        duplicate: true,
        fingerprint: check.fingerprint,
        result: null
      };
    }
    
    // Ejecutar
    try {
      const result = fn();
      return {
        executed: true,
        duplicate: false,
        fingerprint: check.fingerprint,
        result
      };
    } catch (error) {
      // Si falla, eliminar de seen para permitir retry
      this.seen.delete(check.fingerprint);
      throw error;
    }
  }

  /**
   * Limpia entradas expiradas
   */
  _cleanup() {
    const now = Date.now();
    const cutoff = now - this.windowMs;
    let cleaned = 0;
    
    for (const [fp, entry] of this.seen.entries()) {
      if (entry.timestamp < cutoff) {
        this.seen.delete(fp);
        cleaned++;
      }
    }
    
    this.stats.cleaned += cleaned;
    
    if (cleaned > 0) {
      console.log(`[IDEMPOTENCY] Cleanup: ${cleaned} entradas expiradas eliminadas`);
    }
  }

  /**
   * Obtiene estadísticas
   */
  getStats() {
    return {
      ...this.stats,
      entries: this.seen.size,
      windowMs: this.windowMs
    };
  }

  /**
   * Destruye el guard (limpiar intervalos)
   */
  destroy() {
    clearInterval(this.cleanupInterval);
    this.seen.clear();
  }
}

// Singleton global
let globalGuard = null;

export function getIdempotencyGuard() {
  if (!globalGuard) {
    globalGuard = new IdempotencyGuard();
  }
  return globalGuard;
}

export function resetIdempotencyGuard() {
  if (globalGuard) {
    globalGuard.destroy();
    globalGuard = null;
  }
}

// Función helper para usar en módulos
export function guardExecute(action, params, context, fn) {
  return getIdempotencyGuard().execute(action, params, context, fn);
}

export function isDuplicateAction(action, params, context) {
  return getIdempotencyGuard().isDuplicate(action, params, context).isDuplicate;
}

export function getGuardStats() {
  return getIdempotencyGuard().getStats();
}

// Exportar clase para casos avanzados
export { IdempotencyGuard };
