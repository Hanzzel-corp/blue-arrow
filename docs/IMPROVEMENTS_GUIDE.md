# Guía de Mejoras - blueprint-v0

**Versión**: 1.0.0  
**Fecha**: 2026-04-07

> **⚠️ NOTA IMPORTANTE**: Los snippets de este documento son **conceptuales** y deben adaptarse al [contrato v2](../docs/PORT_CONTRACTS.md) antes de implementarse. El contrato v2 requiere: `module`, `port`, `trace_id`, y `meta` a nivel superior del envelope. Algunos ejemplos pueden usar nombres de acciones legacy (ej: `search_google` → `search`) que deben actualizarse a la nomenclatura actual.

---

## Resumen Ejecutivo

Esta guía detalla las mejoras prioritarias identificadas en la auditoría del proyecto. Las mejoras están organizadas por criticidad y área técnica, con ejemplos conceptuales listos para adaptar.

---

## 1. Mejoras Críticas (Seguridad/Estabilidad)

### 1.1 Circuit Breaker para Reinicios de Módulos

**Problema**: El bus reinicia módulos ciegamente hasta 3 veces sin considerar patrones de fallo.

**Solución**:

```javascript
// runtime/circuit_breaker.js
export class CircuitBreaker {
  constructor(moduleId, opts = {}) {
    this.moduleId = moduleId;
    this.failureThreshold = opts.failureThreshold || 5;
    this.resetTimeout = opts.resetTimeout || 30000;
    this.halfOpenMaxCalls = opts.halfOpenMaxCalls || 3;
    this.state = 'CLOSED';
    this.failures = 0;
    this.successes = 0;
    this.lastFailureTime = null;
    this.nextAttempt = null;
  }

  canExecute() {
    if (this.state === 'CLOSED') return true;
    if (this.state === 'OPEN') {
      if (Date.now() >= this.nextAttempt) {
        this.state = 'HALF_OPEN';
        this.successes = 0;
        return true;
      }
      return false;
    }
    if (this.state === 'HALF_OPEN') {
      return this.successes < this.halfOpenMaxCalls;
    }
    return true;
  }

  recordSuccess() {
    this.failures = 0;
    if (this.state === 'HALF_OPEN') {
      this.successes++;
      if (this.successes >= this.halfOpenMaxCalls) {
        this.state = 'CLOSED';
      }
    }
  }

  recordFailure() {
    this.failures++;
    this.lastFailureTime = Date.now();
    if (this.failures >= this.failureThreshold) {
      this.state = 'OPEN';
      this.nextAttempt = Date.now() + this.resetTimeout;
    }
  }
}
```

**Integración en bus.js**:

```javascript
// Modificar runtime/bus.js
import { CircuitBreaker } from './circuit_breaker.js';

class RuntimeBus {
  constructor() {
    this.circuitBreakers = new Map();
  }

  handleModuleExit(mod, code, signal) {
    const cb = this.getCircuitBreaker(mod.id);
    cb.recordFailure();
    
    if (!cb.canExecute()) {
      logger.error(`Circuit breaker abierto para ${mod.id}, esperando ${cb.resetTimeout}ms`);
      return;
    }
    
    // Continuar con reinicio...
  }
}
```

---

### 1.2 Backpressure en el Bus de Mensajes

**Problema**: Sin control de flujo, el buffer de stdin puede crecer indefinidamente causando OOM.

**Solución**:

```javascript
// Modificar runtime/bus.js
class RuntimeBus {
  constructor() {
    this.messageQueues = new Map();
    this.processing = new Map();
  }

  async send(moduleId, port, payload) {
    const child = this.processes.get(moduleId);
    if (!child?.stdin?.writable) {
      logger.debug(`No se pudo enviar mensaje a ${moduleId}`, { port });
      return false;
    }

    // Control de flujo: si el buffer está lleno, encolar
    if (child.stdin.writableNeedDrain) {
      logger.warn(`Backpressure en ${moduleId}, encolando mensaje`);
      
      if (!this.messageQueues.has(moduleId)) {
        this.messageQueues.set(moduleId, []);
      }
      
      this.messageQueues.get(moduleId).push({ port, payload, timestamp: Date.now() });
      
      // Limitar tamaño de cola
      const queue = this.messageQueues.get(moduleId);
      if (queue.length > 100) {
        queue.shift(); // Drop oldest
        logger.error(`Cola de ${moduleId} excedió límite, mensaje antiguo descartado`);
      }
      
      return false;
    }

    const written = child.stdin.write(JSON.stringify({ port, payload }) + "\n");
    
    if (!written) {
      child.stdin.once('drain', () => this.processQueue(moduleId));
    }
    
    return true;
  }

  processQueue(moduleId) {
    const queue = this.messageQueues.get(moduleId);
    if (!queue || queue.length === 0) return;

    const child = this.processes.get(moduleId);
    if (!child?.stdin?.writable) return;

    // Procesar mensajes encolados
    while (queue.length > 0 && !child.stdin.writableNeedDrain) {
      const { port, payload } = queue.shift();
      child.stdin.write(JSON.stringify({ port, payload }) + "\n");
    }

    if (queue.length > 0) {
      child.stdin.once('drain', () => this.processQueue(moduleId));
    }
  }
}
```

---

### 1.3 Schema Validation en Registry

**Problema**: No hay validación de manifests, JSON inválido causa crashes silenciosos.

**Solución**:

```javascript
// runtime/schema.js
export const ManifestSchema = {
  validate(manifest) {
    const required = ['id', 'entry', 'language'];
    for (const field of required) {
      if (!manifest[field]) {
        throw new Error(`Manifest inválido: falta campo requerido '${field}'`);
      }
    }
    
    if (!/^[a-z0-9._-]+$/.test(manifest.id)) {
      throw new Error(`Manifest inválido: id '${manifest.id}' contiene caracteres inválidos`);
    }
    
    if (!['node', 'python'].includes(manifest.language)) {
      throw new Error(`Manifest inválido: language '${manifest.language}' no soportado`);
    }
    
    // Validar puertos si existen
    if (manifest.inputs) {
      if (!Array.isArray(manifest.inputs)) {
        throw new Error(`Manifest inválido: inputs debe ser un array`);
      }
    }
    
    if (manifest.outputs) {
      if (!Array.isArray(manifest.outputs)) {
        throw new Error(`Manifest inválido: outputs debe ser un array`);
      }
    }
    
    return true;
  }
};
```

```javascript
// Modificar runtime/registry.js
import { ManifestSchema } from './schema.js';

export function loadManifest(moduleDir) {
  const manifestPath = path.join(moduleDir, "manifest.json");
  
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`Manifest no encontrado: ${manifestPath}`);
  }
  
  let content;
  try {
    content = fs.readFileSync(manifestPath, "utf8");
  } catch (err) {
    throw new Error(`No se pudo leer manifest: ${err.message}`);
  }
  
  let manifest;
  try {
    manifest = JSON.parse(content);
  } catch (err) {
    throw new Error(`JSON inválido en ${manifestPath}: ${err.message}`);
  }
  
  ManifestSchema.validate(manifest);
  
  return manifest;
}
```

---

## 2. Mejoras de Robustez

### 2.1 Manejo Defensivo de JSON en Todos los Módulos

**Patrón a aplicar en cada módulo Node.js**:

```javascript
// Template para cualquier main.js
import readline from "readline";

const MODULE_ID = "nombre.modulo";
const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

function emit(port, payload) {
  try {
    process.stdout.write(
      JSON.stringify({ module: MODULE_ID, port, payload }) + "\n"
    );
  } catch (err) {
    console.error(`[${MODULE_ID}] Error emitiendo mensaje:`, err.message);
  }
}

function emitError(context, error, originalPayload = null) {
  emit("event.out", {
    level: "error",
    module: MODULE_ID,
    context,
    error: error.message,
    stack: error.stack,
    original_payload: originalPayload,
    timestamp: new Date().toISOString()
  });
}

rl.on("line", (line) => {
  if (!line || !line.trim()) return;
  
  let msg;
  try {
    msg = JSON.parse(line);
  } catch (err) {
    emitError("json_parse", err, { raw_line: line.slice(0, 200) });
    return;
  }
  
  // Validar estructura mínima
  if (!msg || typeof msg !== "object") {
    emitError("invalid_message_structure", new Error("Mensaje no es un objeto"), msg);
    return;
  }
  
  if (!msg.port) {
    emitError("missing_port", new Error("Mensaje sin campo 'port'"), msg);
    return;
  }
  
  try {
    processMessage(msg);
  } catch (err) {
    emitError("message_processing", err, msg);
    // Emitir resultado de error para no dejar colgada la operación
    if (msg.payload?.task_id) {
      emit("result.out", {
        task_id: msg.payload.task_id,
        status: "error",
        error: err.message,
        module: MODULE_ID
      });
    }
  }
});

function processMessage(msg) {
  // Implementación específica del módulo
  switch (msg.port) {
    case "action.in":
      handleAction(msg.payload);
      break;
    default:
      emitError("unknown_port", new Error(`Puerto desconocido: ${msg.port}`), msg);
  }
}
```

**Módulos a modificar**:
- `modules/agent/main.js`
- `modules/router/main.js`
- `modules/safety-guard/main.js`
- `modules/approval/main.js`
- `modules/supervisor/main.js`
- `modules/memory-log/main.js`
- `modules/menus/hud/main.js`
- `modules/menus/tray/main.js`
- `modules/menus/telegram/main.js`

---

### 2.2 Garbage Collection de Estado

**Problema**: Maps de deduplicación crecen indefinidamente.

**Solución para router/main.js**:

```javascript
// Agregar a modules/router/main.js
const recentTasks = new Map();
const TASK_TTL_MS = 60000; // 1 minuto
const GC_INTERVAL_MS = 30000; // 30 segundos

// Garbage collector periódico
setInterval(() => {
  const now = Date.now();
  let cleaned = 0;
  
  for (const [key, timestamp] of recentTasks) {
    if (now - timestamp > TASK_TTL_MS) {
      recentTasks.delete(key);
      cleaned++;
    }
  }
  
  if (cleaned > 0) {
    emit("event.out", {
      level: "debug",
      type: "gc_tasks",
      cleaned,
      remaining: recentTasks.size
    });
  }
}, GC_INTERVAL_MS);

// Versión alternativa con WeakRef (si el runtime lo soporta)
class TaskDeduplicator {
  constructor(ttlMs = 60000) {
    this.tasks = new Map();
    this.ttlMs = ttlMs;
    this.gcInterval = setInterval(() => this.gc(), ttlMs / 2);
  }
  
  check(action, meta = {}, params = {}) {
    const key = this.makeKey(action, meta, params);
    const now = Date.now();
    const prev = this.tasks.get(key);
    
    if (prev && now - prev < this.ttlMs) {
      return { shouldSkip: true, key, elapsed: now - prev };
    }
    
    this.tasks.set(key, now);
    return { shouldSkip: false, key };
  }
  
  gc() {
    const now = Date.now();
    for (const [key, timestamp] of this.tasks) {
      if (now - timestamp > this.ttlMs) {
        this.tasks.delete(key);
      }
    }
  }
  
  makeKey(action, meta, params) {
    return [
      action || "unknown_action",
      meta?.chat_id || "global",
      this.stableStringify(params || {})
    ].join("::");
  }
  
  stableStringify(value) {
    if (value === null || typeof value !== "object") {
      return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
      return `[${value.map(v => this.stableStringify(v)).join(",")}]`;
    }
    const keys = Object.keys(value).sort();
    return `{${keys.map(k => `${JSON.stringify(k)}:${this.stableStringify(value[k])}`).join(",")}}`;
  }
  
  destroy() {
    clearInterval(this.gcInterval);
    this.tasks.clear();
  }
}
```

---

### 2.3 Fallback para IA sin Ollama

**Problema**: El asistente de IA falla completamente si Ollama no está disponible.

**Solución**:

```python
# Modificar ai-assistant/main.py
class DegradedModeHandler:
    """Maneja consultas cuando Ollama no está disponible."""
    
    SUGGESTED_ACTIONS = [
        "search_file",
        "monitor_resources",
        "open_url",
        "search_google"
    ]
    
    FALLBACK_RESPONSES = {
        "ai.query": "Servicio de IA no disponible. Puedo ayudarte con comandos tradicionales como buscar archivos o monitorear recursos.",
        "ai.analyze_intent": {"intent": "unknown", "confidence": 0, "fallback": True},
        "ai.generate_code": "# IA no disponible. Generación de código requiere Ollama.",
        "ai.explain_error": "No puedo analizar errores sin el servicio de IA activo.",
        "ai.analyze_project": {"status": "unavailable", "suggestion": "Reintenta cuando Ollama esté activo"}
    }
    
    def __init__(self, llama_interface):
        self.llama = llama_interface
        self.degraded_mode = not llama_interface.check_ollama_available()
        
    def process(self, action, params):
        if not self.degraded_mode:
            return None  # Delegar a IA normal
            
        result = self.FALLBACK_RESPONSES.get(action, {})
        
        return {
            "success": False,
            "degraded_mode": True,
            "response": result if isinstance(result, str) else None,
            "structured_result": result if not isinstance(result, str) else None,
            "error": "Servicio de IA (Ollama) no disponible",
            "suggested_actions": self.SUGGESTED_ACTIONS,
            "alternative_commands": self._suggest_alternatives(params)
        }
    
    def _suggest_alternatives(self, params):
        query = params.get("query", "").lower()
        suggestions = []
        
        if any(word in query for word in ["buscar", "encontrar", "archivo"]):
            suggestions.append("search_file")
        if any(word in query for word in ["sistema", "cpu", "memoria"]):
            suggestions.append("monitor_resources")
        if any(word in query for word in ["navegar", "web", "url"]):
            suggestions.append("open_url")
            
        return suggestions

# Integración en handle_action()
def handle_action(action, params, meta):
    llama = LLaMAInterface()
    degraded = DegradedModeHandler(llama)
    
    # Intentar fallback primero
    fallback_result = degraded.process(action, params)
    if fallback_result:
        emit_guaranteed_result(meta.get("task_id"), fallback_result)
        return
    
    # Continuar con procesamiento normal...
```

---

## 3. Mejoras de Observabilidad

### 3.1 Distributed Tracing

**Implementación de trace IDs**:

```javascript
// runtime/tracing.js
export class Tracer {
  static generateId() {
    return `${Date.now().toString(36)}-${Math.random().toString(36).substr(2, 9)}`;
  }
  
  static injectTraceContext(payload, currentSpan = null) {
    const traceId = payload?.meta?.trace_id || this.generateId();
    const spanId = this.generateId();
    
    return {
      ...payload,
      meta: {
        ...payload.meta,
        trace_id: traceId,
        span_id: spanId,
        parent_span_id: currentSpan?.span_id || payload?.meta?.span_id,
        trace_timestamp: Date.now()
      }
    };
  }
  
  static createSpan(traceId, name, parentSpanId = null) {
    return {
      trace_id: traceId,
      span_id: this.generateId(),
      parent_span_id: parentSpanId,
      name,
      start_time: Date.now(),
      end_time: null,
      status: "running"
    };
  }
  
  static endSpan(span, status = "ok", error = null) {
    span.end_time = Date.now();
    span.status = status;
    span.error = error;
    span.duration_ms = span.end_time - span.start_time;
    return span;
  }
}

// Modificar runtime/bus.js para propagar trazas
route(message) {
  // Inyectar contexto de tracing si no existe
  if (!message.payload?.meta?.trace_id) {
    message.payload = Tracer.injectTraceContext(message.payload);
  }
  
  const connections = this.blueprint.connections.filter(
    (c) => c.from.module === message.module && c.from.port === message.port
  );
  
  for (const conn of connections) {
    const targetModule = conn.to.module;
    const targetPort = conn.to.port;
    
    // Propagar trace context al mensaje destino
    const tracedPayload = Tracer.injectTraceContext(
      message.payload,
      { span_id: message.payload.meta.span_id }
    );
    
    this.send(targetModule, targetPort, tracedPayload);
    
    // Emitir evento de tracing
    this.emitTracingEvent("message_routed", {
      trace_id: tracedPayload.meta.trace_id,
      from: { module: message.module, port: message.port },
      to: { module: targetModule, port: targetPort },
      span_id: tracedPayload.meta.span_id,
      parent_span_id: tracedPayload.meta.parent_span_id
    });
  }
}
```

---

### 3.2 Health Check API

```javascript
// runtime/health.js
export class HealthMonitor {
  constructor(bus) {
    this.bus = bus;
    this.checks = new Map();
    this.startTime = Date.now();
  }
  
  registerCheck(name, checkFn, intervalMs = 30000) {
    this.checks.set(name, { fn: checkFn, interval: intervalMs, lastResult: null });
    setInterval(() => this.runCheck(name), intervalMs);
  }
  
  async runCheck(name) {
    const check = this.checks.get(name);
    if (!check) return;
    
    try {
      const start = Date.now();
      const result = await check.fn();
      check.lastResult = {
        status: result ? "healthy" : "unhealthy",
        latency_ms: Date.now() - start,
        timestamp: Date.now()
      };
    } catch (err) {
      check.lastResult = {
        status: "error",
        error: err.message,
        timestamp: Date.now()
      };
    }
  }
  
  getHealth() {
    const modules = [];
    for (const [id, proc] of this.bus.processes) {
      modules.push({
        id,
        pid: proc.pid,
        killed: proc.killed,
        exit_code: proc.exitCode,
        restart_count: this.bus.moduleRestartCount.get(id) || 0,
        connected: !proc.stdin?.destroyed && !proc.stdout?.destroyed
      });
    }
    
    return {
      status: this.getOverallStatus(),
      uptime_ms: Date.now() - this.startTime,
      modules: {
        total: modules.length,
        running: modules.filter(m => !m.killed).length,
        failed: modules.filter(m => m.killed).length,
        details: modules
      },
      checks: Object.fromEntries(
        Array.from(this.checks.entries()).map(([name, check]) => [
          name,
          check.lastResult
        ])
      ),
      blueprint: {
        valid: this.validateBlueprint(),
        module_count: this.bus.blueprint?.modules?.length || 0,
        connection_count: this.bus.blueprint?.connections?.length || 0
      }
    };
  }
  
  getOverallStatus() {
    const failedModules = Array.from(this.bus.processes.values()).filter(p => p.killed).length;
    if (failedModules > 0) return "degraded";
    if (Array.from(this.checks.values()).some(c => c.lastResult?.status === "error")) return "degraded";
    return "healthy";
  }
  
  validateBlueprint() {
    try {
      // Verificar que todos los módulos del blueprint están registrados
      const registered = new Set(this.bus.registry.keys());
      for (const mod of this.bus.blueprint?.modules || []) {
        if (!registered.has(mod.id)) return false;
      }
      return true;
    } catch {
      return false;
    }
  }
}

// Exponer endpoint de health
process.on('message', (msg) => {
  if (msg.type === 'health_check') {
    process.send({
      type: 'health_status',
      health: healthMonitor.getHealth()
    });
  }
});
```

---

### 3.3 Métricas Estadísticas

```javascript
// runtime/metrics.js
export class MetricsCollector {
  constructor() {
    this.counters = new Map();
    this.gauges = new Map();
    this.histograms = new Map();
    this.timers = new Map();
  }
  
  counter(name, labels = {}) {
    const key = this.makeKey(name, labels);
    const current = this.counters.get(key) || 0;
    this.counters.set(key, current + 1);
  }
  
  gauge(name, value, labels = {}) {
    const key = this.makeKey(name, labels);
    this.gauges.set(key, value);
  }
  
  histogram(name, value, labels = {}, buckets = [10, 50, 100, 500, 1000, 5000]) {
    const key = this.makeKey(name, labels);
    if (!this.histograms.has(key)) {
      this.histograms.set(key, { buckets: new Map(), sum: 0, count: 0 });
    }
    
    const hist = this.histograms.get(key);
    hist.sum += value;
    hist.count++;
    
    for (const bucket of buckets) {
      if (value <= bucket) {
        const bucketKey = `le_${bucket}`;
        hist.buckets.set(bucketKey, (hist.buckets.get(bucketKey) || 0) + 1);
      }
    }
  }
  
  timer(name, fn, labels = {}) {
    const start = performance.now();
    try {
      const result = fn();
      this.histogram(name, performance.now() - start, labels);
      return result;
    } catch (err) {
      this.histogram(`${name}_errors`, performance.now() - start, labels);
      throw err;
    }
  }
  
  makeKey(name, labels) {
    const labelStr = Object.entries(labels)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${k}=${v}`)
      .join(',');
    return labelStr ? `${name}{${labelStr}}` : name;
  }
  
  exportPrometheus() {
    const lines = [];
    
    for (const [key, value] of this.counters) {
      lines.push(`# TYPE ${key} counter`);
      lines.push(`${key} ${value}`);
    }
    
    for (const [key, value] of this.gauges) {
      lines.push(`# TYPE ${key} gauge`);
      lines.push(`${key} ${value}`);
    }
    
    for (const [key, hist] of this.histograms) {
      lines.push(`# TYPE ${key} histogram`);
      for (const [bucket, count] of hist.buckets) {
        lines.push(`${key}_bucket{${bucket}} ${count}`);
      }
      lines.push(`${key}_sum ${hist.sum}`);
      lines.push(`${key}_count ${hist.count}`);
    }
    
    return lines.join('\n');
  }
  
  snapshot() {
    return {
      counters: Object.fromEntries(this.counters),
      gauges: Object.fromEntries(this.gauges),
      histograms: Object.fromEntries(
        Array.from(this.histograms.entries()).map(([k, v]) => [k, { ...v, buckets: Object.fromEntries(v.buckets) }])
      ),
      timestamp: Date.now()
    };
  }
}
```

---

## 4. Mejoras de Developer Experience

### 4.1 Implementar Transforms

```javascript
// runtime/transforms.js
const transforms = {
  // Agregar timestamp al payload
  add_timestamp: (payload) => ({
    ...payload,
    _timestamp: Date.now(),
    _iso_timestamp: new Date().toISOString()
  }),
  
  // Extraer chat_id de meta anidada
  extract_chat_id: (payload) => ({
    ...payload,
    chat_id: payload?.meta?.chat_id || payload?.chat_id || null
  }),
  
  // Envolver en array si no lo es
  wrap_in_array: (payload) => 
    Array.isArray(payload) ? payload : [payload],
  
  // Aplanar estructura anidada
  flatten_meta: (payload) => ({
    ...payload,
    ...payload.meta,
    _original_meta: payload.meta
  }),
  
  // Agregar info del módulo emisor
  add_source_info: (payload, context) => ({
    ...payload,
    _source_module: context.sourceModule,
    _source_port: context.sourcePort,
    _routed_at: Date.now()
  }),
  
  // Filtrar campos sensibles
  sanitize: (payload) => {
    const sensitive = ['password', 'token', 'secret', 'api_key'];
    const sanitized = { ...payload };
    for (const key of Object.keys(sanitized)) {
      if (sensitive.some(s => key.toLowerCase().includes(s))) {
        sanitized[key] = '[REDACTED]';
      }
    }
    return sanitized;
  },
  
  // Validar y transformar payload de error
  error_envelope: (payload) => ({
    success: false,
    error: typeof payload === 'string' ? payload : payload?.error || 'Unknown error',
    details: payload,
    timestamp: Date.now()
  }),
  
  // Transformar resultado de IA
  ai_result_transform: (payload) => {
    if (typeof payload === 'string') {
      return { response: payload, structured: null, confidence: 1.0 };
    }
    return {
      response: payload.response || payload.text || JSON.stringify(payload),
      structured: typeof payload === 'object' ? payload : null,
      confidence: payload.confidence || 1.0
    };
  }
};

export function applyTransform(name, payload, context = {}) {
  const transform = transforms[name];
  if (!transform) {
    console.warn(`Transform '${name}' no encontrado, retornando payload sin cambios`);
    return payload;
  }
  
  try {
    return transform(payload, context);
  } catch (err) {
    console.error(`Error aplicando transform '${name}':`, err);
    return payload;
  }
}

export function listTransforms() {
  return Object.keys(transforms);
}

export function registerTransform(name, fn) {
  transforms[name] = fn;
}
```

---

### 4.2 Hot Reload para Desarrollo

```javascript
// runtime/hot_reload.js
import fs from 'fs';
import path from 'path';

export class HotReloadManager {
  constructor(bus) {
    this.bus = bus;
    this.watchers = new Map();
    this.debounceTimers = new Map();
  }
  
  enable() {
    if (process.env.NODE_ENV !== 'development') {
      console.log('Hot reload solo disponible en modo development');
      return;
    }
    
    const modulesDir = path.join(process.cwd(), 'modules');
    
    fs.watch(modulesDir, { recursive: true }, (eventType, filename) => {
      if (!filename) return;
      
      // Solo reaccionar a cambios en archivos principales
      if (!filename.includes('main.') && filename !== 'manifest.json') {
        return;
      }
      
      const moduleDir = this.extractModuleDir(filename);
      if (!moduleDir) return;
      
      // Debounce para evitar múltiples reinicios rápidos
      this.debounce(moduleDir, () => {
        this.reloadModule(moduleDir);
      }, 500);
    });
    
    console.log('Hot reload habilitado');
  }
  
  extractModuleDir(filename) {
    const parts = filename.split(path.sep);
    if (parts.length < 2) return null;
    return parts[0]; // e.g., "agent" de "agent/main.js"
  }
  
  debounce(key, fn, delay) {
    if (this.debounceTimers.has(key)) {
      clearTimeout(this.debounceTimers.get(key));
    }
    
    const timer = setTimeout(() => {
      fn();
      this.debounceTimers.delete(key);
    }, delay);
    
    this.debounceTimers.set(key, timer);
  }
  
  async reloadModule(moduleId) {
    console.log(`[Hot Reload] Reiniciando módulo: ${moduleId}`);
    
    try {
      // Detener módulo actual
      const proc = this.bus.processes.get(moduleId);
      if (proc) {
        proc.kill('SIGTERM');
        
        // Esperar a que termine o forzar
        await Promise.race([
          new Promise(resolve => proc.once('exit', resolve)),
          new Promise(resolve => setTimeout(resolve, 5000))
        ]);
        
        if (!proc.killed) {
          proc.kill('SIGKILL');
        }
      }
      
      // Reiniciar
      const mod = this.bus.registry.get(moduleId);
      if (mod) {
        await this.bus.startModule(mod);
        console.log(`[Hot Reload] ${moduleId} reiniciado exitosamente`);
      }
    } catch (err) {
      console.error(`[Hot Reload] Error reiniciando ${moduleId}:`, err);
    }
  }
}
```

---

### 4.3 CLI de Debugging

```javascript
// scripts/blueprint-cli.js
#!/usr/bin/env node

import { createInterface } from 'readline';
import fs from 'fs';
import path from 'path';

const COMMANDS = {
  async trace(args) {
    const moduleId = args[0];
    const port = args[1];
    
    if (!moduleId) {
      console.error('Uso: trace <module-id> [port]');
      process.exit(1);
    }
    
    console.log(`Tracing mensajes para ${moduleId}${port ? `:${port}` : ''}...`);
    
    // Leer desde logs/events.log
    const logPath = path.join(process.cwd(), 'logs/events.log');
    if (!fs.existsSync(logPath)) {
      console.log('No hay logs disponibles');
      return;
    }
    
    const lines = fs.readFileSync(logPath, 'utf8').split('\n');
    let count = 0;
    
    for (const line of lines.reverse()) {
      if (!line.trim()) continue;
      
      try {
        const event = JSON.parse(line);
        if (event.module === moduleId || event.target_module === moduleId) {
          if (!port || event.port === port || event.target_port === port) {
            console.log(`[${new Date(event.timestamp).toISOString()}] ${event.type || 'message'}`);
            console.log(JSON.stringify(event, null, 2));
            console.log('---');
            count++;
            if (count >= 20) break; // Limitar a 20 eventos
          }
        }
      } catch {}
    }
    
    console.log(`Mostrados ${count} eventos`);
  },
  
  async inject(args) {
    const moduleId = args[0];
    const payloadStr = args.slice(1).join(' ');
    
    if (!moduleId || !payloadStr) {
      console.error('Uso: inject <module-id> <json-payload>');
      process.exit(1);
    }
    
    let payload;
    try {
      payload = JSON.parse(payloadStr);
    } catch {
      console.error('Payload inválido, debe ser JSON válido');
      process.exit(1);
    }
    
    // Enviar al runtime via stdin o socket
    const message = {
      type: 'inject_message',
      target_module: moduleId,
      payload,
      timestamp: Date.now()
    };
    
    process.stdout.write(JSON.stringify(message) + '\n');
    console.log(`Mensaje inyectado a ${moduleId}`);
  },
  
  async status() {
    // Leer estado del runtime
    const memoryPath = path.join(process.cwd(), 'logs/session-memory.json');
    
    if (!fs.existsSync(memoryPath)) {
      console.log('Sistema no iniciado (no hay session-memory.json)');
      return;
    }
    
    const memory = JSON.parse(fs.readFileSync(memoryPath, 'utf8'));
    
    console.log('=== Estado del Sistema ===\n');
    
    console.log('Últimos comandos:');
    for (const cmd of (memory.command_history || []).slice(-5)) {
      console.log(`  [${new Date(cmd.timestamp).toLocaleTimeString()}] ${cmd.command}`);
    }
    
    console.log('\nAplicaciones recientes:');
    for (const app of (memory.recent_applications || []).slice(-5)) {
      console.log(`  - ${app}`);
    }
    
    console.log('\nEstadísticas:');
    console.log(`  Total comandos: ${memory.command_history?.length || 0}`);
    console.log(`  Total aplicaciones: ${memory.recent_applications?.length || 0}`);
    console.log(`  Última actualización: ${new Date(memory.last_updated).toISOString()}`);
  },
  
  async validate() {
    console.log('Validando blueprint...\n');
    
    try {
      const blueprint = JSON.parse(
        fs.readFileSync(path.join(process.cwd(), 'blueprints/system.v0.json'), 'utf8')
      );
      
      let errors = 0;
      
      // Validar módulos
      for (const mod of blueprint.modules || []) {
        const manifestPath = path.join(process.cwd(), 'modules', mod.id, 'manifest.json');
        if (!fs.existsSync(manifestPath)) {
          console.error(`  ❌ Módulo '${mod.id}': manifest.json no encontrado`);
          errors++;
        } else {
          console.log(`  ✓ Módulo '${mod.id}': OK`);
        }
      }
      
      // Validar conexiones
      for (const conn of blueprint.connections || []) {
        const fromExists = blueprint.modules.some(m => m.id === conn.from.module);
        const toExists = blueprint.modules.some(m => m.id === conn.to.module);
        
        if (!fromExists) {
          console.error(`  ❌ Conexión: origen '${conn.from.module}' no existe`);
          errors++;
        }
        if (!toExists) {
          console.error(`  ❌ Conexión: destino '${conn.to.module}' no existe`);
          errors++;
        }
      }
      
      console.log(`\n${errors === 0 ? '✓ Blueprint válido' : `❌ ${errors} errores encontrados`}`);
    } catch (err) {
      console.error('Error validando blueprint:', err.message);
    }
  }
};

async function main() {
  const [command, ...args] = process.argv.slice(2);
  
  if (!command || command === 'help') {
    console.log(`
Blueprint CLI - Herramientas de debugging

Comandos:
  trace <module-id> [port]     - Mostrar últimos mensajes de un módulo
  inject <module-id> <payload>   - Inyectar mensaje a un módulo
  status                       - Mostrar estado del sistema
  validate                     - Validar blueprint y módulos
  help                         - Mostrar esta ayuda

Ejemplos:
  node scripts/blueprint-cli.js trace agent.main
  node scripts/blueprint-cli.js inject router.main '{"action":"test"}'
  node scripts/blueprint-cli.js validate
`);
    return;
  }
  
  const fn = COMMANDS[command];
  if (!fn) {
    console.error(`Comando desconocido: ${command}`);
    process.exit(1);
  }
  
  await fn(args);
}

main().catch(console.error);
```

---

## 5. Checklist de Implementación

### Fase 1: Crítico (Semana 1)
- [ ] Implementar Circuit Breaker en runtime
- [ ] Agregar backpressure al bus
- [ ] Agregar schema validation al registry
- [ ] Wrap JSON.parse en módulos principales (agent, router)

### Fase 2: Robustez (Semana 2)
- [ ] Agregar GC a router y otros módulos con Maps
- [ ] Implementar fallback para IA sin Ollama
- [ ] Crear tests unitarios para circuit breaker
- [ ] Crear tests unitarios para schema validation

### Fase 3: Observabilidad (Semana 3)
- [ ] Implementar distributed tracing
- [ ] Crear health check API
- [ ] Agregar métricas básicas (counters, timers)
- [ ] Dashboard simple de health status

### Fase 4: DX (Semana 4)
- [ ] Completar transforms.js
- [ ] Habilitar hot reload en dev
- [ ] Crear CLI de debugging
- [ ] Documentar nuevas APIs

---

## 6. Métricas de Éxito

| Métrica | Antes | Objetivo | Cómo Medir |
|---------|-------|----------|------------|
| Módulos con manejo de errores | ~10% | 100% | Contar try/catch en main.* |
| Tiempo de recuperación tras fallo | Manual | <30s | Desde crash hasta restart exitoso |
| Latencia p99 (IA) | 40s | 10s | Métricas de tiempo de respuesta |
| Tests de integración | 3 | 20+ | Archivos en tests/ |
| Cobertura de código | ~15% | 80% | Herramienta de coverage |
| Tiempo de setup para dev | 5 min | 30s | npm install + npm start |

---

*Guía generada para facilitar la planificación y ejecución de mejoras*
