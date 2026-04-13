import readline from "readline";
import { spawn } from "child_process";
import path from "path";
import { applyTransform } from "./transforms.js";
import { getLogger } from "./logger.js";
import { getContractEnforcer } from "./contract_enforcer.js";
import { TierManager } from "./tier_manager.js";
import { getBackPressureManager } from "./backpressure.js";
import { getContractVersionManager } from "./contract_versioning.js";

const logger = getLogger("runtime.bus");

function resolveCommand(language) {
  if (language === "python") {
    return process.platform === "win32" ? "python" : "python3";
  }
  if (language === "node") {
    return "node";
  }
  throw new Error(`Lenguaje no soportado: ${language}`);
}

export class RuntimeBus {
  constructor(registry, blueprint, options = {}) {
    this.registry = registry;
    this.blueprint = blueprint;
    this.processes = new Map();
    this.moduleRestartCount = new Map();
    this.maxRestarts = 3;
    this.isShuttingDown = false;
    this.contractEnforcer = getContractEnforcer();
    this.tierManager = new TierManager(registry, blueprint);
    this.backPressure = getBackPressureManager(options.backpressure);
    this.contractVersioning = getContractVersionManager();
    
    // Métricas periódicas (Fase B y C)
    this.metricsInterval = setInterval(() => {
      this.contractEnforcer.logMetrics();
      this._logBackPressureStats();
    }, 60000); // Cada minuto
  }

  _logBackPressureStats() {
    const stats = this.backPressure.getStats();
    if (stats.global.totalDropped > 0 || stats.global.totalDelayed > 0) {
      logger.info("Backpressure stats", {
        dropped: stats.global.totalDropped,
        delayed: stats.global.totalDelayed,
        pausedModules: stats.global.pausedModules.length
      });
    }
  }

  /**
   * Obtiene el delay de restart según el tier del módulo
   */
  getRestartDelay(mod) {
    return this.tierManager.getRestartDelay(mod.id);
  }

  /**
   * Verifica si un módulo debe auto-reiniciarse según su política
   */
  shouldAutoRestart(mod) {
    const policy = this.tierManager.getRestartPolicy(mod.id);
    return policy !== "on_demand";
  }

  startModule(mod) {
    if (!mod || !mod.id || !mod.entry || !mod.dir) {
      throw new Error("Módulo inválido para startModule");
    }

    const entry = mod.entry;
    const fullEntry = path.join(mod.dir, entry);
    const cmd = resolveCommand(mod.language);

    logger.info(`Iniciando módulo ${mod.id}`, {
      language: mod.language,
      entry
    });

    const child = spawn(cmd, [fullEntry], {
      stdio: ["pipe", "pipe", "inherit"]
    });

    child.on("error", (err) => {
      logger.error(`No se pudo iniciar ${mod.id}`, { error: err.message });
    });

    child.on("exit", (code, signal) => {
      this.processes.delete(mod.id);

      if (this.isShuttingDown) {
        logger.info(`${mod.id} terminó durante shutdown`, { code, signal });
        return;
      }

      if (code !== 0) {
        logger.error(`${mod.id} terminó con código ${code}`, { signal });
        this.handleModuleExit(mod, code, signal);
      } else {
        logger.info(`${mod.id} terminó normalmente`);
      }
    });

    if (child.stdout) {
      child.stdout.on("error", (err) => {
        logger.error(`stdout error en ${mod.id}`, { error: err.message });
      });

      const rl = readline.createInterface({
        input: child.stdout,
        crlfDelay: Infinity
      });

      rl.on("line", (line) => {
        if (!line.trim()) return;

        let msg;
        try {
          msg = JSON.parse(line);
        } catch {
          logger.error(`Mensaje inválido de ${mod.id}`, {
            line: line.substring(0, 200)
          });
          return;
        }

        if (!msg || typeof msg !== "object" || !msg.module || !msg.port) {
          logger.error(`Mensaje incompleto de ${mod.id}`, {
            line: line.substring(0, 200)
          });
          return;
        }

        // Validación de contrato (3 fases: A=warning, B=warning+métricas, C=rechazo estricto)
        const validation = this.contractEnforcer.validate(msg, mod.id);
        
        if (!validation.isValid) {
          // Fase C: mensaje rechazado (core con violación crítica)
          logger.error(`Mensaje rechazado de ${mod.id} (violación de contrato)`, {
            violations: validation.violations.map(v => v.message),
            port: msg.port
          });
          return; // No procesar el mensaje
        }
        
        // Usar mensaje enriquecido (con campos auto-generados si faltaban)
        const enrichedMsg = validation.enriched;

        logger.debug(`Mensaje recibido de ${mod.id}`, {
          port: enrichedMsg.port,
          trace_id: enrichedMsg.trace_id,
          source: enrichedMsg.meta?.source,
          violations: validation.violations.length
        });
        
        this.route(enrichedMsg);
      });
    } else {
      logger.error(`stdout no disponible en ${mod.id}`);
    }

    if (child.stdin) {
      child.stdin.on("error", (err) => {
        logger.error(`stdin error en ${mod.id}`, { error: err.message });
      });
    }

    this.processes.set(mod.id, child);

    if (!this.moduleRestartCount.has(mod.id)) {
      this.moduleRestartCount.set(mod.id, 0);
    }

    logger.info(`Módulo ${mod.id} iniciado`, { pid: child.pid });
  }

  handleModuleExit(mod, code, signal) {
    if (this.isShuttingDown) {
      return;
    }

    // Usar TierManager para determinar impacto y acción
    const exitInfo = this.tierManager.handleModuleExit(mod.id, code);
    
    // Verificar si debe auto-reiniciarse
    if (!this.shouldAutoRestart(mod)) {
      logger.info(`Módulo ${mod.id} (policy: on_demand) no se reiniciará automáticamente`);
      return;
    }

    const restartCount = this.moduleRestartCount.get(mod.id) || 0;
    const restartDelay = this.getRestartDelay(mod);

    if (restartCount < this.maxRestarts) {
      const nextCount = restartCount + 1;
      this.moduleRestartCount.set(mod.id, nextCount);

      // Log diferenciado por tier
      const tierLabel = exitInfo.tier === "core" ? "🔴 CORE" : "🛰️  SATELLITE";
      logger.warn(
        `${tierLabel} Reiniciando ${mod.id} (${nextCount}/${this.maxRestarts}) en ${restartDelay}ms`,
        { code, signal, tier: exitInfo.tier, impact: exitInfo.impact }
      );

      setTimeout(() => {
        if (this.isShuttingDown) return;

        try {
          this.startModule(mod);
          logger.info(`${mod.id} reiniciado exitosamente`);
        } catch (error) {
          logger.error(`Error reiniciando ${mod.id}`, {
            error: error.message,
            tier: exitInfo.tier
          });
          
          // Si es core y falla reinicio, sistema crítico
          if (exitInfo.tier === "core") {
            logger.error(`CRÍTICO: No se pudo reiniciar módulo core ${mod.id}`);
          }
        }
      }, restartDelay);
    } else {
      logger.error(`${mod.id} alcanzó máximo de reinicios (${this.maxRestarts})`, {
        tier: exitInfo.tier,
        impact: exitInfo.impact
      });
      
      // Si es core, esto es crítico
      if (exitInfo.tier === "core") {
        logger.error(`CRÍTICO: Módulo core ${mod.id} no disponible después de ${this.maxRestarts} intentos`);
      }
    }
  }

  send(moduleId, port, payload) {
    const child = this.processes.get(moduleId);

    if (!child || !child.stdin || child.stdin.destroyed || child.killed) {
      logger.debug(`No se pudo enviar mensaje a ${moduleId}`, {
        port,
        reason: "process_not_available"
      });
      return false;
    }

    // BACKPRESSURE: Verificar antes de enviar
    const bpResult = this.backPressure.registerIncoming(moduleId, { port, payload });
    if (bpResult.action === 'drop') {
      logger.warn(`Message dropped due to backpressure`, {
        target: moduleId,
        port,
        reason: bpResult.reason
      });
      return false;
    }
    if (bpResult.action === 'delay') {
      // Delay aplicado - continuar pero loggear
      logger.debug(`Message delayed due to backpressure`, {
        target: moduleId,
        port,
        delayMs: bpResult.delayMs
      });
    }

    // Extraer contexto interno (_trace_id, _meta) del payload
    const { _trace_id, _meta, ...cleanPayload } = payload || {};

    // Construir mensaje con contexto en el nivel superior
    // Los módulos reciben: { port, payload, trace_id?, meta? }
    const message = { port, payload: cleanPayload };

    if (_trace_id) {
      message.trace_id = _trace_id;
    }

    if (_meta) {
      message.meta = _meta;
    }

    try {
      child.stdin.write(JSON.stringify(message) + "\n");

      // Log de debug con trace_id si existe
      if (_trace_id) {
        logger.debug(`Mensaje enviado a ${moduleId}`, {
          port,
          trace_id: _trace_id
        });
      }

      return true;
    } catch (error) {
      logger.error(`Error enviando mensaje a ${moduleId}`, {
        error: error.message,
        trace_id: _trace_id
      });
      return false;
    }
  }

  route(message) {
    const sourceKey = `${message.module}:${message.port}`;
    let routed = false;

    for (const conn of this.blueprint.connections || []) {
      if (conn.from !== sourceKey) continue;

      const [targetModule, targetPort] = String(conn.to || "").split(":");
      if (!targetModule || !targetPort) {
        logger.error("Conexión inválida en blueprint", { connection: conn });
        continue;
      }

      if (!this.registry.has(targetModule)) {
        logger.error("Target module no encontrado en registry", {
          connection: conn,
          targetModule
        });
        continue;
      }

      let transformed;
      try {
        transformed = applyTransform(conn.transform, message.payload);
      } catch (error) {
        logger.error("Error aplicando transform", {
          connection: conn,
          error: error.message
        });
        continue;
      }

      // Propagar trace_id y meta al mensaje enviado
      const enrichedPayload = {
        ...transformed,
        _trace_id: message.trace_id,
        _meta: message.meta
      };

      this.send(targetModule, targetPort, enrichedPayload);
      routed = true;
    }

    if (!routed) {
      logger.debug(`Mensaje de ${message.module} no enrutado`, {
        port: message.port
      });
    }
  }

  async shutdown(timeoutMs = 5000) {
    this.isShuttingDown = true;
    logger.info("Cerrando runtime...");

    const waits = [];

    for (const [moduleId, child] of this.processes) {
      logger.info(`Cerrando módulo ${moduleId}`);

      waits.push(
        new Promise((resolve) => {
          let finished = false;

          const done = () => {
            if (finished) return;
            finished = true;
            resolve();
          };

          child.once("exit", done);

          try {
            if (child.stdin && !child.stdin.destroyed) {
              child.stdin.end();
            }
            child.kill("SIGTERM");
          } catch (error) {
            logger.error(`Error cerrando ${moduleId}`, {
              error: error.message
            });
            done();
            return;
          }

          setTimeout(() => {
            if (!finished) {
              logger.warn(`Forzando cierre de ${moduleId}`);
              try {
                child.kill("SIGKILL");
              } catch {
                // ignore
              }
              done();
            }
          }, timeoutMs);
        })
      );
    }

    await Promise.allSettled(waits);
    logger.info("Shutdown completado");
  }
}