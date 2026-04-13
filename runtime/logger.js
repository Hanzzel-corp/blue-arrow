import fs from "fs";
import path from "path";
import { config, PROJECT_ROOT } from "./config.js";

class Logger {
  constructor(moduleId) {
    this.moduleId = moduleId;
  }

  getCurrentConfig() {
    return config.getLoggingConfig();
  }

  getLogLevelNumber(level) {
    const levels = {
      error: 0,
      warn: 1,
      info: 2,
      debug: 3,
      trace: 4
    };
    return levels[level] ?? 2;
  }

  shouldLog(level) {
    const cfg = this.getCurrentConfig();
    const currentLevel = this.getLogLevelNumber(cfg.level || "info");
    return this.getLogLevelNumber(level) <= currentLevel;
  }

  formatMessage(level, message, meta = {}) {
    const timestamp = new Date().toISOString();
    const logEntry = {
      timestamp,
      level: level.toUpperCase(),
      module: this.moduleId,
      message,
      ...meta
    };

    const cfg = this.getCurrentConfig();
    if (cfg.structured) {
      return JSON.stringify(logEntry);
    }

    const metaStr =
      Object.keys(meta).length > 0 ? ` ${JSON.stringify(meta)}` : "";
    return `[${timestamp}] ${level.toUpperCase()} [${this.moduleId}] ${message}${metaStr}`;
  }

  writeLog(level, formattedMessage) {
    const cfg = this.getCurrentConfig();

    if (cfg.console !== false) {
      if (level === "error") console.error(formattedMessage);
      else if (level === "warn") console.warn(formattedMessage);
      else console.log(formattedMessage);
    }

    if (cfg.file !== false) {
      const logsDir = config.get("runtime.logs_dir", "logs");
      const logFile = path.join(PROJECT_ROOT, logsDir, "blueprint.log");

      try {
        fs.mkdirSync(path.dirname(logFile), { recursive: true });
        fs.writeFileSync(logFile, formattedMessage + "\n", { flag: "a" });
      } catch (error) {
        console.error("Failed to write to log file:", error.message);
      }
    }
  }

  error(message, meta = {}) {
    if (!this.shouldLog("error")) return;
    const formatted = this.formatMessage("error", message, meta);
    this.writeLog("error", formatted);
  }

  warn(message, meta = {}) {
    if (!this.shouldLog("warn")) return;
    const formatted = this.formatMessage("warn", message, meta);
    this.writeLog("warn", formatted);
  }

  info(message, meta = {}) {
    if (!this.shouldLog("info")) return;
    const formatted = this.formatMessage("info", message, meta);
    this.writeLog("info", formatted);
  }

  debug(message, meta = {}) {
    if (!this.shouldLog("debug")) return;
    const formatted = this.formatMessage("debug", message, meta);
    this.writeLog("debug", formatted);
  }

  trace(message, meta = {}) {
    if (!this.shouldLog("trace")) return;
    const formatted = this.formatMessage("trace", message, meta);
    this.writeLog("trace", formatted);
  }
}

const loggers = new Map();

export function getLogger(moduleId) {
  if (!loggers.has(moduleId)) {
    loggers.set(moduleId, new Logger(moduleId));
  }
  return loggers.get(moduleId);
}

export const logger = getLogger("runtime");
export { Logger };