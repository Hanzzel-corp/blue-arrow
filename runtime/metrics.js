import http from "http";
import { config } from "./config.js";
import { getLogger } from "./logger.js";

class MetricsCollector {
  constructor() {
    this.counters = new Map();
    this.gauges = new Map();
    this.histograms = new Map();
    this.logger = getLogger("metrics");
    this.enabled = config.get("monitoring.enabled", false);
    this.startTime = Date.now();
    this.server = null;
    this.collectInterval = null;

    if (this.enabled) {
      this.startMetricsServer();
      this.startSystemCollection();
    }
  }

  incrementCounter(name, labels = {}, value = 1) {
    if (!this.enabled) return;

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) return;

    const key = this.createKey(name, labels);
    const current = this.counters.get(key) || 0;
    this.counters.set(key, current + numericValue);
  }

  getCounter(name, labels = {}) {
    if (!this.enabled) return 0;
    return this.counters.get(this.createKey(name, labels)) || 0;
  }

  setGauge(name, value, labels = {}) {
    if (!this.enabled) return;

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) return;

    this.gauges.set(this.createKey(name, labels), numericValue);
  }

  getGauge(name, labels = {}) {
    if (!this.enabled) return 0;
    return this.gauges.get(this.createKey(name, labels)) || 0;
  }

  recordHistogram(name, value, labels = {}) {
    if (!this.enabled) return;

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) return;

    const key = this.createKey(name, labels);
    if (!this.histograms.has(key)) {
      this.histograms.set(key, []);
    }

    const values = this.histograms.get(key);
    values.push(numericValue);

    // Mantener solo las últimas 1000 muestras
    if (values.length > 1000) {
      values.splice(0, values.length - 1000);
    }
  }

  createKey(name, labels) {
    const safeName = String(name || "").trim();
    const safeLabels =
      labels && typeof labels === "object" && !Array.isArray(labels) ? labels : {};

    const labelStr = Object.entries(safeLabels)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}="${String(v)}"`)
      .join(",");

    return labelStr ? `${safeName}{${labelStr}}` : safeName;
  }

  splitMetricKey(key) {
    const idx = key.indexOf("{");
    if (idx === -1) {
      return { name: key, labels: {} };
    }

    const name = key.slice(0, idx);
    const labelsRaw = key.slice(idx + 1, -1);
    const labels = {};

    if (!labelsRaw.trim()) {
      return { name, labels };
    }

    for (const pair of labelsRaw.split(",")) {
      const [k, v] = pair.split("=");
      if (k && v) {
        labels[k] = v.replace(/^"|"$/g, "");
      }
    }

    return { name, labels };
  }

  percentile(sortedValues, p) {
    if (!Array.isArray(sortedValues) || sortedValues.length === 0) return null;
    const index = Math.min(
      sortedValues.length - 1,
      Math.max(0, Math.floor((sortedValues.length - 1) * p))
    );
    return sortedValues[index];
  }

  getHistogramStats(name, labels = {}) {
    if (!this.enabled) return null;

    const key = this.createKey(name, labels);
    const values = this.histograms.get(key) || [];

    if (values.length === 0) return null;

    const sorted = [...values].sort((a, b) => a - b);
    const sum = values.reduce((a, b) => a + b, 0);

    return {
      count: values.length,
      sum,
      min: sorted[0],
      max: sorted[sorted.length - 1],
      mean: sum / values.length,
      p50: this.percentile(sorted, 0.5),
      p95: this.percentile(sorted, 0.95),
      p99: this.percentile(sorted, 0.99)
    };
  }

  startTimer(name, labels = {}) {
    if (!this.enabled) return () => 0;

    const startTime = process.hrtime.bigint();

    return () => {
      const endTime = process.hrtime.bigint();
      const durationMs = Number(endTime - startTime) / 1000000;
      this.recordHistogram(`${name}_duration_ms`, durationMs, labels);
      return durationMs;
    };
  }

  collectSystemMetrics() {
    if (!this.enabled) return;

    const memUsage = process.memoryUsage();
    const cpuUsage = process.cpuUsage();

    this.setGauge("process_memory_bytes", memUsage.rss, { type: "rss" });
    this.setGauge("process_memory_bytes", memUsage.heapTotal, { type: "heap_total" });
    this.setGauge("process_memory_bytes", memUsage.heapUsed, { type: "heap_used" });
    this.setGauge("process_memory_bytes", memUsage.external, { type: "external" });

    this.setGauge("process_cpu_microseconds", cpuUsage.user, { type: "user" });
    this.setGauge("process_cpu_microseconds", cpuUsage.system, { type: "system" });
    this.setGauge("uptime_seconds", Math.floor((Date.now() - this.startTime) / 1000));
  }

  startSystemCollection() {
    if (!this.enabled || this.collectInterval) return;

    this.collectSystemMetrics();
    this.collectInterval = setInterval(() => {
      try {
        this.collectSystemMetrics();
      } catch (error) {
        this.logger.warn("Error collecting system metrics", {
          error: error.message
        });
      }
    }, 15000);
  }

  exportPrometheusFormat() {
    if (!this.enabled) return "";

    let output = "";

    // Counters
    const counterNames = new Set(
      Array.from(this.counters.keys()).map((key) => this.splitMetricKey(key).name)
    );
    for (const name of counterNames) {
      output += `# TYPE ${name} counter\n`;
      for (const [key, value] of this.counters.entries()) {
        const parsed = this.splitMetricKey(key);
        if (parsed.name === name) {
          output += `${key} ${value}\n`;
        }
      }
    }

    // Gauges
    const gaugeNames = new Set(
      Array.from(this.gauges.keys()).map((key) => this.splitMetricKey(key).name)
    );
    for (const name of gaugeNames) {
      output += `# TYPE ${name} gauge\n`;
      for (const [key, value] of this.gauges.entries()) {
        const parsed = this.splitMetricKey(key);
        if (parsed.name === name) {
          output += `${key} ${value}\n`;
        }
      }
    }

    // Histograms exported as summary-style stats
    const histogramNames = new Set(
      Array.from(this.histograms.keys()).map((key) => this.splitMetricKey(key).name)
    );
    for (const name of histogramNames) {
      output += `# TYPE ${name} summary\n`;

      for (const [key] of this.histograms.entries()) {
        const parsed = this.splitMetricKey(key);
        if (parsed.name !== name) continue;

        const stats = this.getHistogramStats(parsed.name, parsed.labels);
        if (!stats) continue;

        const baseLabels = Object.entries(parsed.labels)
          .map(([k, v]) => `${k}="${v}"`)
          .join(",");

        const q = (quantile) =>
          baseLabels
            ? `${name}{${baseLabels},quantile="${quantile}"}`
            : `${name}{quantile="${quantile}"}`;

        const countKey = baseLabels ? `${name}_count{${baseLabels}}` : `${name}_count`;
        const sumKey = baseLabels ? `${name}_sum{${baseLabels}}` : `${name}_sum`;

        output += `${q("0.5")} ${stats.p50}\n`;
        output += `${q("0.95")} ${stats.p95}\n`;
        output += `${q("0.99")} ${stats.p99}\n`;
        output += `${countKey} ${stats.count}\n`;
        output += `${sumKey} ${stats.sum}\n`;
      }
    }

    return output;
  }

  startMetricsServer() {
    if (!this.enabled || this.server) return;

    const port = config.get("monitoring.port", 9464);
    const host = config.get("monitoring.host", "0.0.0.0");

    this.server = http.createServer((req, res) => {
      if (req.url === "/metrics") {
        try {
          const body = this.exportPrometheusFormat();
          res.writeHead(200, { "Content-Type": "text/plain; version=0.0.4" });
          res.end(body);
        } catch (error) {
          this.logger.error("Metrics export failed", { error: error.message });
          res.writeHead(500, { "Content-Type": "text/plain" });
          res.end("metrics export error");
        }
        return;
      }

      if (req.url === "/health") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({
            ok: true,
            enabled: this.enabled,
            uptime_seconds: Math.floor((Date.now() - this.startTime) / 1000)
          })
        );
        return;
      }

      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("not found");
    });

    this.server.listen(port, host, () => {
      this.logger.info("Metrics server started", { host, port });
    });

    this.server.on("error", (error) => {
      this.logger.error("Metrics server error", { error: error.message });
    });
  }

  stop() {
    if (this.collectInterval) {
      clearInterval(this.collectInterval);
      this.collectInterval = null;
    }

    if (this.server) {
      this.server.close();
      this.server = null;
    }
  }
}

let instance = null;

export function getMetricsCollector() {
  if (!instance) {
    instance = new MetricsCollector();
  }
  return instance;
}

export function resetMetricsCollector() {
  if (instance) {
    instance.stop();
  }
  instance = null;
}