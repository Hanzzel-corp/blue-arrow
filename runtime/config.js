import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
export const PROJECT_ROOT = path.resolve(__dirname, "..");

class Config {
  constructor() {
    this.environment = process.env.NODE_ENV || "development";
    this.config = this.loadConfig();
  }

  loadJsonFile(filePath) {
    try {
      if (!fs.existsSync(filePath)) return {};
      return JSON.parse(fs.readFileSync(filePath, "utf8"));
    } catch (error) {
      throw new Error(`Config inválida en ${filePath}: ${error.message}`);
    }
  }

  loadConfig() {
    const configDir = path.join(PROJECT_ROOT, "config");

    const defaultConfigPath = path.join(configDir, "default.json");
    let config = this.loadJsonFile(defaultConfigPath);

    const envConfigPath = path.join(configDir, `${this.environment}.json`);
    const envConfig = this.loadJsonFile(envConfigPath);
    config = this.mergeConfigs(config, envConfig);

    config = this.applyEnvironmentOverrides(config);
    return config;
  }

  mergeConfigs(base, override) {
    const safeBase =
      base && typeof base === "object" && !Array.isArray(base) ? base : {};
    const safeOverride =
      override && typeof override === "object" && !Array.isArray(override)
        ? override
        : {};

    const result = { ...safeBase };

    for (const [key, value] of Object.entries(safeOverride)) {
      if (
        typeof value === "object" &&
        value !== null &&
        !Array.isArray(value)
      ) {
        result[key] = this.mergeConfigs(result[key] || {}, value);
      } else {
        result[key] = value;
      }
    }

    return result;
  }

  applyEnvironmentOverrides(config) {
    const overrides = {
      TELEGRAM_BOT_TOKEN: ["telegram", "bot_token"],
      TELEGRAM_WEBHOOK_URL: ["telegram", "webhook_url"],
      LOG_LEVEL: ["logging", "level"],
      DEBUG_MODE: ["runtime", "debug"],
      MESSAGE_VALIDATION: ["runtime", "message_validation"],
      SAFETY_ENABLED: ["safety", "enabled"],
      APPROVAL_ENABLED: ["approval", "enabled"],
      MONITORING_ENABLED: ["monitoring", "enabled"],
      MEMORY_RETENTION_DAYS: ["memory", "retention_days"],
      SUPERVISOR_TASK_TIMEOUT: ["supervisor", "task_timeout"],
      WORKER_DESKTOP_TIMEOUT: ["workers", "desktop", "timeout"],
      WORKER_BROWSER_TIMEOUT: ["workers", "browser", "timeout"],
      WORKER_SYSTEM_TIMEOUT: ["workers", "system", "timeout"]
    };

    for (const [envVar, configPath] of Object.entries(overrides)) {
      const value = process.env[envVar];
      if (value !== undefined) {
        this.setNestedValue(config, configPath, this.parseEnvValue(value));
      }
    }

    return config;
  }

  parseEnvValue(value) {
    try {
      return JSON.parse(value);
    } catch {
      if (value === "true") return true;
      if (value === "false") return false;
      if (/^\d+$/.test(value)) return parseInt(value, 10);
      if (/^\d+\.\d+$/.test(value)) return parseFloat(value);
      return value;
    }
  }

  setNestedValue(obj, pathValue, value) {
    const keys = Array.isArray(pathValue) ? pathValue : pathValue.split(".");
    let current = obj;

    for (let i = 0; i < keys.length - 1; i += 1) {
      const key = keys[i];
      if (
        !(key in current) ||
        typeof current[key] !== "object" ||
        current[key] === null ||
        Array.isArray(current[key])
      ) {
        current[key] = {};
      }
      current = current[key];
    }

    current[keys[keys.length - 1]] = value;
  }

  get(pathValue, defaultValue = undefined) {
    const keys = Array.isArray(pathValue) ? pathValue : pathValue.split(".");
    let current = this.config;

    for (const key of keys) {
      if (current && typeof current === "object" && key in current) {
        current = current[key];
      } else {
        return defaultValue;
      }
    }

    return current;
  }

  set(pathValue, value) {
    this.setNestedValue(this.config, pathValue, value);
  }

  has(pathValue) {
    return this.get(pathValue) !== undefined;
  }

  getAll() {
    return JSON.parse(JSON.stringify(this.config));
  }

  reload() {
    this.config = this.loadConfig();
    return this.config;
  }

  getEnvironment() {
    return this.environment;
  }

  isDevelopment() {
    return this.environment === "development";
  }

  isProduction() {
    return this.environment === "production";
  }

  isTest() {
    return this.environment === "test";
  }

  getLoggingConfig() {
    const cfg = this.get("logging", {});
    return {
      level: cfg?.level || "info",
      console: cfg?.console !== false,
      file: cfg?.file !== false,
      structured: cfg?.structured === true
    };
  }

  getRuntimeConfig() {
    return this.get("runtime", {});
  }

  getTelegramConfig() {
    return this.get("telegram", {});
  }

  getMonitoringConfig() {
    return this.get("monitoring", {});
  }

  getSupervisorConfig() {
    return this.get("supervisor", {});
  }

  getWorkersConfig() {
    return this.get("workers", {});
  }

  getSafetyConfig() {
    return this.get("safety", {});
  }

  getApprovalConfig() {
    return this.get("approval", {});
  }
}

export const config = new Config();
export { Config };
